"""MCP-backed adapters for the real local and deployed WebLens systems.

The older ``WebLensAdapter`` intentionally calls the service in-process and is
useful for unit experiments.  It must not be used as evidence for an MCP
transport comparison.  This adapter always crosses an MCP boundary: stdio for
the local process and Streamable HTTP for the deployed target.
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Literal

from evaluations.provenance import redact_error
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from .common_interface.base import (
    AnswerResponse,
    ExtractItem,
    ExtractResponse,
    ProviderUsage,
    ResearchProvider,
    ResearchResponse,
    SearchItem,
    SearchResponse,
)

SystemName = Literal["local_weblens", "deployed_weblens"]


class MCPWebLensAdapter(ResearchProvider):
    """Call a WebLens MCP server through its real transport."""

    def __init__(
        self,
        *,
        system: SystemName,
        endpoint: str | None = None,
        python_executable: str | None = None,
        repo_root: Path | None = None,
        profile: str = "full",
        read_timeout_seconds: float = 35.0,
    ) -> None:
        self.system = system
        self.endpoint = endpoint.rstrip("/") if endpoint else None
        self.repo_root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
        self.profile = profile
        self.read_timeout_seconds = read_timeout_seconds
        self._python = python_executable or sys.executable
        self._stack: AsyncExitStack | None = None
        self._client: Client | None = None
        self._usage = ProviderUsage()
        self._tools: list[str] = []
        self.last_call_metadata: dict[str, Any] = {}
        self.identity: dict[str, Any] = {"system": system, "transport": "unknown"}

    @property
    def name(self) -> str:
        return self.system

    @property
    def is_independent(self) -> bool:
        return True

    def _stdio_params(self) -> StdioServerParameters:
        package_root = self.repo_root / "weblens"
        # Do not inherit credentials into the independent local provider.
        env = {k: v for k, v in os.environ.items() if k not in {
            "TAVILY_API_KEY",
            "WEBLENS_TAVILY_API_KEY",
            "BRAVE_API_KEY",
            "WEBLENS_BRAVE_API_KEY",
        }}
        env.update({
            "PYTHONPATH": str(package_root / "src"),
            "WEBLENS_SEARCH_PROVIDERS": "ddg,mwmbl,wikipedia",
            "WEBLENS_TAVILY_API_KEY": "",
            "WEBLENS_BRAVE_API_KEY": "",
            "WEBLENS_CACHE_ENABLED": "false",
            "WEBLENS_MCP_PROFILE": self.profile,
        })
        return StdioServerParameters(
            command=self._python,
            args=["-m", "weblens.cli", "serve", "--profile", self.profile],
            cwd=str(package_root),
            env=env,
        )

    async def open(self) -> dict[str, Any]:
        if self._client is not None:
            return self.identity
        server: Any
        if self.system == "local_weblens":
            server = self._stdio_params()
            self.identity["transport"] = "stdio"
        else:
            if not self.endpoint:
                raise ValueError("deployed WebLens endpoint is required")
            server = self.endpoint
            self.identity["transport"] = "streamable_http"
            self.identity["endpoint"] = self.endpoint

        self._stack = AsyncExitStack()
        self._client = await self._stack.enter_async_context(
            Client(server, mode="auto", read_timeout_seconds=self.read_timeout_seconds)
        )
        tools = await self._client.list_tools()
        self._tools = [tool.name for tool in tools.tools]
        info = self._client.server_info
        if info is not None:
            self.identity["server_name"] = getattr(info, "name", None)
            self.identity["server_version"] = getattr(info, "version", None)
        self.identity["tool_count"] = len(self._tools)
        self.identity["tools"] = self._tools
        self.identity["protocol_version"] = self._client.protocol_version
        return self.identity

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._client = None

    async def _call(self, name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], float, bool, str | None]:
        if self._client is None:
            await self.open()
        assert self._client is not None
        started = time.perf_counter()
        self._usage.requests += 1
        try:
            result = await self._client.call_tool(name, arguments)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            text = next((getattr(block, "text", "") for block in result.content), "")
            payload = json.loads(text) if text else {}
            self.last_call_metadata = {
                "backend_provider": payload.get("prov"),
                "model": payload.get("model"),
                "cache_state": payload.get("cache", "unknown"),
            }
            ok = not result.is_error and payload.get("status") not in {"error"}
            if ok:
                self._usage.successful_requests += 1
            else:
                self._usage.failed_requests += 1
            self._usage.total_latency_ms += elapsed_ms
            self._usage.output_tokens += int(payload.get("tok", 0) or payload.get("tokens", 0) or 0)
            return payload, elapsed_ms, ok, None if ok else redact_error(payload.get("msg") or payload.get("error"))
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self._usage.failed_requests += 1
            self._usage.total_latency_ms += elapsed_ms
            return {}, elapsed_ms, False, redact_error(exc)

    async def search(self, query: str, *, max_results: int = 5, **options: Any) -> SearchResponse:
        data, elapsed, ok, error = await self._call(
            "web_search",
            {"query": query, "max_results": max_results, **{k: v for k, v in options.items() if v is not None}},
        )
        items = [
            SearchItem(url=item.get("u", ""), title=item.get("t", ""), content=item.get("s", ""), published_date=item.get("d"))
            for item in data.get("res", [])
        ]
        status = "ok" if ok and items else "no_reliable_result" if ok else "error"
        return SearchResponse(
            provider=self.name,
            query=query,
            results=items,
            status=status,
            latency_ms=elapsed,
            tokens_returned=int(data.get("tok", 0) or 0),
            credits_used=0.0,
            error=error,
        )

    async def extract(self, urls: list[str], **options: Any) -> ExtractResponse:
        started = time.perf_counter()
        results: list[ExtractItem] = []
        total_tokens = 0
        for url in urls[:10]:
            data, _, ok, error = await self._call("extract_url", {"url": url, **options})
            passages = data.get("ps", [])
            text = data.get("x", "") or "\n\n".join(p.get("x", "") for p in passages)
            total_tokens += int(data.get("tok", 0) or 0)
            results.append(ExtractItem(url=url, raw_content=text, markdown=text, status="ok" if ok and text else "failed", error=error))
        elapsed = (time.perf_counter() - started) * 1000.0
        return ExtractResponse(self.name, results, elapsed, total_tokens, error=None if results else "no results")

    async def crawl(self, url: str, *, max_pages: int = 10, **options: Any) -> ExtractResponse:
        data, elapsed, ok, error = await self._call(
            "crawl_site", {"url": url, "mode": "crawl", "max_pages": min(max_pages, 30), **options}
        )
        pages = data.get("pages", [])
        items = [
            ExtractItem(url=page.get("u", page.get("url", url)), raw_content=page.get("x", page.get("text", "")), markdown=page.get("x", page.get("text", "")), status="ok")
            for page in pages
        ]
        return ExtractResponse(self.name, items, elapsed, int(data.get("tok", 0) or 0), error=None if ok else error)

    async def answer(self, query: str, **options: Any) -> AnswerResponse:
        data, elapsed, ok, error = await self._call("deep_research", {"query": query, "max_tokens": options.get("max_tokens", 1500)})
        findings = data.get("f") or data.get("key_findings", [])
        summary = data.get("summary") or data.get("executive_summary", "")
        citations = [
            {
                "url": item.get("u") or item.get("url"),
                "title": item.get("c") or item.get("claim"),
                "span": item.get("s") or item.get("span"),
            }
            for item in findings
        ]
        tokens = int(data.get("tok", 0) or data.get("methodology", {}).get("tokens_returned", 0) or 0)
        return AnswerResponse(self.name, query, summary, citations, 0.9 if citations else None, elapsed, tokens, status="ok" if ok and summary else "uncertain", error=error)

    async def research(self, query: str, **options: Any) -> ResearchResponse:
        data, elapsed, ok, error = await self._call("deep_research", {"query": query, "max_tokens": options.get("max_tokens", 2500)})
        findings = data.get("f") or data.get("key_findings", [])
        methodology = data.get("methodology", {})
        gaps = data.get("gaps") or []
        tokens = int(data.get("tok", 0) or methodology.get("tokens_returned", 0) or 0)
        report = "# Research Report: " + query + "\n\n" + str(
            data.get("summary") or data.get("executive_summary", "")
        )
        report += "\n\n" + "\n".join(
            f"- {item.get('c') or item.get('claim')} ({item.get('u') or item.get('url')})"
            for item in findings
        )
        if gaps:
            report += "\n\n### Gaps\n" + "\n".join(f"- {gap}" for gap in gaps)
        return ResearchResponse(
            provider=self.name,
            query=query,
            report_markdown=report,
            subqueries=data.get("searched") or methodology.get("subqueries_searched", []),
            sources=[
                {
                    "url": item.get("u") or item.get("url"),
                    "claim": item.get("c") or item.get("claim"),
                    "span": item.get("s") or item.get("span"),
                }
                for item in findings
            ],
            contradictions=data.get("contradictions") or [],
            latency_ms=elapsed,
            tokens_returned=tokens,
            status="ok" if ok and findings else "error",
            error=error,
        )

    def get_usage(self) -> ProviderUsage:
        return self._usage
