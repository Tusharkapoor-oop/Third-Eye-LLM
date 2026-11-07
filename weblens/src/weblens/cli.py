"""Command-line interface: serve MCP, call tools directly, measure schemas."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import deque
from typing import Any

from . import __version__
from .config import Settings
from .service import WebLens
from .tokens import count_json_tokens, count_tokens


def _configure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


def _emit(payload: dict[str, Any], pretty: bool) -> None:
    if pretty:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))


async def _call(service: WebLens, args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "search":
        return await service.search(
            args.query,
            max_results=args.max_results,
            freshness=args.freshness,
            domains=args.domain,
            exclude_domains=args.exclude_domain,
            max_tokens=args.max_tokens,
        )
    if args.command == "extract":
        return await service.extract(
            args.url, query=args.query, max_tokens=args.max_tokens, full=args.full
        )
    if args.command == "crawl":
        return await service.crawl_site(
            args.url,
            mode=args.mode,
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            query=args.query,
            max_tokens=args.max_tokens,
        )
    if args.command == "research":
        return await service.deep_research(args.query, max_tokens=args.max_tokens)
    if args.command == "doctor":
        return await service.doctor(live=args.live)
    raise RuntimeError(f"unknown command {args.command}")


async def _run_command(args: argparse.Namespace) -> int:
    service = WebLens()
    try:
        payload = await _call(service, args)
    finally:
        await service.close()
    _emit(payload, getattr(args, "pretty", False))
    return 1 if payload.get("status") == "error" else 0


async def _run_cache(args: argparse.Namespace) -> int:
    from .cache import Cache

    cache = Cache(Settings())
    try:
        if args.cache_command == "stats":
            payload: dict[str, Any] = {
                "status": "ok",
                "path": str(cache.path),
                **cache.stats(),
            }
        else:
            removed = await (cache.clear() if args.all else cache.purge())
            payload = {
                "status": "ok",
                "path": str(cache.path),
                "scope": "all" if args.all else "expired",
                "removed": removed,
                **cache.stats(),
            }
    finally:
        cache.close()
    _emit(payload, getattr(args, "pretty", False))
    return 0


async def _serve_stdio(args: argparse.Namespace | None = None) -> None:
    from .mcp_server import build_server

    service = WebLens()
    profile = getattr(args, "profile", None) if args else None
    server = build_server(service, profile=profile)
    try:
        await server.run_stdio_async()
    finally:
        await service.close()


class _BearerAuth:
    """Minimal ASGI bearer check for the optional HTTP transport."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        if scope.get("path") in {"/", "/healthz"}:
            return await self.app(scope, receive, send)
        headers = {k.lower(): v for k, v in scope.get("headers") or []}
        supplied = headers.get(b"authorization", b"").decode("latin-1")
        import hmac

        if not hmac.compare_digest(supplied, f"Bearer {self.token}"):
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
        return await self.app(scope, receive, send)


class _SecurityHeaders:
    """Add browser hardening headers to every HTTP response."""

    _HEADERS = (
        (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
    )

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers") or [])
                present = {name.lower() for name, _ in headers}
                for name, value in self._HEADERS:
                    if name not in present:
                        headers.append((name, value))
                message = {**message, "headers": headers}
            await send(message)

        return await self.app(scope, receive, send_with_headers)


class _RateLimit:
    """Small in-process sliding-window limiter for the HTTP MCP transport.

    Cloud Run may run multiple instances, so this is a per-instance defense,
    not a replacement for an edge quota. It still stops a single client from
    exhausting a worker and makes the public endpoint fail closed with 429.
    """

    def __init__(self, app, *, limit: int = 120, window_s: float = 60.0):
        self.app = app
        self.limit = max(1, int(limit))
        self.window_s = float(window_s)
        self._hits: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        if scope.get("path") in {"/", "/healthz"}:
            return await self.app(scope, receive, send)

        headers = {k.lower(): v for k, v in scope.get("headers") or []}
        forwarded = [
            part.strip()
            for part in headers.get(b"x-forwarded-for", b"").decode("latin-1").split(",")
            if part.strip()
        ]
        client = scope.get("client") or ("unknown", 0)
        # Use the address appended by the closest trusted proxy. The left-most
        # value is client-controlled and would let a caller evade the limiter.
        key = forwarded[-1] if forwarded else str(client[0])
        now = time.monotonic()
        async with self._lock:
            bucket = self._hits.setdefault(key, deque())
            cutoff = now - self.window_s
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                retry_after = max(1, int(self.window_s - (now - bucket[0])) + 1)
                body = b'{"error":"rate_limited"}'
                await send(
                    {
                        "type": "http.response.start",
                        "status": 429,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                            (b"retry-after", str(retry_after).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
            bucket.append(now)

        return await self.app(scope, receive, send)


def _serve_http(args: argparse.Namespace) -> int:
    import uvicorn
    from starlette.responses import JSONResponse

    from .mcp_server import build_server

    settings = Settings()
    host = args.host or settings.http_host
    port = args.port or settings.http_port
    token = args.token or settings.http_token
    loopback = host in ("127.0.0.1", "localhost", "::1")
    if not loopback and not token and not args.allow_insecure:
        print(
            "refusing to bind a non-loopback address without a bearer token; "
            "pass --token or --allow-insecure",
            file=sys.stderr,
        )
        return 2

    transport_security = None
    if not loopback or args.allow_insecure:
        from mcp.server.transport_security import TransportSecuritySettings

        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
            allowed_hosts=["*"],
            allowed_origins=["*"],
        )

    service = WebLens(settings)
    # Stateful tools (Crawl2RAG, research chat) share one SQLite store. A
    # public, unauthenticated listener has no tenant identity, so exposing them
    # would let one caller read another caller's documents. Keep them available
    # on loopback or when the listener is authenticated.
    allow_stateful = loopback or bool(token)
    if not allow_stateful:
        print(
            "stateful tools disabled: non-loopback listener without a bearer token",
            file=sys.stderr,
        )
    server = build_server(service, profile=args.profile, allow_stateful=allow_stateful)
    app = server.streamable_http_app(
        stateless_http=not args.stateful,
        json_response=False,
        transport_security=transport_security,
        host=host,
    )

    async def _health(request):
        return JSONResponse({
            "status": "ok",
            "service": "weblens",
            "version": "0.1.0",
            "mcp_endpoint": "/mcp",
        })

    app.add_route("/", _health, methods=["GET"])
    app.add_route("/healthz", _health, methods=["GET"])

    if token:
        app.add_middleware(_BearerAuth, token=token)
    app.add_middleware(
        _RateLimit,
        limit=settings.http_rate_limit_per_minute,
    )
    app.add_middleware(_SecurityHeaders)

    async def run() -> None:
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level=(args.log_level or settings.log_level).lower(),
            access_log=False,
        )
        uv = uvicorn.Server(config)
        try:
            await uv.serve()
        finally:
            await service.close()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    return 0


async def _run_app(args: argparse.Namespace) -> int:
    service = WebLens()
    try:
        if args.app_name == "crawl2rag":
            from .apps.crawl2rag import Crawl2RAG
            kb = Crawl2RAG(service)
            if args.action == "ingest":
                payload = await kb.ingest(args.target, max_pages=args.max_pages)
            elif args.action == "query":
                payload = await kb.query(args.target, top_k=args.top_k)
            else:
                payload = kb.stats()
        elif args.app_name == "company":
            from .apps.company import CompanyResearcher
            comp = CompanyResearcher(service)
            payload = await comp.research_company(args.company)
        elif args.app_name == "market":
            from .apps.market import MarketResearcher
            mkt = MarketResearcher(service)
            if getattr(args, "portfolio", None):
                payload = await mkt.analyze_portfolio(args.portfolio)
            else:
                payload = await mkt.analyze_asset(args.asset, question=args.question)
        elif args.app_name == "chat":
            from .apps.chat import ResearchChatSession
            chat = ResearchChatSession(service)
            payload = await chat.send_message(args.message)
        elif args.app_name == "research-chat":
            from .apps.research_chat import PersistentResearchChat
            pchat = PersistentResearchChat(service, session_id=getattr(args, "session_id", None))
            msg = await pchat.send_query(args.message)
            payload = {
                "status": "ok",
                "session_id": pchat.session_id,
                "role": msg.role,
                "content": msg.content,
                "citations": msg.citations,
                "tokens_used": msg.tokens_used,
            }
        elif args.app_name == "meeting":
            from .apps.meeting import MeetingPrepAgent
            mtg = MeetingPrepAgent(service)
            payload = await mtg.prepare_brief(args.title, args.attendee, company_or_org=args.company)
        elif args.app_name == "sheets":
            from .apps.sheets import SheetsEnricher
            col_specs = {}
            for c in args.col:
                if "=" in c:
                    k, v = c.split("=", 1)
                    col_specs[k.strip()] = v.strip()
            enricher = SheetsEnricher(service)
            payload = await enricher.process_csv(args.input_csv, args.output_csv, col_specs)
        elif args.app_name == "tutorial":
            from .apps.tutorial_101 import run_tutorial
            payload = await run_tutorial(service, step=getattr(args, "step", "all"))
        else:
            payload = {"status": "error", "msg": f"unknown app {args.app_name}"}
    finally:
        await service.close()
    _emit(payload, getattr(args, "pretty", False))
    return 1 if payload.get("status") == "error" else 0


async def _schema_report() -> dict[str, Any]:
    from .mcp_server import build_server

    service = WebLens()
    profiles_data = {}
    try:
        for prof in ("core", "research", "full"):
            server = build_server(service, profile=prof)
            tools = await server.list_tools()
            per: dict[str, int] = {}
            dumped: list[dict[str, Any]] = []
            for tool in tools:
                item = tool.model_dump(by_alias=True, exclude_none=True)
                dumped.append(item)
                per[tool.name] = count_tokens(json.dumps(item, separators=(",", ":"), ensure_ascii=False))
            total = count_json_tokens(dumped)
            profiles_data[prof] = {
                "tools": per,
                "tool_count": len(tools),
                "total_tokens": total,
                "within_budget": total <= 1000 if prof == "core" else True,
            }
    finally:
        await service.close()

    core_data = profiles_data["core"]
    return {
        "status": "ok",
        "profile": "core",
        "tools": core_data["tools"],
        "total_tokens": core_data["total_tokens"],
        "tokenizer": "cl100k_base",
        "budget": 1000,
        "within_budget": core_data["within_budget"],
        "profiles": profiles_data,
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="weblens",
        description="Local-first web intelligence for AI agents (MCP).",
    )
    p.add_argument("--version", action="version", version=f"weblens {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("serve", help="run the MCP server (stdio by default)")
    s.add_argument("--profile", choices=["core", "research", "full"], default=None, help="tool profile")
    s.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    s.add_argument("--host", default=None)
    s.add_argument("--port", type=int, default=None)
    s.add_argument("--token", default=None, help="bearer token for HTTP")
    s.add_argument(
        "--stateful",
        action="store_true",
        help="keep MCP sessions for legacy HTTP clients that require Mcp-Session-Id",
    )
    s.add_argument("--allow-insecure", action="store_true", help="allow non-loopback without a token")
    s.add_argument("--log-level", default=None)

    q = sub.add_parser("search", help="search the live web")
    q.add_argument("query")
    q.add_argument("-k", "--max-results", type=int, default=5)
    q.add_argument("--freshness", choices=["day", "week", "month", "year"], default=None)
    q.add_argument("--domain", action="append", default=None)
    q.add_argument("--exclude-domain", action="append", default=None)
    q.add_argument("--max-tokens", type=int, default=None)
    q.add_argument("--pretty", action="store_true")

    e = sub.add_parser("extract", help="extract passages from one URL")
    e.add_argument("url")
    e.add_argument("-q", "--query", default=None)
    e.add_argument("--max-tokens", type=int, default=None)
    e.add_argument("--full", action="store_true")
    e.add_argument("--pretty", action="store_true")

    c = sub.add_parser("crawl", help="map or crawl a site")
    c.add_argument("url")
    c.add_argument("--mode", choices=["map", "crawl"], default="map")
    c.add_argument("--max-pages", type=int, default=10)
    c.add_argument("--max-depth", type=int, default=2)
    c.add_argument("-q", "--query", default=None)
    c.add_argument("--max-tokens", type=int, default=None)
    c.add_argument("--pretty", action="store_true")

    r = sub.add_parser("research", help="collect verbatim evidence from several sources")
    r.add_argument("query")
    r.add_argument("--max-tokens", type=int, default=None)
    r.add_argument("--pretty", action="store_true")

    d = sub.add_parser("doctor", help="show configuration, provider and cache status")
    d.add_argument("--live", action="store_true", help="run one live search")
    d.add_argument("--pretty", action="store_true")

    ca = sub.add_parser("cache", help="inspect or purge the local WebLens cache")
    cs = ca.add_subparsers(dest="cache_command", required=True)
    cst = cs.add_parser("stats", help="show cache size and hit counters")
    cst.add_argument("--pretty", action="store_true")
    cpu = cs.add_parser("purge", help="delete expired cache entries")
    cpu.add_argument(
        "--all",
        action="store_true",
        help="delete all entries, not only expired ones",
    )
    cpu.add_argument("--pretty", action="store_true")

    t = sub.add_parser("tokens", help="measure tools/list schema tokens")
    t.add_argument("--pretty", action="store_true")

    ap = sub.add_parser("app", help="execute a WebLens application")
    ap_sub = ap.add_subparsers(dest="app_name", required=True)

    # crawl2rag
    a_c2r = ap_sub.add_parser("crawl2rag", help="query or ingest into a local knowledge base")
    a_c2r.add_argument("action", choices=["ingest", "query", "stats"])
    a_c2r.add_argument("target", help="URL to ingest or question to query")
    a_c2r.add_argument("--max-pages", type=int, default=10)
    a_c2r.add_argument("--top-k", type=int, default=5)
    a_c2r.add_argument("--pretty", action="store_true")

    # company
    a_comp = ap_sub.add_parser("company", help="research a company profile")
    a_comp.add_argument("company", help="company name or domain")
    a_comp.add_argument("--pretty", action="store_true")

    # market
    a_mkt = ap_sub.add_parser("market", help="research asset filings and disclosures")
    a_mkt.add_argument("asset", nargs="?", default="", help="ticker or company name")
    a_mkt.add_argument("-q", "--question", default=None)
    a_mkt.add_argument("-p", "--portfolio", action="append", help="stock ticker for portfolio analysis")
    a_mkt.add_argument("--pretty", action="store_true")

    # chat
    a_chat = ap_sub.add_parser("chat", help="send a turn to the conversational research agent")
    a_chat.add_argument("message", help="user message")
    a_chat.add_argument("--pretty", action="store_true")

    # research-chat
    a_rc = ap_sub.add_parser("research-chat", help="send inquiry to persistent research chat session")
    a_rc.add_argument("message", help="user inquiry")
    a_rc.add_argument("--session-id", default=None, help="session id for multi-turn continuity")
    a_rc.add_argument("--pretty", action="store_true")

    # meeting
    a_mtg = ap_sub.add_parser("meeting", help="prepare a cited pre-meeting brief")
    a_mtg.add_argument("title", help="meeting title")
    a_mtg.add_argument("-a", "--attendee", action="append", required=True, help="attendee name")
    a_mtg.add_argument("-c", "--company", default=None, help="company name")
    a_mtg.add_argument("--pretty", action="store_true")

    # sheets
    a_sht = ap_sub.add_parser("sheets", help="enrich a CSV table with web evidence")
    a_sht.add_argument("input_csv", help="input CSV path")
    a_sht.add_argument("output_csv", help="output CSV path")
    a_sht.add_argument("--col", action="append", required=True, help="spec in format col_name=prompt")
    a_sht.add_argument("--pretty", action="store_true")

    # tutorial
    a_tut = ap_sub.add_parser("tutorial", help="run WebLens 101 tutorial walkthrough")
    a_tut.add_argument("--step", default="all", help="step to run")
    a_tut.add_argument("--pretty", action="store_true")

    return p


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    args = _build_parser().parse_args(argv)
    if args.command == "serve":
        if args.http:
            return _serve_http(args)
        asyncio.run(_serve_stdio(args))
        return 0
    if args.command == "cache":
        return asyncio.run(_run_cache(args))
    if args.command == "tokens":
        report = asyncio.run(_schema_report())
        _emit(report, args.pretty)
        return 0
    if args.command == "app":
        return asyncio.run(_run_app(args))
    return asyncio.run(_run_command(args))


if __name__ == "__main__":
    raise SystemExit(main())
