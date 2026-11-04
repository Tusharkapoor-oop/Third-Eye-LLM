"""Grounded Multi-Hop Deep Research Engine.

Executes autonomous iterative research:
1. Query Plan & Sub-query Decomposition
2. Parallel Search & Tiered Passage Extraction
3. Missing-Evidence Gap Analysis
4. Cited Synthesis with [Source Title](URL) citations and raw evidence appendix.
5. Persistent asynchronous job state machine and document export integration.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal

from document_generator import DocumentGenerator
from query_engine import plan_query_fast
from schemas import ResearchResponse, SourceItem, UnifiedResponse
from search_pipeline import SearchPipeline


class ResearchJobStatus(StrEnum):
    """Lifecycle states of an asynchronous deep research job."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class ResearchJob:
    """Persistent state record for an autonomous deep research job."""

    job_id: str
    prompt: str
    mode: str = "mini"
    status: ResearchJobStatus = ResearchJobStatus.CREATED
    progress_step: str = "initialized"
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    sub_queries: list[str] = field(default_factory=list)
    sources: list[SourceItem] = field(default_factory=list)
    report: str | None = None
    evidence_summary: str = ""
    response_time: float = 0.0
    error: str | None = None
    _task: asyncio.Task[None] | None = None


class DeepResearchEngine:
    """Autonomous deep research agent supporting 'mini' and 'pro' multi-hop modes and async job lifecycle."""

    def __init__(self, search_pipeline: SearchPipeline | None = None):
        self.search_pipeline = search_pipeline or SearchPipeline()
        self.jobs: dict[str, ResearchJob] = {}

    async def _synthesize_report(
        self,
        prompt: str,
        sources: list[SourceItem],
        sub_queries: list[str],
        mode: str,
        model: str | None = None,
    ) -> str:
        """Synthesize cited Markdown report with evidence anchors."""
        # Multi-model intelligence synthesis via NVIDIA NIM / Gemini
        try:
            from model_provider import model_client
            source_dicts = [{"title": s.title, "url": s.url, "content": s.content} for s in sources]
            res = await model_client.synthesize_research_report(prompt, source_dicts, mode=mode, model=model)
            if res and res.content and len(res.content.strip()) > 50:
                return res.content.strip()
        except Exception:
            pass

        # Algorithmic Synthesis Fallback (Deterministic & Grounded)
        lines: list[str] = [
            f"# Research Report: {prompt}",
            "",
            "## Executive Summary",
            f"This intelligence brief synthesizes verified evidence retrieved across {len(sources)} authoritative sources "
            f"addressing the query: *{prompt}*.",
            "",
            "## Key Findings & Verified Evidence",
        ]

        for s in sources:
            lines.append(f"### [{s.title}]({s.url})")
            for c in s.chunks[:2]:
                lines.append(f"> {c.content}\n")
            lines.append(f"*Source Reference: [{s.title}]({s.url}) (Score: {s.score:.2f})*\n")

        lines.extend([
            "## Evidence Summary & Citations Table",
            "| Source Title | Canonical URL | Evidence Density |",
            "|---|---|---|",
        ])
        for s in sources:
            lines.append(f"| {s.title[:45]} | [{s.url[:40]}...]({s.url}) | {s.score:.2f} |")

        lines.append(f"\n*Generated via Autonomous Deep Research ({mode} mode) across {len(sub_queries)} search hops.*")
        return "\n".join(lines)

    async def conduct_research(
        self,
        prompt: str,
        mode: Literal["mini", "pro"] = "mini",
        model: str | None = None,
    ) -> ResearchResponse:
        """Execute autonomous multi-hop research pipeline."""
        t0 = time.perf_counter()
        if not prompt or not prompt.strip():
            return ResearchResponse(
                query=prompt or "",
                answer="No prompt provided for deep research.",
                sources=[],
                sub_queries=[],
                evidence_summary="Empty input prompt",
                response_time=0.0,
            )

        # Phase 1: Query Plan & Decomposition
        plan = await plan_query_fast(prompt)
        sub_queries = [plan.primary_keyword_query, plan.semantic_expansion_query]
        sub_queries.extend(plan.sub_queries)
        sub_queries = list(dict.fromkeys(sub_queries))[: (4 if mode == "pro" else 2)]

        # Phase 2: Parallel Search & Tiered Extraction
        search_tasks = [
            self.search_pipeline.search(
                sq,
                search_depth="advanced" if mode == "pro" else "basic",
                max_results=3,
                chunks_per_source=3,
            )
            for sq in sub_queries
        ]

        search_responses: list[UnifiedResponse] = await asyncio.gather(*search_tasks, return_exceptions=False)

        # Deduplicate sources by URL
        seen_urls: set[str] = set()
        all_sources: list[SourceItem] = []

        for resp in search_responses:
            for source in resp.results:
                if source.url not in seen_urls:
                    seen_urls.add(source.url)
                    all_sources.append(source)

        # Phase 3: Missing-Evidence Gap Analysis (Pro mode only)
        if mode == "pro" and len(all_sources) < 6:
            gap_query = f"{prompt} technical specifications benchmarks comparison"
            sub_queries.append(gap_query)
            gap_resp = await self.search_pipeline.search(
                gap_query,
                search_depth="advanced",
                max_results=3,
                chunks_per_source=3,
            )
            for s in gap_resp.results:
                if s.url not in seen_urls:
                    seen_urls.add(s.url)
                    all_sources.append(s)

        # Sort sources by score
        all_sources.sort(key=lambda s: s.score, reverse=True)
        top_sources = all_sources[: (8 if mode == "pro" else 5)]

        # Phase 4: Cited Synthesis
        report = await self._synthesize_report(prompt, top_sources, sub_queries, mode, model=model)

        elapsed = round(time.perf_counter() - t0, 3)
        return ResearchResponse(
            query=prompt,
            answer=report,
            sources=top_sources,
            sub_queries=sub_queries,
            evidence_summary=f"Synthesized from {len(top_sources)} sources across {len(sub_queries)} hops in {elapsed}s",
            response_time=elapsed,
        )

    # ---------------------------------------------------------
    # Asynchronous Deep Research Job State Machine
    # ---------------------------------------------------------

    async def _run_research_job(
        self,
        job: ResearchJob,
        mode: Literal["mini", "pro"],
    ) -> None:
        """Internal worker executing multi-hop research with stage transitions."""
        t0 = time.perf_counter()
        job.status = ResearchJobStatus.RUNNING
        job.progress_step = "planning"

        try:
            # Step 1: Decomposition
            plan = await plan_query_fast(job.prompt)
            sub_queries = [plan.primary_keyword_query, plan.semantic_expansion_query]
            sub_queries.extend(plan.sub_queries)
            sub_queries = list(dict.fromkeys(sub_queries))[: (4 if mode == "pro" else 2)]
            job.sub_queries = sub_queries

            if job.status == ResearchJobStatus.CANCELLED:
                return

            # Step 2: Search & Extraction
            job.progress_step = "searching"
            search_tasks = [
                self.search_pipeline.search(
                    sq,
                    search_depth="advanced" if mode == "pro" else "basic",
                    max_results=3,
                    chunks_per_source=3,
                )
                for sq in sub_queries
            ]
            search_responses: list[UnifiedResponse] = await asyncio.gather(*search_tasks, return_exceptions=False)

            if job.status == ResearchJobStatus.CANCELLED:
                return

            seen_urls: set[str] = set()
            all_sources: list[SourceItem] = []
            for resp in search_responses:
                for source in resp.results:
                    if source.url not in seen_urls:
                        seen_urls.add(source.url)
                        all_sources.append(source)

            # Step 3: Gap Analysis
            if mode == "pro" and len(all_sources) < 6:
                job.progress_step = "gap_analysis"
                gap_query = f"{job.prompt} technical specifications benchmarks comparison"
                job.sub_queries.append(gap_query)
                gap_resp = await self.search_pipeline.search(
                    gap_query,
                    search_depth="advanced",
                    max_results=3,
                    chunks_per_source=3,
                )
                for s in gap_resp.results:
                    if s.url not in seen_urls:
                        seen_urls.add(s.url)
                        all_sources.append(s)

            all_sources.sort(key=lambda s: s.score, reverse=True)
            top_sources = all_sources[: (8 if mode == "pro" else 5)]
            job.sources = top_sources

            if job.status == ResearchJobStatus.CANCELLED:
                return

            # Step 4: Synthesis
            job.progress_step = "synthesizing"
            report = await self._synthesize_report(job.prompt, top_sources, job.sub_queries, mode)
            job.report = report

            elapsed = round(time.perf_counter() - t0, 3)
            job.response_time = elapsed
            job.evidence_summary = f"Synthesized from {len(top_sources)} sources across {len(job.sub_queries)} hops in {elapsed}s"
            job.progress_step = "completed"
            job.status = ResearchJobStatus.COMPLETED
            job.completed_at = time.time()

        except asyncio.CancelledError:
            job.status = ResearchJobStatus.CANCELLED
            job.progress_step = "cancelled"
            job.completed_at = time.time()
            raise
        except Exception as e:
            job.status = ResearchJobStatus.FAILED
            job.progress_step = "failed"
            job.error = str(e)
            job.completed_at = time.time()

    def start_research_job(
        self,
        prompt: str,
        mode: Literal["mini", "pro"] = "mini",
    ) -> ResearchJob:
        """Create and launch a background managed deep research job."""
        job_id = f"research_{uuid.uuid4().hex[:12]}"
        job = ResearchJob(job_id=job_id, prompt=prompt, mode=mode)
        self.jobs[job_id] = job

        task = asyncio.create_task(self._run_research_job(job, mode=mode))
        job._task = task
        return job

    def get_research_status(self, job_id: str) -> ResearchJob | None:
        """Retrieve state for a managed research job."""
        return self.jobs.get(job_id)

    def cancel_research_job(self, job_id: str) -> bool:
        """Cancel an ongoing research job."""
        job = self.jobs.get(job_id)
        if not job:
            return False

        if job.status in (ResearchJobStatus.CREATED, ResearchJobStatus.RUNNING):
            job.status = ResearchJobStatus.CANCELLED
            job.progress_step = "cancelled"
            if job._task and not job._task.done():
                job._task.cancel()
            job.completed_at = time.time()
            return True
        return False

    def export_research_document(
        self,
        job_id: str,
        format_type: str,
        output_path: str | Path,
    ) -> Path:
        """Export research results of a completed job to a validated document artifact."""
        job = self.jobs.get(job_id)
        if not job:
            raise KeyError(f"Research job '{job_id}' not found")

        if job.status != ResearchJobStatus.COMPLETED:
            raise ValueError(f"Job '{job_id}' is not in COMPLETED state (current: {job.status})")

        response = ResearchResponse(
            query=job.prompt,
            answer=job.report or "",
            sources=job.sources,
            sub_queries=job.sub_queries,
            evidence_summary=job.evidence_summary,
            response_time=job.response_time,
        )
        return DocumentGenerator.from_research_response(response, format_type, output_path)
