"""Deployed WebLens MCP adapter.

Exercises the real remote deployment over Streamable HTTP with a full MCP
handshake (initialize -> notifications/initialized -> tools/list -> tools/call).
Every call records HTTP status, payload bytes, negotiated protocol version and
server identity so remote behaviour is distinguishable from a localhost run.
"""

from __future__ import annotations

import time
from typing import Any

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
from ..mcp_client import CallMeta, MCPHttpClient
from ..provenance import classify_search_status, results_hash

DEFAULT_ENDPOINT = "https://weblens-16131012091.us-central1.run.app/mcp"


def _extract_text(data: dict[str, Any]) -> str:
    passages = data.get("ps") or []
    texts = [
        str(p.get("x") or "").strip()
        for p in passages
        if isinstance(p, dict) and str(p.get("x") or "").strip()
    ]
    if texts:
        return "\n\n".join(texts)
    return str(data.get("text") or data.get("markdown") or "").strip()


def _finding_value(finding: dict[str, Any], short: str, long: str) -> Any:
    return finding.get(short) if finding.get(short) is not None else finding.get(long)


def _findings(data: dict[str, Any]) -> list[dict[str, Any]]:
    found = data.get("f") or data.get("key_findings") or []
    return [f for f in found if isinstance(f, dict)]


class DeployedWebLensAdapter(ResearchProvider):
    def __init__(
        self,
        endpoint_url: str | None = None,
        *,
        token: str | None = None,
        timeout_s: float = 45.0,
    ) -> None:
        self.endpoint_url = (endpoint_url or DEFAULT_ENDPOINT).rstrip("/")
        self.timeout_s = timeout_s
        self._usage = ProviderUsage()
        self._client = MCPHttpClient(
            self.endpoint_url,
            token=token,
            timeout_s=timeout_s,
            client_name="weblens-lab-deployed",
        )
        self.tools: list[str] = []
        self.server_info: dict[str, Any] = {}
        self.protocol_version: str | None = None
        self._initialize_ms: float | None = None
        self._tools_list_ms: float | None = None
        self._started = False

    @property
    def name(self) -> str:
        return "deployed_weblens_mcp"

    @property
    def is_independent(self) -> bool:
        return True

    async def start(self) -> None:
        t0 = time.perf_counter()
        await self._client.initialize()
        self._initialize_ms = (time.perf_counter() - t0) * 1000.0
        t0 = time.perf_counter()
        tools = await self._client.list_tools()
        self._tools_list_ms = (time.perf_counter() - t0) * 1000.0
        self.tools = [tool.name for tool in tools]
        self.server_info = self._client.server_info
        self.protocol_version = self._client.protocol_version
        self._started = True

    def start_metadata(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint_url,
            "server_info": self.server_info,
            "protocol_version": self.protocol_version,
            "tools": self.tools,
            "initialize_ms": round(self._initialize_ms, 1) if self._initialize_ms else None,
            "tools_list_ms": round(self._tools_list_ms, 1) if self._tools_list_ms else None,
        }

    async def close(self) -> None:
        await self._client.close()

    async def _call(self, tool: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], CallMeta, float]:
        if not self._started:
            await self.start()
        data, elapsed_ms, meta = await self._client.timed_call(tool, arguments)
        return data or {}, meta, elapsed_ms

    async def search(self, query: str, *, max_results: int = 5, **options: Any) -> SearchResponse:
        self._usage.requests += 1
        t0 = time.perf_counter()
        try:
            data, meta, elapsed_ms = await self._call(
                "web_search", {"query": query, "max_results": max_results}
            )
            self._usage.total_latency_ms += elapsed_ms
            items = [
                SearchItem(
                    url=r.get("u", ""),
                    title=r.get("t", ""),
                    content=r.get("s", ""),
                    published_date=r.get("d"),
                )
                for r in (data.get("res") or [])
            ]
            raw_status = data.get("status")
            status = classify_search_status(raw_status, len(items))
            if status == "error":
                self._usage.failed_requests += 1
            else:
                self._usage.successful_requests += 1
            self._usage.output_tokens += int(data.get("tok") or 0)
            return SearchResponse(
                provider=self.name,
                query=query,
                results=items,
                status=status,  # type: ignore[arg-type]
                latency_ms=elapsed_ms,
                tokens_returned=int(data.get("tok") or 0),
                credits_used=0.0,
                raw_status=raw_status,
                http_status=meta.http_status,
                response_bytes=meta.response_bytes,
                response_hash=results_hash(items),
                backend_provider=",".join(data.get("prov") or []) or "deployed_keyless",
                cache_state="unknown",
                error=data.get("msg") if raw_status == "error" else None,
            )
        except Exception as exc:
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
                error=f"{type(exc).__name__}: {str(exc)[:300]}",
                cache_state="unknown",
            )

    async def extract(self, urls: list[str], **options: Any) -> ExtractResponse:
        self._usage.requests += 1
        t0 = time.perf_counter()
        items: list[ExtractItem] = []
        total_tokens = 0
        try:
            for url in urls[:5]:
                data, _meta, _ms = await self._call(
                    "extract_url", {"url": url, "full": bool(options.get("full", False))}
                )
                text = _extract_text(data)
                total_tokens += int(data.get("tok") or 0)
                ok = data.get("status") == "ok" and bool(text)
                items.append(
                    ExtractItem(
                        url=url,
                        raw_content=text,
                        markdown=text,
                        status="ok" if ok else "failed",
                        error=None
                        if ok
                        else str(data.get("msg") or "extract returned no passages"),
                    )
                )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.total_latency_ms += elapsed_ms
            self._usage.successful_requests += 1
            self._usage.output_tokens += total_tokens
            return ExtractResponse(
                provider=self.name,
                results=items,
                latency_ms=elapsed_ms,
                tokens_returned=total_tokens,
                credits_used=0.0,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.failed_requests += 1
            return ExtractResponse(
                provider=self.name,
                results=items,
                latency_ms=elapsed_ms,
                tokens_returned=total_tokens,
                credits_used=0.0,
                error=f"{type(exc).__name__}: {str(exc)[:300]}",
            )

    async def crawl(self, url: str, *, max_pages: int = 5, **options: Any) -> ExtractResponse:
        self._usage.requests += 1
        t0 = time.perf_counter()
        try:
            data, _meta, elapsed_ms = await self._call(
                "crawl_site", {"url": url, "mode": "crawl", "max_pages": min(max_pages, 5)}
            )
            pages = data.get("pages") or []
            items = [
                ExtractItem(
                    url=p.get("u") or p.get("url") or url,
                    raw_content=p.get("text") or "",
                    markdown=p.get("text") or "",
                    status="ok" if (p.get("text") or "") else "failed",
                )
                for p in pages
            ]
            self._usage.total_latency_ms += elapsed_ms
            self._usage.successful_requests += 1
            self._usage.output_tokens += int(data.get("tok") or 0)
            return ExtractResponse(
                provider=self.name,
                results=items,
                latency_ms=elapsed_ms,
                tokens_returned=int(data.get("tok") or 0),
                credits_used=0.0,
                error=data.get("msg") if data.get("status") == "error" else None,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.failed_requests += 1
            return ExtractResponse(
                provider=self.name,
                results=[],
                latency_ms=elapsed_ms,
                tokens_returned=0,
                credits_used=0.0,
                error=f"{type(exc).__name__}: {str(exc)[:300]}",
            )

    async def answer(self, query: str, **options: Any) -> AnswerResponse:
        self._usage.requests += 1
        t0 = time.perf_counter()
        try:
            data, _meta, elapsed_ms = await self._call(
                "deep_research", {"query": query, "max_tokens": 1500}
            )
            findings = _findings(data)
            summary = data.get("summary") or data.get("executive_summary") or ""
            citations = [
                {
                    "url": _finding_value(f, "u", "url"),
                    "title": _finding_value(f, "c", "claim"),
                    "span": _finding_value(f, "s", "span"),
                }
                for f in findings
            ]
            tokens = int((data.get("methodology") or {}).get("tokens_returned") or data.get("tok") or 0)
            self._usage.successful_requests += 1
            self._usage.output_tokens += tokens
            return AnswerResponse(
                provider=self.name,
                query=query,
                answer=summary,
                citations=citations,
                confidence=0.9 if citations else 0.4,
                latency_ms=elapsed_ms,
                tokens_returned=tokens,
                credits_used=0.0,
                status="ok" if summary else "uncertain",
                error=data.get("msg") if data.get("status") == "error" else None,
            )
        except Exception as exc:
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
                error=f"{type(exc).__name__}: {str(exc)[:300]}",
            )

    async def research(self, query: str, **options: Any) -> ResearchResponse:
        self._usage.requests += 1
        t0 = time.perf_counter()
        try:
            data, _meta, elapsed_ms = await self._call(
                "deep_research", {"query": query, "max_tokens": 2500}
            )
            findings = _findings(data)
            summary = data.get("summary") or data.get("executive_summary") or ""
            methodology = data.get("methodology") or {}
            gaps = data.get("gaps") or []
            searched = data.get("searched") or methodology.get("subqueries_searched") or [query]
            tokens = int(methodology.get("tokens_returned") or data.get("tok") or 0)
            self._usage.successful_requests += 1
            self._usage.output_tokens += tokens
            report = f"### Executive Summary\n{summary}\n\n### Findings\n"
            report += "\n".join(
                f"- {_finding_value(f, 'c', 'claim')} ({_finding_value(f, 'u', 'url')})"
                for f in findings
            )
            if gaps:
                report += "\n\n### Gaps\n" + "\n".join(f"- {gap}" for gap in gaps)
            return ResearchResponse(
                provider=self.name,
                query=query,
                report_markdown=report,
                subqueries=list(searched),
                sources=[
                    {
                        "url": _finding_value(f, "u", "url"),
                        "title": _finding_value(f, "c", "claim"),
                        "heading": _finding_value(f, "h", "heading"),
                        "span": _finding_value(f, "s", "span"),
                    }
                    for f in findings
                ],
                contradictions=data.get("contradictions") or [],
                latency_ms=elapsed_ms,
                tokens_returned=tokens,
                credits_used=0.0,
                status="ok" if findings else "partial",
                error=data.get("msg") if data.get("status") == "error" else None,
            )
        except Exception as exc:
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
                error=f"{type(exc).__name__}: {str(exc)[:300]}",
            )

    def get_usage(self) -> ProviderUsage:
        return self._usage
