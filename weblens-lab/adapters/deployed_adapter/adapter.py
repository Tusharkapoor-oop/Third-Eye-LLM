"""Deployed WebLens MCP Provider Adapter for Three-System Evaluation.

Connects to the deployed WebLens MCP endpoint on Google Cloud Run via HTTP/MCP (JSON-RPC).
Instruments remote latency, network payload sizes, status codes, and tool responses.
"""

from __future__ import annotations

import json
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


class DeployedWebLensAdapter(ResearchProvider):
    """Adapter for remote deployed WebLens MCP running on Google Cloud Run."""

    def __init__(
        self,
        endpoint_url: str = "https://weblens-16131012091.us-central1.run.app/mcp",
        *,
        timeout_s: float = 35.0,
    ) -> None:
        self.endpoint_url = endpoint_url.rstrip("/")
        self.timeout_s = timeout_s
        self._usage = ProviderUsage()
        self._client = httpx.AsyncClient(timeout=timeout_s)
        self._req_id = 0

    @property
    def name(self) -> str:
        return "deployed_weblens"

    @property
    def is_independent(self) -> bool:
        return True

    async def close(self) -> None:
        await self._client.aclose()

    def _next_id(self) -> str:
        self._req_id += 1
        return str(self._req_id)

    async def _call_mcp_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC tools/call request to the remote MCP HTTP server."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments,
            },
        }

        resp = await self._client.post(self.endpoint_url, json=payload)
        resp.raise_for_status()

        # Parse SSE or raw JSON response
        text = resp.text
        if "data:" in text:
            # Server-Sent Event stream
            for line in text.splitlines():
                if line.startswith("data:"):
                    line_data = line[len("data:"):].strip()
                    if line_data:
                        msg = json.loads(line_data)
                        if msg.get("id") == payload["id"]:
                            res = msg.get("result", {})
                            content_blocks = res.get("content", [])
                            if content_blocks and "text" in content_blocks[0]:
                                return json.loads(content_blocks[0]["text"])
                            return res
        # Fallback to direct json
        msg = resp.json()
        res = msg.get("result", {})
        if "content" in res and res["content"] and "text" in res["content"][0]:
            return json.loads(res["content"][0]["text"])
        return res

    async def search(self, query: str, *, max_results: int = 5, **options: Any) -> SearchResponse:
        t0 = time.perf_counter()
        self._usage.requests += 1

        try:
            data = await self._call_mcp_tool(
                "web_search",
                {"query": query, "max_results": max_results},
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.total_latency_ms += elapsed_ms

            status = data.get("status", "error")
            raw_res = data.get("res", [])
            items = [
                SearchItem(
                    url=r.get("u", ""),
                    title=r.get("t", ""),
                    content=r.get("s", ""),
                    published_date=r.get("d"),
                )
                for r in raw_res
            ]

            toks = data.get("tok", 0)
            self._usage.successful_requests += 1
            self._usage.output_tokens += toks

            return SearchResponse(
                provider=self.name,
                query=query,
                results=items,
                status="ok" if status == "ok" and items else "no_reliable_result",
                latency_ms=elapsed_ms,
                tokens_returned=toks,
                credits_used=0.0,
                error=data.get("error") if status != "ok" else None,
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
        items: list[ExtractItem] = []
        total_toks = 0

        try:
            for url in urls[:5]:
                data = await self._call_mcp_tool(
                    "extract_url",
                    {"url": url, "full": options.get("full", False)},
                )
                text = data.get("text", "")
                toks = data.get("tokens", 0)
                total_toks += toks
                items.append(
                    ExtractItem(
                        url=url,
                        raw_content=text,
                        markdown=text,
                        status="ok" if text else "failed",
                    )
                )

            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.total_latency_ms += elapsed_ms
            self._usage.successful_requests += 1
            self._usage.output_tokens += total_toks

            return ExtractResponse(
                provider=self.name,
                results=items,
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
            data = await self._call_mcp_tool(
                "crawl_site",
                {"url": url, "mode": "crawl", "max_pages": min(max_pages, 5)},
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.total_latency_ms += elapsed_ms

            pages = data.get("pages", [])
            items = [
                ExtractItem(
                    url=p.get("url", url),
                    raw_content=p.get("text", ""),
                    markdown=p.get("text", ""),
                    status="ok",
                )
                for p in pages
            ]

            toks = data.get("tokens", 0)
            self._usage.successful_requests += 1
            self._usage.output_tokens += toks

            return ExtractResponse(
                provider=self.name,
                results=items,
                latency_ms=elapsed_ms,
                tokens_returned=toks,
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
            data = await self._call_mcp_tool(
                "deep_research",
                {"query": query, "max_tokens": 1500},
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.total_latency_ms += elapsed_ms

            findings = data.get("key_findings", [])
            summary = data.get("executive_summary", "")
            citations = [{"url": f.get("url"), "title": f.get("claim")} for f in findings]
            toks = data.get("methodology", {}).get("tokens_returned", 0)

            self._usage.successful_requests += 1
            self._usage.output_tokens += toks

            return AnswerResponse(
                provider=self.name,
                query=query,
                answer=summary,
                citations=citations,
                confidence=0.9 if citations else 0.4,
                latency_ms=elapsed_ms,
                tokens_returned=toks,
                credits_used=0.0,
                status="ok" if summary else "uncertain",
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.failed_requests += 1
            return AnswerResponse(
                provider=self.name,
                query=query,
                answer="",
                citations=[],
                confidence=0.0,
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
            data = await self._call_mcp_tool(
                "deep_research",
                {"query": query, "max_tokens": 2500},
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.total_latency_ms += elapsed_ms

            findings = data.get("key_findings", [])
            summary = data.get("executive_summary", "")
            subqueries = data.get("methodology", {}).get("subqueries_searched", [])
            toks = data.get("methodology", {}).get("tokens_returned", 0)

            self._usage.successful_requests += 1
            self._usage.output_tokens += toks

            return ResearchResponse(
                provider=self.name,
                query=query,
                report_markdown=f"### Executive Summary\n{summary}\n\n### Findings\n" + "\n".join(f"- {f.get('claim')} ({f.get('url')})" for f in findings),
                subqueries=subqueries,
                sources=[{"url": f.get("url"), "title": f.get("claim")} for f in findings],
                contradictions=[],
                latency_ms=elapsed_ms,
                tokens_returned=toks,
                credits_used=0.0,
                status="ok" if summary else "partial",
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.failed_requests += 1
            return ResearchResponse(
                provider=self.name,
                query=query,
                report_markdown="",
                subqueries=[],
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

