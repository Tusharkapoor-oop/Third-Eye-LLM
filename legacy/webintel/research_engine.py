"""Grounded multi-hop research.

Pipeline
--------
1. Query plan (lexical + semantic + authority queries).
2. Parallel multi-query search, then tiered extraction of the best sources.
3. Structure-aware passage selection across pages (global, not per-page only).
4. Missing-evidence gap check. With Gemini available the model names the gaps
   and proposes follow-up queries; without it a deterministic term-coverage
   check produces the gaps, so the field is never fabricated.
5. Cited synthesis with Gemini, followed by citation verification against the
   evidence actually fetched.

When no Gemini key is configured the tool returns ``evidence_only`` with the
verbatim passages and an explicit note. It never invents a synthesised answer.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Awaitable, Callable, Optional

from pydantic import BaseModel, Field

from .config import Config
from .extractor import TieredExtractor
from .query_engine import expand_query, gemini_available, gemini_client
from .reranker import PassageSelector
from .schemas import (Citation, EvidenceItem, Passage, ResearchPayload, dump)
from .search_pipeline import HybridSearchPipeline

ProgressFn = Callable[[float, str], Awaitable[None]]

_CITATION = re.compile(r"\[([^\]]{1,160})\]\((https?://[^)\s]+)\)")


class GapCheck(BaseModel):
    """Structured output for the gap-check call."""

    missing_facts: list[str] = Field(default_factory=list, max_length=8)
    followup_queries: list[str] = Field(default_factory=list, max_length=5)


async def _noop_progress(_pct: float, _msg: str) -> None:
    return None


def _evidence_digest(passages: list[Passage], limit: int = 14) -> str:
    lines: list[str] = []
    for idx, passage in enumerate(passages[:limit], start=1):
        body = re.sub(r"\s+", " ", passage.span)[:900]
        section = f" [{passage.section}]" if passage.section else ""
        lines.append(f"[{idx}] {passage.url}{section}\n{body}")
    return "\n\n".join(lines)


class GroundedResearcher:
    def __init__(self, cfg: Config, search: HybridSearchPipeline,
                 extractor: TieredExtractor, selector: PassageSelector):
        self.cfg = cfg
        self.search = search
        self.extractor = extractor
        self.selector = selector

    # ------------------------------------------------------------------
    async def run(self, question: str, *, mode: str = "mini",
                  max_sources: int = 6, max_tokens: int = 4000,
                  progress: Optional[ProgressFn] = None) -> ResearchPayload:
        started = time.perf_counter()
        progress = progress or _noop_progress
        max_sources = max(3, min(int(max_sources or 6), 10))

        await progress(4, "planning query")
        plan = await expand_query(question)

        await progress(12, f"searching {len(plan.subqueries())} query variants")
        outcome = await self.search.search(plan, max_results=max_sources + 2)
        candidates = outcome.candidates[:max_sources]

        budget_pages = 0
        budget_searches = len(plan.subqueries()) * len(outcome.provider_log or [1])
        if not candidates:
            return ResearchPayload(
                status="no_reliable_result", q=question,
                gaps=["no search results"],
                plan=self._plan_dict(plan),
                budget={"searches": 0, "pages": 0},
                note="all configured providers returned zero usable results; "
                     "no synthesis was attempted.",
                ms=int((time.perf_counter() - started) * 1000),
            )

        await progress(26, f"extracting {len(candidates)} sources")
        extractions = await self.extractor.extract_many(
            [c.url for c in candidates], query=question, concurrency=4
        )
        budget_pages += len(extractions)
        usable = [e for e in extractions if e.status == "ok" and e.markdown.strip()]
        blocked = [e for e in extractions if e.status != "ok"]

        await progress(48, "selecting passages")
        pages = [(e.final_url or e.url, e.markdown) for e in usable]
        passages = await self.selector.select_many(
            pages, question, plan, per_page=3, total=min(14, max_sources * 3)
        )
        titles = {e.final_url or e.url: e.title for e in usable}
        for passage in passages:
            passage.title = titles.get(passage.url, "")

        gaps, followups = await self._gap_check(question, passages)

        # One bounded second hop, only when the gap check produced something
        # concrete. This is a multi-hop engine, not an unbounded crawler.
        if followups and len(passages) >= 2:
            await progress(64, f"filling gaps with {min(len(followups), 2)} follow-up queries")
            known = {c.url for c in candidates}
            for followup in followups[:2]:
                sub_plan = plan.model_copy(update={
                    "primary_keyword_query": followup[:380],
                    "semantic_expansion_query": followup[:380],
                    "authority_query": followup[:380],
                })
                sub_outcome = await self.search.search(sub_plan, max_results=4)
                budget_searches += len(sub_plan.subqueries())
                fresh = [c for c in sub_outcome.candidates if c.url not in known][:3]
                if not fresh:
                    continue
                extra = await self.extractor.extract_many(
                    [c.url for c in fresh], query=followup, concurrency=3
                )
                budget_pages += len(extra)
                extra_usable = [e for e in extra if e.status == "ok" and e.markdown.strip()]
                extra_pages = [(e.final_url or e.url, e.markdown) for e in extra_usable]
                extra_passages = await self.selector.select_many(
                    extra_pages, followup, sub_plan, per_page=2, total=6
                )
                for passage in extra_passages:
                    passage.title = next(
                        (e.title for e in extra_usable
                         if (e.final_url or e.url) == passage.url), ""
                    )
                passages.extend(extra_passages)
                known.update(c.url for c in fresh)

        await progress(78, "synthesising grounded answer")
        answer, citation_urls = await self._synthesise(question, passages, mode=mode)

        evidence, used_passages = self._budget_evidence(passages, max_tokens)
        if not evidence:
            return ResearchPayload(
                status="no_reliable_result", q=question,
                gaps=gaps or ["no extractable passages"],
                plan=self._plan_dict(plan),
                budget={"searches": budget_searches, "pages": budget_pages},
                note="sources were reachable but no passage survived the relevance gate.",
                ms=int((time.perf_counter() - started) * 1000),
            )

        citations = self._build_citations(evidence, citation_urls)
        status = "ok" if answer else "evidence_only"
        note_parts = [
            "evidence spans are verbatim; each u is the exact URL fetched at ts."
        ]
        if blocked:
            note_parts.append(
                f"{len(blocked)}/{len(extractions)} sources could not be extracted "
                f"({', '.join(sorted({e.status for e in blocked}))})."
            )
        if answer:
            verified = {c.url for c in citations}
            unverified = [u for u in citation_urls if u not in verified]
            if unverified:
                note_parts.append(
                    f"{len(unverified)} citation URL(s) in the synthesis were not in the "
                    "fetched evidence set and were removed from the citation list."
                )
        else:
            note_parts.append(
                "GEMINI_API_KEY is not configured, so no synthesis was requested: "
                "the payload is raw cited evidence only."
            )
        await progress(96, "finalising")
        return ResearchPayload(
            status=status,
            q=question,
            answer=answer,
            citations=citations,
            evidence=evidence,
            gaps=gaps,
            plan=self._plan_dict(plan),
            budget={"searches": budget_searches, "pages": budget_pages},
            note=" ".join(note_parts),
            ms=int((time.perf_counter() - started) * 1000),
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _plan_dict(plan) -> dict:
        return {
            "primary": plan.primary_keyword_query,
            "semantic": plan.semantic_expansion_query,
            "authority": plan.authority_query,
            "tokens": plan.bm25_tokens,
            "locks": plan.lexical_locks,
            "intent": plan.intent,
            "source": plan.source,
            "expand_ms": plan.expand_ms,
        }

    async def _gap_check(self, question: str, passages: list[Passage]
                         ) -> tuple[list[str], list[str]]:
        client = gemini_client()
        if client is None or not passages:
            return self._lexical_gaps(question, passages), []

        prompt = (
            "You audit research evidence for a question.\n"
            f"QUESTION: {question}\n\nEVIDENCE:\n{_evidence_digest(passages, 10)}\n\n"
            "Identify what is still missing to answer the question completely: exact "
            "numbers, versions, steps, code, or comparisons. Then propose at most 3 "
            "targeted follow-up search queries that would fill those gaps. Return JSON "
            "only. If the evidence is sufficient, return empty lists."
        )
        try:
            from google.genai import types

            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        response_mime_type="application/json",
                        response_schema=GapCheck,
                    ),
                ),
                timeout=12.0,
            )
            parsed = GapCheck.model_validate_json((response.text or "").strip())
            return parsed.missing_facts[:6], parsed.followup_queries[:3]
        except Exception:
            return self._lexical_gaps(question, passages), []

    @staticmethod
    def _lexical_gaps(question: str, passages: list[Passage]) -> list[str]:
        from .utils import STOPWORDS

        terms = {
            t.lower() for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9_+.#-]{2,}", question)
            if t.lower() not in STOPWORDS
        }
        if not terms:
            return []
        blob = " ".join(p.span.lower() for p in passages)
        return sorted(t for t in terms if t not in blob)[:6]

    async def _synthesise(self, question: str, passages: list[Passage],
                          *, mode: str = "mini") -> tuple[Optional[str], list[str]]:
        if not passages or not gemini_available():
            return None, []
        client = gemini_client()
        if client is None:
            return None, []
        model = "gemini-2.5-pro" if mode == "pro" else "gemini-2.5-flash"

        digest = _evidence_digest(passages, 14)
        prompt = (
            "Answer the question using ONLY the numbered evidence below.\n"
            "Rules:\n"
            "- Every factual sentence must end with an inline citation copied exactly "
            "from the evidence URL, in the form [short title](URL).\n"
            "- Copy numbers, versions, flags and code verbatim. Never paraphrase code.\n"
            "- Use a Markdown table when the question is a comparison.\n"
            "- If the evidence does not answer part of the question, say so explicitly "
            "under a 'What the sources do not establish' heading. Do not guess.\n\n"
            f"QUESTION: {question}\n\nEVIDENCE:\n{digest}"
        )
        try:
            from google.genai import types

            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.15),
                ),
                timeout=60.0,
            )
            answer = (response.text or "").strip()
            if not answer:
                return None, []
            urls = [m.group(2) for m in _CITATION.finditer(answer)]
            return answer, list(dict.fromkeys(urls))
        except Exception:
            return None, []

    @staticmethod
    def _budget_evidence(passages: list[Passage], max_tokens: int
                         ) -> tuple[list[EvidenceItem], list[Passage]]:
        from .limits import json_tokens

        out: list[EvidenceItem] = []
        used: list[Passage] = []
        spent = 0
        for passage in passages:
            item = EvidenceItem(
                x=passage.span[:2400],
                u=passage.url,
                sec=passage.section,
                ts=None,
                kind=passage.kind,
            )
            cost = json_tokens(dump(item))
            if spent + cost > max_tokens and out:
                break
            out.append(item)
            used.append(passage)
            spent += cost
        return out, used

    @staticmethod
    def _build_citations(evidence: list[EvidenceItem], urls: list[str]) -> list[Citation]:
        known = {item.u for item in evidence}
        ordered = [u for u in urls if u in known]
        for item in evidence:
            if item.u not in ordered:
                ordered.append(item.u)
        out: list[Citation] = []
        for idx, url in enumerate(ordered, start=1):
            host = re.sub(r"^https?://(?:www\.)?", "", url).split("/")[0]
            out.append(Citation(title=host, url=url, idx=idx))
        return out[:16]
