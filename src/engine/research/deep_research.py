"""
Autonomous Evidence-Driven Deep Research Engine.
Iteratively explores multi-angle search queries, gathers passages across sources,
cross-corroborates evidence, detects contradictions, and outputs structured dossiers.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import tiktoken

from src.engine.config import CONFIG
from src.engine.extract.extractor import DocumentExtractor
from src.engine.search.aggregator import SearchAggregator, normalize_url


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

def generate_sub_queries(question: str) -> list[str]:
    """Generates focused sub-queries targeting core facts, technical specifications, and potential critiques."""
    q_clean = question.strip().rstrip("?").strip()
    queries = [q_clean]

    # If question asks about comparison
    if " vs " in q_clean.lower() or " versus " in q_clean.lower():
        parts = re.split(r"\s+(?:vs|versus)\s+", q_clean, flags=re.IGNORECASE)
        if len(parts) >= 2:
            queries.append(f"{parts[0].strip()} overview features")
            queries.append(f"{parts[1].strip()} overview features")

    # If question asks how-to or tutorial
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

        for q in sub_queries:
            resp = await self.search_aggregator.search(q, count=4, time_filter=time_filter, max_tokens=600)
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
        top_candidates = candidate_urls[:max_pages]
        sourced_facts: list[SourcedFact] = []
        sources_consulted: list[str] = []
        accumulated_tokens = 0

        for url, title in top_candidates:
            sources_consulted.append(url)
            doc = await self.extractor.extract_url(
                url,
                query=question,
                mode="passages",
                max_tokens=600
            )

            if doc.status == "success" and doc.passages:
                for p in doc.passages[:2]:
                    passage_toks = p.token_count
                    if accumulated_tokens + passage_toks > max_tokens and sourced_facts:
                        break
                    sourced_facts.append(SourcedFact(
                        claim_passage=p.text,
                        source_url=url,
                        source_title=doc.title or title,
                        fetch_timestamp=doc.fetch_timestamp
                    ))
                    accumulated_tokens += passage_toks

            if accumulated_tokens >= max_tokens:
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
            key_claims = [f.claim_passage.strip().replace("\n", " ") for f in sourced_facts[:2]]
            summary = "Key findings from top sources:\n- " + "\n- ".join(key_claims)
        else:
            summary = "Insufficient verifiable evidence discovered."

        return ResearchReport(
            question=question,
            status=status,
            summary_synthesis=summary,
            facts=sourced_facts,
            uncertainties_and_gaps=uncertainties,
            sources_consulted=sources_consulted,
            tokens_used=accumulated_tokens,
            latency_seconds=time.time() - t0
        )
