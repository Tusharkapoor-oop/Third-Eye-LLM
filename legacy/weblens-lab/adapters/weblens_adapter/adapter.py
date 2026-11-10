"""WebLens Provider Adapter for fair benchmark evaluation.

Connects to the local WebLens service. Supports both independent mode
(keyless search via DDG, Wikipedia, Mwmbl) and backend-assisted mode.
"""

from __future__ import annotations

import time
from typing import Any

from weblens.apps.chat import ResearchChatSession
from weblens.apps.crawl2rag import Crawl2RAG
from weblens.apps.deep_research import DeepResearchAgent
from weblens.config import Settings
from weblens.service import WebLens

from ..common_interface.base import (
    AnswerResponse,
    ExtractItem,
    ExtractResponse,
    ProviderUsage,
    ResearchProvider,
    ResearchResponse,
    SearchItem,
    SearchResponse,
)


class WebLensAdapter(ResearchProvider):
    """Adapter for WebLens local intelligence engine."""

    def __init__(self, settings: Settings | None = None, *, independent: bool = True) -> None:
        self._settings = settings or Settings()
        self._independent = independent
        if self._independent:
            # Enforce independent provider chain (no Tavily or third-party paid keys)
            # CYCLE-1 (v10): keyless Bing added as first provider (see
            # evidence/prereg-v10-cycle1 chain note); baseline was ddg,mwmbl,wikipedia.
            self._settings.search_providers = "bing,ddg,mwmbl,wikipedia"
            self._settings.tavily_api_key = None

        self._service = WebLens(self._settings)
        self._usage = ProviderUsage()

    @property
    def name(self) -> str:
        return "weblens_independent" if self._independent else "weblens_tavily_assisted"

    @property
    def is_independent(self) -> bool:
        return self._independent

    async def close(self) -> None:
        await self._service.close()

    async def search(self, query: str, *, max_results: int = 5, **options: Any) -> SearchResponse:
        t0 = time.perf_counter()
        self._usage.requests += 1

        try:
            result = await self._service.search(
                query,
                max_results=max_results,
                freshness=options.get("freshness"),
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.total_latency_ms += elapsed_ms

            status = result.get("status", "error")
            raw_res = result.get("res", [])
            items = [
                SearchItem(
                    url=r.get("u", ""),
                    title=r.get("t", ""),
                    content=r.get("s", ""),
                    published_date=r.get("d"),
                )
                for r in raw_res
            ]

            toks = result.get("tok", 0)
            self._usage.successful_requests += 1
            self._usage.output_tokens += toks

            return SearchResponse(
                provider=self.name,
                query=query,
                results=items,
                status="ok" if status == "ok" and items else "no_reliable_result",
                latency_ms=elapsed_ms,
                tokens_returned=toks,
                credits_used=0.0 if self._independent else 1.0,
                error=result.get("error") if status != "ok" else None,
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.failed_requests += 1
            return SearchResponse(
                provider=self.name,
                query=query,
                results=[],
                status="error",
                latency_ms=elapsed_ms,
                tokens_returned=0,
                credits_used=0.0,
                error=str(e),
            )

    async def extract(self, urls: list[str], **options: Any) -> ExtractResponse:
        t0 = time.perf_counter()
        self._usage.requests += 1
        results: list[ExtractItem] = []
        total_toks = 0

        try:
            for url in urls[:10]:
                doc = await self._service.extract(url)
                doc_status = doc.get("status", "failed")
                if doc_status == "ok":
                    passages = doc.get("ps", [])
                    md_text = "\n\n".join(p.get("p", "") for p in passages)
                    results.append(
                        ExtractItem(
                            url=url,
                            raw_content=doc.get("text", "") or md_text,
                            markdown=md_text,
                            status="ok",
                        )
                    )
                    total_toks += doc.get("tok", 0)
                else:
                    results.append(
                        ExtractItem(
                            url=url,
                            raw_content="",
                            markdown="",
                            status="failed",
                            error=doc.get("error"),
                        )
                    )

            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.total_latency_ms += elapsed_ms
            self._usage.successful_requests += 1
            self._usage.output_tokens += total_toks

            return ExtractResponse(
                provider=self.name,
                results=results,
                latency_ms=elapsed_ms,
                tokens_returned=total_toks,
                credits_used=0.0,
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.failed_requests += 1
            return ExtractResponse(
                provider=self.name,
                results=[],
                latency_ms=elapsed_ms,
                tokens_returned=0,
                credits_used=0.0,
                error=str(e),
            )

    async def crawl(self, url: str, *, max_pages: int = 10, **options: Any) -> ExtractResponse:
        t0 = time.perf_counter()
        self._usage.requests += 1

        try:
            rag = Crawl2RAG(service=self._service)
            crawl_report = await rag.index_site(url, max_pages=max_pages, max_depth=2)

            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.total_latency_ms += elapsed_ms
            self._usage.successful_requests += 1

            items = [
                ExtractItem(
                    url=u,
                    raw_content=f"Indexed in local FTS5 vector store ({crawl_report.indexed_chunks} chunks)",
                    markdown=f"Indexed in local FTS5 vector store ({crawl_report.indexed_chunks} chunks)",
                    status="ok",
                )
                for u in crawl_report.crawled_urls
            ]

            return ExtractResponse(
                provider=self.name,
                results=items,
                latency_ms=elapsed_ms,
                tokens_returned=crawl_report.indexed_chunks * 60,
                credits_used=0.0,
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.failed_requests += 1
            return ExtractResponse(
                provider=self.name,
                results=[],
                latency_ms=elapsed_ms,
                tokens_returned=0,
                credits_used=0.0,
                error=str(e),
            )

    async def answer(self, query: str, **options: Any) -> AnswerResponse:
        t0 = time.perf_counter()
        self._usage.requests += 1

        try:
            session = ResearchChatSession(service=self._service)
            msg = await session.send_message(query)

            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.total_latency_ms += elapsed_ms
            self._usage.successful_requests += 1
            self._usage.output_tokens += msg.tokens_used

            return AnswerResponse(
                provider=self.name,
                query=query,
                answer=msg.content,
                citations=msg.citations,
                confidence=1.0 if msg.citations else 0.5,
                latency_ms=elapsed_ms,
                tokens_returned=msg.tokens_used,
                credits_used=0.0,
                status="ok" if msg.citations else "uncertain",
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.failed_requests += 1
            return AnswerResponse(
                provider=self.name,
                query=query,
                answer="",
                citations=[],
                confidence=None,
                latency_ms=elapsed_ms,
                tokens_returned=0,
                credits_used=0.0,
                status="error",
                error=str(e),
            )

    async def research(self, query: str, **options: Any) -> ResearchResponse:
        t0 = time.perf_counter()
        self._usage.requests += 1

        try:
            agent = DeepResearchAgent(service=self._service)
            result = await agent.execute_research(query)

            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.total_latency_ms += elapsed_ms
            toks = result.get("methodology", {}).get("tokens_returned", 0)
            self._usage.successful_requests += 1
            self._usage.output_tokens += toks

            sources = [{"url": f["url"], "snippet": f["claim"]} for f in result.get("key_findings", [])]
            contradictions = result.get("contradictions", [])
            report_md = f"# Research Dossier: {query}\n\n## Executive Summary\n{result.get('executive_summary', '')}\n\n## Findings\n"
            for f in result.get("key_findings", []):
                report_md += f"- [{f['claim']}]({f['url']})\n"

            return ResearchResponse(
                provider=self.name,
                query=query,
                report_markdown=report_md,
                subqueries=result.get("methodology", {}).get("subqueries_searched", []),
                sources=sources,
                contradictions=contradictions,
                latency_ms=elapsed_ms,
                tokens_returned=toks,
                credits_used=0.0,
                status=result.get("status", "ok"),
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.failed_requests += 1
            return ResearchResponse(
                provider=self.name,
                query=query,
                report_markdown="",
                subqueries=[query],
                sources=[],
                contradictions=[],
                latency_ms=elapsed_ms,
                tokens_returned=0,
                credits_used=0.0,
                status="error",
                error=str(e),
            )

    def get_usage(self) -> ProviderUsage:
        return self._usage
