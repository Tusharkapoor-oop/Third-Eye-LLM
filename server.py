"""Model Context Protocol (MCP) Server: MyWebEngine.

Exposes the complete 5-tool Tavily-compatible web intelligence suite:
- web_search: Multi-query consensus, domain authority scoring, two-stage passage extraction
- extract_url: Tiered HTTP-to-Stealth extraction with atomic code/table protection
- web_map: Sitemap and BFS link graph discovery with regex path filtering
- crawl_website: Deep site ingestion with in-flight semantic passage pruning
- deep_research: Autonomous multi-hop research agent with cited synthesis
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import ipaddress
import json
import os
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from config import CONFIG
from crawl_engine import CrawlEngine
from event_store import OperationEvent, event_store
from extractor import TieredExtractor
from research_engine import DeepResearchEngine
from search_pipeline import SearchPipeline
from security import SecurityValidationError

# Initialize Singletons
extractor = TieredExtractor()
search_pipeline = SearchPipeline(extractor=extractor)
research_engine = DeepResearchEngine(search_pipeline=search_pipeline)
crawl_engine = CrawlEngine(extractor=extractor)


async def _recorded_operation(
    capability: str,
    operation: str,
    action: Callable[[], Awaitable[Any]],
    *,
    provider: str = "root_local",
) -> Any:
    """Run one real tool operation while preserving truthful lifecycle events."""
    started = time.perf_counter()
    await event_store.record_event(
        OperationEvent(
            capability=capability, operation=operation, status="attempted",
            duration_ms=0.0, provider=provider,
        )
    )
    try:
        result = await action()
    except asyncio.CancelledError:
        await event_store.record_event(
            OperationEvent(
                capability=capability, operation=operation, status="failed",
                duration_ms=(time.perf_counter() - started) * 1000,
                provider=provider, details={"cancelled": True},
            )
        )
        raise
    except (SecurityValidationError, PermissionError) as error:
        await event_store.record_event(
            OperationEvent(
                capability=capability, operation=operation, status="blocked",
                duration_ms=(time.perf_counter() - started) * 1000,
                provider=provider,
                details={"error_type": type(error).__name__, "error": str(error)[:300]},
            )
        )
        raise
    except Exception as error:
        await event_store.record_event(
            OperationEvent(
                capability=capability, operation=operation, status="failed",
                duration_ms=(time.perf_counter() - started) * 1000,
                provider=provider,
                details={"error_type": type(error).__name__, "error": str(error)[:300]},
            )
        )
        raise
    status = getattr(result, "status", None)
    terminal_status = "blocked" if status in {"blocked", "no_reliable_result"} else "success"
    await event_store.record_event(
        OperationEvent(
            capability=capability, operation=operation, status=terminal_status,
            duration_ms=(time.perf_counter() - started) * 1000,
            provider=provider,
            details={"result_status": status} if status else {},
        )
    )
    return result

mcp = MCPServer(
    name=CONFIG.server_name,
    version=CONFIG.server_version,
    instructions=(
        "Production-grade Web Intelligence Server providing Tavily-compatible search, "
        "tiered extraction with atomic table/code protection, site mapping, crawling, "
        "and autonomous multi-hop deep research."
    ),
)


@mcp.tool(
    name="web_search",
    description="Search web with consensus and passage ranking.",
)
async def web_search(
    query: str,
    search_depth: str = "basic",
    max_results: int = 5,
    chunks_per_source: int = 3,
    domains: list[str] = [],
) -> str:
    """Execute high-precision web search returning unified source items."""
    res = await _recorded_operation(
        "search", "web_search",
        lambda: search_pipeline.search(
            query=query,
            search_depth=search_depth,
            max_results=max_results,
            chunks_per_source=chunks_per_source,
            include_domains=domains or None,
        ),
    )
    return res.model_dump_json(indent=2)


@mcp.tool(
    name="extract_url",
    description="Extract URL passages with table and code preservation.",
)
async def extract_url(
    url: str,
    query: str = "",
    chunks_per_source: int = 3,
) -> str:
    """Extract clean Markdown passages from target URL."""
    res = await _recorded_operation(
        "extract", "extract_url",
        lambda: extractor.extract_url(
            url=url,
            query=query or None,
            chunks_per_source=chunks_per_source,
        ),
    )
    return res.model_dump_json(indent=2)


@mcp.tool(
    name="web_map",
    description="Map website URL graph via sitemap and BFS traversal.",
)
async def web_map(
    url: str,
    max_depth: int = 2,
    limit: int = 50,
) -> str:
    """Discover URLs across a target domain."""
    res = await _recorded_operation(
        "map_web", "web_map",
        lambda: crawl_engine.map_website(
            base_url=url,
            max_depth=max_depth,
            limit=limit,
        ),
    )
    return res.model_dump_json(indent=2)


@mcp.tool(
    name="crawl_website",
    description="Crawl site pages with passage ranking.",
)
async def crawl_website(
    url: str,
    limit: int = 15,
    instructions: str = "",
    chunks_per_source: int = 3,
) -> str:
    """Crawl and extract passages across a website."""
    res = await _recorded_operation(
        "crawl", "crawl_website",
        lambda: crawl_engine.crawl_website(
            base_url=url,
            limit=limit,
            instructions=instructions or None,
            chunks_per_source=chunks_per_source,
        ),
    )
    return res.model_dump_json(indent=2)


@mcp.tool(
    name="deep_research",
    description="Multi-hop research with cited synthesis.",
)
async def deep_research(
    input_prompt: str,
    mode: str = "mini",
    model: str = "",
) -> str:
    """Execute autonomous deep research pipeline."""
    res = await _recorded_operation(
        "research", "deep_research",
        lambda: research_engine.conduct_research(
            prompt=input_prompt,
            mode=mode,
            model=model or None,
        ),
    )
    return res.model_dump_json(indent=2)


def _register_extended_tools() -> None:
    """Expose browser, geographic, and document tools only in the opt-in profile."""
    if os.getenv("WEBLENS_V14_EXTENDED_TOOLS", "0").lower() not in {"1", "true", "yes"}:
        return

    from browser_agent import browser_agent
    from document_generator import DocumentGenerator
    from geo_mapper import geo_mapper
    from schemas import ResearchResponse
    from security import safe_resolve_path

    @mcp.tool(name="browser_create_session", description="Create an isolated controlled browser session.")
    async def browser_create_session(permission_level: int = 1) -> str:
        async def action() -> dict[str, Any]:
            session = await browser_agent.create_session(permission_level=int(permission_level))
            return {
                "session_id": session.session_id,
                "permission_level": session.permission_level,
                "created_at": session.created_at,
                "status": "ok",
            }

        return json.dumps(await _recorded_operation("browser", "browser_create_session", action, provider="playwright"))

    @mcp.tool(name="browser_navigate", description="Navigate a controlled browser session to a public URL.")
    async def browser_navigate(session_id: str, url: str) -> str:
        result = await _recorded_operation(
            "browser", "browser_navigate", lambda: browser_agent.navigate(session_id, url), provider="playwright"
        )
        return json.dumps(result)

    @mcp.tool(name="browser_back", description="Navigate backward in a controlled browser session.")
    async def browser_back(session_id: str) -> str:
        result = await _recorded_operation(
            "browser", "browser_back", lambda: browser_agent.back(session_id), provider="playwright"
        )
        return json.dumps(result)

    @mcp.tool(name="browser_forward", description="Navigate forward in a controlled browser session.")
    async def browser_forward(session_id: str) -> str:
        result = await _recorded_operation(
            "browser", "browser_forward", lambda: browser_agent.forward(session_id), provider="playwright"
        )
        return json.dumps(result)

    @mcp.tool(name="browser_refresh", description="Reload the current controlled browser page.")
    async def browser_refresh(session_id: str) -> str:
        result = await _recorded_operation(
            "browser", "browser_refresh", lambda: browser_agent.refresh(session_id), provider="playwright"
        )
        return json.dumps(result)

    @mcp.tool(name="browser_observe", description="Observe visible structured browser page evidence.")
    async def browser_observe(session_id: str) -> str:
        result = await _recorded_operation(
            "browser", "browser_observe", lambda: browser_agent.observe(session_id), provider="playwright"
        )
        return json.dumps(result)

    @mcp.tool(name="browser_interact", description="Perform a permission-checked browser interaction.")
    async def browser_interact(
        session_id: str,
        action: str,
        target: str,
        value: str = "",
        approval_token: str = "",
    ) -> str:
        allowed = {"click", "fill", "type", "select", "press_key", "scroll"}
        if action not in allowed:
            raise ValueError(f"unsupported browser action: {action}")
        result = await _recorded_operation(
            "browser", "browser_interact",
            lambda: browser_agent.interact(session_id, action, target, value, approval_token or None),
            provider="playwright",
        )
        return json.dumps(result)

    @mcp.tool(name="browser_close_session", description="Close a controlled browser session and its isolated context.")
    async def browser_close_session(session_id: str) -> str:
        await _recorded_operation(
            "browser", "browser_close_session", lambda: browser_agent.close_session(session_id), provider="playwright"
        )
        return json.dumps({"session_id": session_id, "status": "closed"})

    @mcp.tool(name="browser_screenshot", description="Capture a controlled browser viewport as base64 JPEG.")
    async def browser_screenshot(session_id: str) -> str:
        result = await _recorded_operation(
            "browser", "browser_screenshot", lambda: browser_agent.take_screenshot(session_id), provider="playwright"
        )
        return json.dumps({"session_id": session_id, "image_base64": result, "status": "ok"})

    @mcp.tool(name="geo_resolve", description="Extract and geocode locations from text with source attribution.")
    async def geo_resolve(text_content: str, source_url: str = "") -> str:
        locations = await _recorded_operation(
            "map_geo", "geo_resolve",
            lambda: geo_mapper.resolve_map_from_text(text_content, source_url=source_url or None),
            provider="nominatim",
        )
        return json.dumps({"status": "ok", "locations": [asdict(location) for location in locations]})

    @mcp.tool(name="generate_document", description="Generate and structurally validate a research document artifact.")
    async def generate_document(format_type: str, title: str, content: str, output_name: str) -> str:
        fmt = format_type.lower().lstrip(".")
        allowed_formats = {"docx", "pdf", "pptx", "xlsx", "csv", "md", "txt"}
        if fmt not in allowed_formats:
            raise ValueError(f"unsupported document format: {format_type}")
        name = Path(output_name).name
        if name != output_name or not name or name.startswith("."):
            raise ValueError("output_name must be a simple non-hidden filename")
        expected_suffix = f".{fmt}"
        if not name.lower().endswith(expected_suffix):
            name = f"{name}{expected_suffix}"
        target = safe_resolve_path(str(Path("cache") / "documents" / name))
        response = ResearchResponse(query=title, answer=content)
        generated = await _recorded_operation(
            "document", "generate_document",
            lambda: _generate_document(DocumentGenerator, response, fmt, target),
            provider=fmt,
        )
        return json.dumps({"status": "ok", "format": fmt, "path": str(generated), "validated": True})

    async def _generate_document(generator: Any, response: ResearchResponse, fmt: str, target: Path) -> Path:
        return generator.from_research_response(response, fmt, target)

    @mcp.tool(name="dashboard_metrics", description="Return persisted operation metrics without fabricated activity.")
    async def dashboard_metrics() -> str:
        return json.dumps(await event_store.get_dashboard_metrics())


_register_extended_tools()


async def shutdown_services() -> None:
    """Close every SQLite-backed singleton in the process.

    aiosqlite worker threads are non-daemon, so a connection that is left open
    keeps the interpreter alive after the event loop stops (observed as a hang
    after "N passed" in the test suite). The cache connections owned by
    search_pipeline and geo_mapper therefore have to be closed explicitly, not
    just the event store.
    """
    async def _close(name: str, closer) -> None:
        # Shutdown must never block the caller: a lock or socket belonging to an
        # event loop that has already been torn down would otherwise await
        # forever and hang interpreter exit.
        try:
            await asyncio.wait_for(closer(), timeout=10)
        except Exception as e:
            print(f"[shutdown] {name}: {type(e).__name__}: {e}", file=sys.stderr)

    await _close("search_pipeline", search_pipeline.close)

    async def _close_geo() -> None:
        from geo_mapper import geo_mapper  # lazily imported by the extended tool profile

        await geo_mapper.close()

    await _close("geo_mapper", _close_geo)
    await _close("extractor", extractor.close)
    await _close("event_store", event_store.close)


LOOPBACK_BIND_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1"})


def _is_loopback_host(host: str) -> bool:
    """Return True only for addresses that cannot be reached from another machine."""
    normalized = (host or "").strip().strip("[]").lower()
    if normalized in LOOPBACK_BIND_HOSTS:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _require_token_for_bind(host: str, token: str) -> None:
    """Refuse to expose an unauthenticated HTTP transport beyond loopback."""
    if token:
        return
    if _is_loopback_host(host):
        return
    raise SystemExit(
        f"Refusing to expose the HTTP transport on non-loopback host {host!r} "
        "without authentication. Set WEBINTEL_HTTP_TOKEN, or bind --host 127.0.0.1."
    )


def _bearer_token_guard(app: Any, token: str) -> Any:
    """ASGI middleware rejecting HTTP requests without the configured bearer token."""
    expected = f"Bearer {token}"

    async def guarded(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await app(scope, receive, send)
            return
        supplied = ""
        for key, value in scope.get("headers", []):
            if key.lower() == b"authorization":
                supplied = value.decode("latin-1")
                break
        if not hmac.compare_digest(supplied, expected):
            body = b'{"error":"unauthorized"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        (b"www-authenticate", b"Bearer"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await app(scope, receive, send)

    return guarded


async def run_server() -> None:
    """Run MCP server over STDIO or Streamable HTTP."""
    parser = argparse.ArgumentParser(description="MyWebEngine MCP Server")
    parser.add_argument("--http", action="store_true", help="Run Streamable HTTP transport instead of STDIO")
    parser.add_argument("--host", default=CONFIG.host, help="Bind host for HTTP transport")
    parser.add_argument("--port", type=int, default=CONFIG.port, help="Bind port for HTTP transport")
    args = parser.parse_args()

    try:
        if args.http:
            token = CONFIG.http_auth_token.strip()
            _require_token_for_bind(args.host, token)
            print(f"Starting {CONFIG.server_name} on http://{args.host}:{args.port}/mcp ...", file=sys.stderr)
            import uvicorn
            app = mcp.streamable_http_app()
            if token:
                app = _bearer_token_guard(app, token)
                print("HTTP transport requires a bearer token.", file=sys.stderr)
            config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
            server = uvicorn.Server(config)
            await server.serve()
        else:
            await mcp.run_stdio_async()
    finally:
        await shutdown_services()


def main() -> None:
    """Entry point for CLI script."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
