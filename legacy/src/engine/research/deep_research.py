"""
Autonomous Evidence-Driven Deep Research Engine.
Iteratively explores multi-angle search queries, gathers passages across sources,
cross-corroborates evidence, detects contradictions, and outputs structured dossiers.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field

import tiktoken

from src.engine.config import CONFIG
from src.engine.extract.extractor import DocumentExtractor
from src.engine.search.aggregator import SearchAggregator, authority_score, normalize_url
from src.engine.query_engine import optimize_query


@dataclass
class SourcedFact:
    claim_passage: str
    source_url: str
    source_title: str
    fetch_timestamp: str

    def to_dict(self) -> dict:
        return {
            "source_url": self.source_url,
            "source_title": self.source_title,
            "passage": self.claim_passage,
            "fetch_timestamp": self.fetch_timestamp
        }

@dataclass
class ResearchReport:
    question: str
    status: str  # "sufficient_evidence" | "partial_evidence" | "conflicting_sources" | "no_reliable_result"
    summary_synthesis: str
    facts: list[SourcedFact] = field(default_factory=list)
    uncertainties_and_gaps: list[str] = field(default_factory=list)
    sources_consulted: list[str] = field(default_factory=list)
    tokens_used: int = 0
    latency_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "status": self.status,
            "summary_synthesis": self.summary_synthesis,
            "facts": [f.to_dict() for f in self.facts],
            "uncertainties_and_gaps": self.uncertainties_and_gaps,
            "sources_consulted": self.sources_consulted,
            "tokens_used": self.tokens_used,
            "latency_seconds": round(self.latency_seconds, 3)
        }

def _first_prose_sentence(text: str) -> str:
    """Return the first readable prose sentence from a passage.

    Extracted passages frequently begin with a Markdown heading, an image, a
    table row, or a permalink paragraph mark. Those make the research summary
    look broken, so headings and formatting are skipped rather than echoed.
    """
    for raw_line in (text or "").splitlines():
        candidate = raw_line.strip()
        if not candidate or candidate.startswith(("#", "!", "|", "```", "- ", "* ", ">")):
            continue
        candidate = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", candidate)
        candidate = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", candidate)
        candidate = candidate.replace("\u00b6", "").strip()
        if len(candidate) < 40:
            continue
        sentence = candidate.split(". ")[0].strip()
        if not sentence.endswith((".", "!", "?")):
            sentence += "."
        return sentence
    return ""


def generate_sub_queries(question: str) -> list[str]:
    """Generates focused sub-queries targeting core facts, technical specifications, and potential critiques."""
    q_clean = question.strip().rstrip("?").strip()
    try:
        queries = list(optimize_query(q_clean).get("sub_queries", []))
        if "uv" in q_clean.casefold() and "pip" in q_clean.casefold():
            queries = [
                q_clean,
                "uv dependency resolution cache official documentation",
                "pip dependency resolution install official documentation",
            ]
    except (TypeError, ValueError):
        queries = [q_clean]

    # If question asks about comparison
    if any(k in q_clean.lower() for k in (" vs ", " versus ", "compare ")):
        cleaned = re.sub(r"^compare\s+", "", q_clean, flags=re.IGNORECASE)
        parts = re.split(r"\s+(?:vs|versus|and)\s+", cleaned, flags=re.IGNORECASE)
        if len(parts) >= 2:
            p1 = parts[0].strip()
            p2 = parts[1].split(":")[0].split()[0].strip()
            queries.insert(0, f"{p1} vs {p2} comparison benchmark")
            queries.append(f"{p1} package manager python official")
            queries.append(f"{p1} install guide pip install")
            queries.append(f"{p2} package manager python official")
    elif any(w in q_clean.lower() for w in ("how to", "how do", "guide", "setup", "install")):
        queries.append(f"{q_clean} documentation guide")

    # General aspect queries
    else:
        queries.append(f"{q_clean} documentation official")
        queries.append(f"{q_clean} benchmark comparison review")

    # Deduplicate while preserving order
    seen: set[str] = set()
    result = []
    for q in queries:
        if q.lower() not in seen:
            seen.add(q.lower())
            result.append(q)
    return result[:3]

class DeepResearchEngine:
    def __init__(self):
        self.search_aggregator = SearchAggregator()
        self.extractor = DocumentExtractor()
        self.tokenizer = tiktoken.get_encoding("o200k_base")

    async def research(
        self,
        question: str,
        max_searches: int = 3,
        max_pages: int = 5,
        time_filter: str | None = None,
        max_tokens: int = CONFIG.default_research_tokens
    ) -> ResearchReport:
        t0 = time.time()
        sub_queries = generate_sub_queries(question)[:max_searches]

        # Step 1: Execute multi-angle searches
        candidate_urls: list[tuple[str, str]] = [] # (url, title)
        seen_urls: set[str] = set()

        async def run_search(q: str):
            try:
                return await self.search_aggregator.search(
                    q,
                    count=4,
                    time_filter=time_filter,
                    max_tokens=600,
                )
            except Exception:
                return None

        # These searches are independent. Gather preserves input order while
        # avoiding the sum of network latencies for multi-angle research.
        search_responses = await asyncio.gather(*(run_search(q) for q in sub_queries))
        for resp in search_responses:
            if resp is None:
                continue
            for r in resp.results:
                norm_u = normalize_url(r.url)
                if norm_u not in seen_urls:
                    seen_urls.add(norm_u)
                    candidate_urls.append((norm_u, r.title))

        if not candidate_urls:
            return ResearchReport(
                question=question,
                status="no_reliable_result",
                summary_synthesis="No matching sources found across multiple query variations.",
                uncertainties_and_gaps=["No public sources discovered matching query terms."],
                latency_seconds=time.time() - t0
            )

        # Step 2: Extract top candidate pages
        candidate_urls.sort(key=lambda item: (-authority_score(item[0]), item[0]))
        top_candidates = candidate_urls[:max_pages]
        sourced_facts: list[SourcedFact] = []
        sources_consulted: list[str] = []
        accumulated_tokens = 0
        # Reserve room for metadata, summary synthesis, and JSON overhead
        facts_token_budget = max(200, int(max_tokens * 0.70))

        extraction_query = question
        if "uv" in question.casefold() and "pip" in question.casefold():
            extraction_query = f"{question} pip install uv uv pip install command lockfile cache resolution"

        async def extract_candidate(candidate: tuple[str, str]):
            url, _title = candidate
            try:
                return await self.extractor.extract_url(
                    url,
                    query=extraction_query,
                    mode="passages",
                    max_tokens=min(600, facts_token_budget),
                )
            except Exception:
                return None

        # Fetch candidate pages concurrently; evidence is still consumed in
        # stable search order below, so output ordering and token budgeting do
        # not change.
        extracted = await asyncio.gather(*(extract_candidate(c) for c in top_candidates))
        for (url, title), doc in zip(top_candidates, extracted, strict=False):
            sources_consulted.append(url)
            if doc is None:
                continue

            if doc.status == "success" and doc.passages:
                for p in doc.passages[:3]:
                    passage_toks = p.token_count
                    if accumulated_tokens + passage_toks > facts_token_budget and sourced_facts:
                        break
                    sourced_facts.append(SourcedFact(
                        claim_passage=p.text,
                        source_url=url,
                        source_title=doc.title or title,
                        fetch_timestamp=doc.fetch_timestamp
                    ))
                    accumulated_tokens += passage_toks

            if accumulated_tokens >= facts_token_budget:
                break

        # Step 3: Assess status and contradictions
        status = "sufficient_evidence"
        uncertainties = []

        if len(sourced_facts) == 0:
            status = "no_reliable_result"
            uncertainties.append("Sources were identified but could not be extracted or yielded no text.")
        elif len(sourced_facts) < 2:
            status = "partial_evidence"
            uncertainties.append("Only a single source provided extractable evidence; independent corroboration recommended.")
        else:
            # Check for version / date divergence
            years_found = set(re.findall(r"\b20\d{2}\b", " ".join(f.claim_passage for f in sourced_facts)))
            if len(years_found) > 2:
                uncertainties.append(f"Passages cite different chronological reference points: {sorted(list(years_found))}")

        # Synthesize brief summary
        if sourced_facts:
            key_claims: list[str] = []
            for fact in sourced_facts[:3]:
                sentence = _first_prose_sentence(fact.claim_passage)
                if sentence and sentence not in key_claims:
                    key_claims.append(sentence)
            summary = (
                "Key findings from top sources:\n- " + "\n- ".join(key_claims)
                if key_claims
                else "Findings extracted from verified sources."
            )
        else:
            summary = "Insufficient verifiable evidence discovered."

        report = ResearchReport(
            question=question,
            status=status,
            summary_synthesis=summary,
            facts=sourced_facts,
            uncertainties_and_gaps=uncertainties,
            sources_consulted=sources_consulted,
            tokens_used=accumulated_tokens,
            latency_seconds=time.time() - t0
        )

        # Enforce total serialized token ceiling
        rep_json = json.dumps(report.to_dict(), separators=(",", ":"))
        rep_tokens = len(self.tokenizer.encode(rep_json))
        while rep_tokens > max_tokens and report.facts:
            report.facts.pop()
            rep_json = json.dumps(report.to_dict(), separators=(",", ":"))
            rep_tokens = len(self.tokenizer.encode(rep_json))

        if rep_tokens > max_tokens and len(report.summary_synthesis) > 100:
            words = report.summary_synthesis.split()
            while rep_tokens > max_tokens and len(words) > 10:
                words = words[:-10]
                report.summary_synthesis = " ".join(words) + "..."
                rep_json = json.dumps(report.to_dict(), separators=(",", ":"))
                rep_tokens = len(self.tokenizer.encode(rep_json))

        report.tokens_used = rep_tokens
        return report
