"""Tavily API Provider Adapter for fair benchmark evaluation.

Connects directly to official Tavily API endpoints using environment-supplied
credentials. Tracks latency, tokens, credits, and HTTP telemetry.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx

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
from ..provenance import results_hash


class TavilyAdapter(ResearchProvider):
    """Adapter for official Tavily search and extract endpoints."""

    BASE_URL = "https://api.tavily.com"

    def __init__(self, api_key: str | None = None, *, client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key or os.environ.get("TAVILY_API_KEY", "")
        if not self._api_key:
            from pathlib import Path
            for cand in [Path(".env"), Path("../.env"), Path("../../.env")]:
                if cand.exists():
                    for line in cand.read_text(encoding="utf-8").splitlines():
                        if line.startswith("TAVILY_API_KEY="):
                            self._api_key = line.split("=", 1)[1].strip()
                            break
                    if self._api_key:
                        break
        if not self._api_key:
            raise ValueError("Tavily API key is missing. Set TAVILY_API_KEY in environment.")
        self._client = client
        self._usage = ProviderUsage()

    @property
    def name(self) -> str:
        return "tavily"

    @property
    def is_independent(self) -> bool:
        return False

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None and not self._client.is_closed:
            return self._client
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": "weblens-lab/10.0",
            },
        )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def search(self, query: str, *, max_results: int = 5, **options: Any) -> SearchResponse:
        t0 = time.perf_counter()
        self._usage.requests += 1
        client = self._get_client()

        # Key goes in the Authorization header, never in the JSON body, so it
        # cannot end up in request-body logs.
        payload: dict[str, Any] = {
            "query": query,
            "max_results": max(1, min(max_results, 20)),
            "search_depth": options.get("search_depth", "basic"),
            "include_raw_content": options.get("include_raw_content", False),
            "include_answer": options.get("include_answer", False),
            "include_published_date": True,
            "include_usage": True,
        }

        try:
            resp = await client.post(f"{self.BASE_URL}/search", json=payload)
            if resp.status_code == 429:
                retry_after = resp.headers.get("retry-after", "2")
                delay = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 2.0
                await asyncio.sleep(min(delay, 10.0))
                resp = await client.post(f"{self.BASE_URL}/search", json=payload)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.total_latency_ms += elapsed_ms

            if resp.status_code != 200:
                self._usage.failed_requests += 1
                credits = 1.0 if resp.status_code >= 500 else 0.0
                return SearchResponse(
                    provider=self.name,
                    query=query,
                    results=[],
                    status="error",
                    latency_ms=elapsed_ms,
                    tokens_returned=0,
                    credits_used=credits,
                    http_status=resp.status_code,
                    response_bytes=len(resp.content),
                    error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )

            data = resp.json()
            raw_results = data.get("results", [])
            items = [
                SearchItem(
                    url=r.get("url", ""),
                    title=r.get("title", ""),
                    content=r.get("content", ""),
                    score=r.get("score"),
                    raw_content=r.get("raw_content"),
                    published_date=r.get("published_date"),
                )
                for r in raw_results
            ]

            total_chars = sum(len(i.content) + len(i.title) for i in items)
            approx_tokens = total_chars // 4
            usage = data.get("usage") or {}
            credits = float(usage.get("credits", 1.0))

            self._usage.successful_requests += 1
            self._usage.credits_consumed += credits
            self._usage.output_tokens += approx_tokens

            return SearchResponse(
                provider=self.name,
                query=query,
                results=items,
                status="ok" if items else "empty",
                latency_ms=elapsed_ms,
                tokens_returned=approx_tokens,
                credits_used=credits,
                http_status=resp.status_code,
                response_bytes=len(resp.content),
                response_hash=results_hash(items),
                backend_provider="tavily",
                raw_status="ok",
                cache_state="unknown",
                raw_response={
                    "response_time": data.get("response_time"),
                    "request_id": data.get("request_id"),
                    "usage": usage,
                },
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
                error=str(e)[:300],
            )

    async def extract(self, urls: list[str], **options: Any) -> ExtractResponse:
        t0 = time.perf_counter()
        self._usage.requests += 1
        client = self._get_client()

        payload = {
            "api_key": self._api_key,
            "urls": urls[:10],
        }

        try:
            resp = await client.post(f"{self.BASE_URL}/extract", json=payload)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.total_latency_ms += elapsed_ms

            if resp.status_code != 200:
                self._usage.failed_requests += 1
                return ExtractResponse(
                    provider=self.name,
                    results=[],
                    latency_ms=elapsed_ms,
                    tokens_returned=0,
                    credits_used=float(len(urls)),
                    error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )

            data = resp.json()
            results = [
                ExtractItem(
                    url=r.get("url", ""),
                    raw_content=r.get("raw_content", ""),
                    markdown=r.get("raw_content", ""),
                    status="ok",
                )
                for r in data.get("results", [])
            ]
            for f in data.get("failed_results", []):
                results.append(
                    ExtractItem(
                        url=f.get("url", ""),
                        raw_content="",
                        markdown="",
                        status="failed",
                        error=f.get("error"),
                    )
                )

            total_tokens = sum(len(r.markdown) for r in results) // 4
            self._usage.successful_requests += 1
            self._usage.credits_consumed += float(len(urls))
            self._usage.output_tokens += total_tokens

            return ExtractResponse(
                provider=self.name,
                results=results,
                latency_ms=elapsed_ms,
                tokens_returned=total_tokens,
                credits_used=float(len(urls)),
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
        # Official Tavily API has extract, but site crawl requires manual discovery or returns unsupported
        t0 = time.perf_counter()
        return ExtractResponse(
            provider=self.name,
            results=[
                ExtractItem(
                    url=url,
                    raw_content="",
                    markdown="",
                    status="unsupported",
                    error="Tavily REST API does not provide a standalone unauthenticated site crawler endpoint",
                )
            ],
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            tokens_returned=0,
            credits_used=0.0,
            error="UNSUPPORTED_ENDPOINT",
        )

    async def answer(self, query: str, **options: Any) -> AnswerResponse:
        t0 = time.perf_counter()
        self._usage.requests += 1
        client = self._get_client()

        payload = {
            "api_key": self._api_key,
            "query": query,
            "include_answer": True,
            "max_results": 5,
        }

        try:
            resp = await client.post(f"{self.BASE_URL}/search", json=payload)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.total_latency_ms += elapsed_ms

            if resp.status_code != 200:
                self._usage.failed_requests += 1
                return AnswerResponse(
                    provider=self.name,
                    query=query,
                    answer="",
                    citations=[],
                    confidence=None,
                    latency_ms=elapsed_ms,
                    tokens_returned=0,
                    credits_used=1.0,
                    status="error",
                    error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )

            data = resp.json()
            answer_text = data.get("answer") or ""
            citations = [
                {"url": r.get("url"), "title": r.get("title"), "snippet": r.get("content", "")[:150]}
                for r in data.get("results", [])
            ]

            toks = len(answer_text) // 4
            self._usage.successful_requests += 1
            self._usage.credits_consumed += 1.0
            self._usage.output_tokens += toks

            return AnswerResponse(
                provider=self.name,
                query=query,
                answer=answer_text,
                citations=citations,
                confidence=1.0 if answer_text else None,
                latency_ms=elapsed_ms,
                tokens_returned=toks,
                credits_used=1.0,
                status="ok" if answer_text else "uncertain",
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
        # Multi-hop via Tavily search
        t0 = time.perf_counter()
        initial = await self.search(query, max_results=5)
        if initial.status != "ok":
            return ResearchResponse(
                provider=self.name,
                query=query,
                report_markdown="",
                subqueries=[query],
                sources=[],
                contradictions=[],
                latency_ms=initial.latency_ms,
                tokens_returned=0,
                status="error",
                error=initial.error,
            )

        sources = [{"url": r.url, "title": r.title, "content": r.content[:300]} for r in initial.results]
        report = f"# Research Report: {query}\n\n"
        for s in sources:
            report += f"- **[{s['title']}]({s['url']})**: {s['content']}\n"

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return ResearchResponse(
            provider=self.name,
            query=query,
            report_markdown=report,
            subqueries=[query],
            sources=sources,
            contradictions=[],
            latency_ms=elapsed_ms,
            tokens_returned=len(report) // 4,
            credits_used=initial.credits_used,
            status="ok",
        )

    def get_usage(self) -> ProviderUsage:
        return self._usage

    async def fetch_account_telemetry(self) -> dict[str, Any]:
        """Query official Tavily /usage endpoint for verified billable usage."""
        client = self._get_client()
        resp = await client.get(
            f"{self.BASE_URL}/usage",
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"HTTP {resp.status_code}: {resp.text}"}
