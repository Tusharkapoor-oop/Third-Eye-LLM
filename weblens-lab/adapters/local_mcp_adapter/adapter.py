"""Local WebLens MCP adapter.

Unlike the earlier adapter, this class does **not** import the WebLens service
and call it in-process. It launches the real local MCP server
(``python -m weblens.cli serve --http --profile full``) on loopback, performs the
MCP initialize/initialized handshake, enumerates the real tool registry, and
calls the tools over Streamable HTTP. That is the surface a local MCP client
actually uses.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
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
from ..mcp_client import CallMeta, MCPHttpClient, MCPTransportError
from ..provenance import classify_search_status, results_hash

ROOT = Path(__file__).resolve().parent.parent.parent.parent
CACHE_ROOT = ROOT / "weblens-lab" / "sandbox" / "temporary" / "local_mcp_cache"
LOG_ROOT = ROOT / "weblens-lab" / "sandbox" / "logs"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _extract_text(data: dict[str, Any]) -> str:
    """Read both the compact MCP passage schema and older text-shaped replies."""

    passages = data.get("ps") or []
    texts = [
        str(p.get("x") or "").strip()
        for p in passages
        if isinstance(p, dict) and str(p.get("x") or "").strip()
    ]
    if texts:
        return "\n\n".join(texts)
    text = data.get("text") or data.get("markdown") or ""
    return str(text).strip()


def _finding_value(finding: dict[str, Any], short: str, long: str) -> Any:
    return finding.get(short) if finding.get(short) is not None else finding.get(long)


def _findings(data: dict[str, Any]) -> list[dict[str, Any]]:
    found = data.get("f") or data.get("key_findings") or []
    return [f for f in found if isinstance(f, dict)]


class LocalMCPAdapter(ResearchProvider):
    """Adapter for a real local WebLens MCP server process."""

    def __init__(
        self,
        *,
        port: int | None = None,
        startup_timeout_s: float = 45.0,
        request_timeout_s: float = 45.0,
    ) -> None:
        self.port = port or _free_port()
        self.endpoint_url = f"http://127.0.0.1:{self.port}/mcp"
        self.startup_timeout_s = startup_timeout_s
        self.request_timeout_s = request_timeout_s
        self._usage = ProviderUsage()
        self._proc: subprocess.Popen[bytes] | None = None
        self._log_handle: Any = None
        self._client: MCPHttpClient | None = None
        self._run_id = uuid.uuid4().hex[:12]
        self.cache_dir = CACHE_ROOT / self._run_id
        self._health_ms: float | None = None
        self._initialize_ms: float | None = None
        self._tools_list_ms: float | None = None
        self.tools: list[str] = []
        self.server_info: dict[str, Any] = {}
        self.protocol_version: str | None = None
        self.resource_usage: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "local_weblens_mcp"

    @property
    def is_independent(self) -> bool:
        # Independent by construction: the subprocess is launched with
        # Tavily/Brave keys removed and only keyless providers enabled.
        return True

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            {
                "WEBLENS_SEARCH_PROVIDERS": "ddg,mwmbl,wikipedia",
                "WEBLENS_SEARCH_MODE": "fuse",
                "WEBLENS_CACHE_DIR": str(self.cache_dir),
                "WEBLENS_MCP_PROFILE": "full",
                "WEBLENS_LOG_LEVEL": "WARNING",
                "WEBLENS_HTTP_HOST": "127.0.0.1",
                "WEBLENS_HTTP_PORT": str(self.port),
                "WEBLENS_ALLOW_BROWSER": "false",
                "PYTHONPATH": os.pathsep.join(
                    [str(ROOT / "weblens" / "src"), str(ROOT / "src"), env.get("PYTHONPATH", "")]
                ),
            }
        )
        # Hard-strip every paid third-party search credential in the child so a
        # WebLens result can never be silently Tavily-backed.
        for key in (
            "WEBLENS_TAVILY_API_KEY",
            "WEBLENS_BRAVE_API_KEY",
            "TAVILY_API_KEY",
            "BRAVE_SEARCH_API_KEY",
            "EXA_API_KEY",
        ):
            env.pop(key, None)
        return env

    async def start(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        LOG_ROOT.mkdir(parents=True, exist_ok=True)
        self._log_handle = open(LOG_ROOT / f"local_mcp_{self._run_id}.log", "w", encoding="utf-8")
        cmd = [
            sys.executable,
            "-m",
            "weblens.cli",
            "serve",
            "--http",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--profile",
            "full",
        ]
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            cmd,
            cwd=str(ROOT),
            env=self._env(),
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )

        health_start = time.perf_counter()
        deadline = health_start + self.startup_timeout_s
        async with httpx.AsyncClient(timeout=2.0) as probe:
            while time.perf_counter() < deadline:
                if self._proc.poll() is not None:
                    raise MCPTransportError(
                        f"local MCP server exited early (code {self._proc.returncode}); see "
                        f"{self._log_handle.name if self._log_handle else 'log'}"
                    )
                try:
                    resp = await probe.get(f"http://127.0.0.1:{self.port}/")
                    if resp.status_code == 200:
                        self._health_ms = (time.perf_counter() - health_start) * 1000.0
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.25)
            else:
                raise MCPTransportError("local MCP server did not become healthy in time")

        self._client = MCPHttpClient(
            self.endpoint_url,
            timeout_s=self.request_timeout_s,
            client_name="weblens-lab-local",
        )
        t0 = time.perf_counter()
        await self._client.initialize()
        self._initialize_ms = (time.perf_counter() - t0) * 1000.0
        t0 = time.perf_counter()
        tools = await self._client.list_tools()
        self._tools_list_ms = (time.perf_counter() - t0) * 1000.0
        self.tools = [tool.name for tool in tools]
        self.server_info = self._client.server_info
        self.protocol_version = self._client.protocol_version

    def _ensure_started(self) -> None:
        if self._client is None:
            raise MCPTransportError("local MCP adapter not started")

    async def _call(self, tool: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], CallMeta, float]:
        self._ensure_started()
        assert self._client is not None
        data, elapsed_ms, meta = await self._client.timed_call(tool, arguments)
        return data or {}, meta, elapsed_ms

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
        if self._proc is not None:
            try:
                import psutil

                proc = psutil.Process(self._proc.pid)
                self.resource_usage = {
                    "rss_mb": round(proc.memory_info().rss / (1024 * 1024), 1),
                    "cpu_user_s": round(proc.cpu_times().user, 3),
                    "cpu_system_s": round(proc.cpu_times().system, 3),
                    "threads": proc.num_threads(),
                }
            except Exception:
                self.resource_usage = {}
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)
            self._proc = None
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

    def start_metadata(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint_url,
            "server_info": self.server_info,
            "protocol_version": self.protocol_version,
            "tools": self.tools,
            "health_ms": round(self._health_ms, 1) if self._health_ms else None,
            "initialize_ms": round(self._initialize_ms, 1) if self._initialize_ms else None,
            "tools_list_ms": round(self._tools_list_ms, 1) if self._tools_list_ms else None,
            "cache_dir": str(self.cache_dir),
            "pid": self._proc.pid if self._proc else None,
        }

    # -- provider interface ------------------------------------------------
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
                backend_provider=",".join(data.get("prov") or []) or "keyless",
                cache_state="cold",
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
                cache_state="cold",
            )

    async def extract(self, urls: list[str], **options: Any) -> ExtractResponse:
        self._usage.requests += 1
        t0 = time.perf_counter()
        items: list[ExtractItem] = []
        total_tokens = 0
        try:
            for url in urls[:10]:
                data, _meta, _ms = await self._call(
                    "extract_url",
                    {"url": url, "full": bool(options.get("full", False))},
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
                "crawl_site", {"url": url, "mode": "crawl", "max_pages": min(max_pages, 10)}
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
