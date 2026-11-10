"""Command-line interface: serve MCP, call tools directly, measure schemas."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from . import __version__
from .config import Settings, get_settings
from .ratelimit import TenantRateLimiter, rate_limit_key, trusted_client_ip
from .service import WebLens
from .tenancy import ApiKeyRegistry, current_tenant
from .tokens import count_json_tokens, count_tokens


def _configure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
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
        return await service.extract(args.url, query=args.query, max_tokens=args.max_tokens, full=args.full)
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
    if args.command == "synthesize":
        return await service.synthesize(
            args.query,
            max_tokens=args.max_tokens,
            max_hops=args.max_hops,
        )
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
    from .cache import build_cache

    cache = build_cache(Settings())
    try:
        stats_fn = getattr(cache, "stats_async", None)
        stats = await stats_fn() if stats_fn is not None else cache.stats()
        path = str(cache.path) if hasattr(cache, "path") else None
        if args.cache_command == "stats":
            payload: dict[str, Any] = {
                "status": "ok",
                "path": path,
                **stats,
            }
        else:
            removed = await (cache.clear() if args.all else cache.purge())
            stats_fn = getattr(cache, "stats_async", None)
            stats = await stats_fn() if stats_fn is not None else cache.stats()
            payload = {
                "status": "ok",
                "path": path,
                "scope": "all" if args.all else "expired",
                "removed": removed,
                **stats,
            }
    finally:
        aclose = getattr(cache, "aclose", None)
        if aclose is not None:
            await aclose()
        else:
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


class _ApiKeyAuth:
    """ASGI bearer / X-API-Key check that binds a tenant to the request.

    Only this middleware turns a secret into an identity. Tool handlers read
    the identity from ``current_tenant`` and never accept a tenant id from the
    caller.
    """

    PUBLIC_PATHS = frozenset({"/", "/healthz"})

    def __init__(
        self,
        app,
        registry: ApiKeyRegistry,
        *,
        failure_limit: int = 60,
        max_failure_buckets: int = 10_000,
        trust_proxy_headers: bool = False,
    ):
        self.app = app
        self.registry = registry
        self.trust_proxy_headers = trust_proxy_headers
        # Authenticated requests are metered by the tenant limiter downstream.
        # Failed attempts never reach it, so they get a separate IP-scoped
        # budget. Without this, a flood of bad keys would bypass backpressure.
        self.failures = TenantRateLimiter(
            failure_limit,
            window_s=60.0,
            max_buckets=max_failure_buckets,
        )

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        if scope.get("path") in self.PUBLIC_PATHS:
            return await self.app(scope, receive, send)

        state = scope.get("state")
        if isinstance(state, dict):
            state["settings"] = state.get("settings") or get_settings()
        else:
            state = {"settings": get_settings()}
            scope["state"] = state
        state["settings"].trust_proxy_headers = self.trust_proxy_headers

        headers = {k.lower(): v for k, v in scope.get("headers") or []}
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        api_key = headers.get(b"x-api-key", b"").decode("latin-1")
        tenant = self.registry.authenticate_header(authorization, api_key)
        if tenant is None:
            decision = self.failures.check(f"ip:{trusted_client_ip(scope)}")
            if not decision.allowed:
                body = b'{"error":"rate_limited"}'
                await send(
                    {
                        "type": "http.response.start",
                        "status": 429,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                            (b"retry-after", str(decision.retry_after).encode()),
                            (b"x-ratelimit-limit", str(decision.limit).encode()),
                            (b"x-ratelimit-remaining", str(decision.remaining).encode()),
                            (b"x-ratelimit-reset", str(decision.reset_after).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
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

        state["tenant_id"] = tenant
        token = current_tenant.set(tenant)
        try:
            return await self.app(scope, receive, send)
        finally:
            current_tenant.reset(token)


class _BearerAuth:
    """Backward-compatible single-token wrapper around :class:`_ApiKeyAuth`."""

    def __init__(self, app, token: str):
        self.app = _ApiKeyAuth(app, ApiKeyRegistry({"default": token}))

    async def __call__(self, scope, receive, send):
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
    """Per-tenant (or per-address) token-bucket limiter for the HTTP MCP transport.

    Cloud Run may run multiple instances, so this is a per-instance defense,
    not a replacement for an edge quota. It still stops a single client from
    exhausting a worker and makes the public endpoint fail closed with 429.
    """

    def __init__(
        self,
        app,
        *,
        limit: int = 120,
        window_s: float = 60.0,
        tenant_limits: dict[str, int] | None = None,
        max_buckets: int = 10_000,
        trust_proxy_headers: bool = False,
    ):
        self.app = app
        self.trust_proxy_headers = trust_proxy_headers
        self.limiter = TenantRateLimiter(
            limit,
            window_s=window_s,
            per_tenant=tenant_limits,
            max_buckets=max_buckets,
        )

    @staticmethod
    def _headers(decision) -> list[tuple[bytes, bytes]]:
        return [
            (b"x-ratelimit-limit", str(decision.limit).encode()),
            (b"x-ratelimit-remaining", str(decision.remaining).encode()),
            (b"x-ratelimit-reset", str(decision.reset_after).encode()),
        ]

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        if scope.get("path") in {"/", "/healthz"}:
            return await self.app(scope, receive, send)

        state = scope.get("state")
        if isinstance(state, dict):
            state["settings"] = state.get("settings") or get_settings()
        else:
            state = {"settings": get_settings()}
            scope["state"] = state
        state["settings"].trust_proxy_headers = self.trust_proxy_headers

        decision = self.limiter.check(rate_limit_key(scope))
        headers = self._headers(decision)
        if not decision.allowed:
            body = b'{"error":"rate_limited"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        (b"retry-after", str(decision.retry_after).encode()),
                        *headers,
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        async def send_with_headers(message):
            if message.get("type") == "http.response.start":
                existing = list(message.get("headers") or [])
                existing.extend(headers)
                message = {**message, "headers": existing}
            await send(message)

        return await self.app(scope, receive, send_with_headers)


def _serve_http(args: argparse.Namespace) -> int:
    import uvicorn
    from starlette.responses import JSONResponse

    from .mcp_server import build_server

    settings = Settings()
    host = args.host or settings.http_host
    port = args.port or settings.http_port
    token = args.token if args.token is not None else settings.http_token
    keys = dict(settings.api_key_map)
    if token:
        keys["default"] = token
    try:
        registry = ApiKeyRegistry(keys)
    except ValueError as exc:
        print(f"invalid API key configuration: {exc}", file=sys.stderr)
        return 2
    loopback = host in ("127.0.0.1", "localhost", "::1")
    if not loopback and not registry and not args.allow_insecure:
        print(
            "refusing to bind a non-loopback address without an API key or bearer token; "
            "pass --token, set WEBLENS_API_KEYS, or --allow-insecure",
            file=sys.stderr,
        )
        return 2

    transport_security = (
        _transport_security_settings(settings) if settings.allowed_hosts or settings.allowed_origins else None
    )

    service = WebLens(settings)
    # Stateful tools (Crawl2RAG, research chat) resolve a per-tenant SQLite
    # path from the authenticated identity. An unauthenticated public listener
    # has no identity, so keep those tools unavailable there.
    allow_stateful = loopback or bool(registry)
    if not allow_stateful:
        print(
            "stateful tools disabled: non-loopback listener without an API key",
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
        return JSONResponse(
            {
                "status": "ok",
                "service": "weblens",
                "version": "0.1.0",
                "mcp_endpoint": "/mcp",
            }
        )

    app.add_route("/", _health, methods=["GET"])
    app.add_route("/healthz", _health, methods=["GET"])

    # add_middleware inserts at the front and Starlette builds in reverse, so
    # the last added middleware is outermost. Auth must run before the limiter
    # so the limiter can key on the authenticated tenant rather than only an IP.
    app.add_middleware(
        _RateLimit,
        limit=settings.http_rate_limit_per_minute,
        tenant_limits=settings.tenant_rate_limit_map,
        trust_proxy_headers=settings.trust_proxy_headers,
    )
    if registry:
        app.add_middleware(
            _ApiKeyAuth,
            registry=registry,
            failure_limit=settings.http_auth_failure_limit_per_minute,
            trust_proxy_headers=settings.trust_proxy_headers,
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

    sy = sub.add_parser(
        "synthesize",
        help="test hypotheses and resolve contradictions from verbatim evidence",
    )
    sy.add_argument("query")
    sy.add_argument("--max-tokens", type=int, default=None)
    sy.add_argument("--max-hops", type=int, choices=[1, 2, 3], default=2)
    sy.add_argument("--pretty", action="store_true")

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


def _transport_security_settings(settings: Settings):
    """Build MCP TransportSecuritySettings from configured allowed hosts/origins."""
    hosts = [h.strip() for h in settings.allowed_hosts.split(",") if h.strip()]
    origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
    if not hosts and not origins:
        # Let the MCP transport apply its own defaults rather than enabling
        # DNS-rebinding protection with an empty allowlist.
        return None

    from mcp.server.transport_security import TransportSecuritySettings

    if "*" in hosts:
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
            allowed_hosts=["*"],
            allowed_origins=["*"],
        )

    # The MCP transport matches the Host header EXACTLY, or against an explicit
    # "host:*" pattern. A bare entry such as "127.0.0.1" therefore never matches
    # the real header "127.0.0.1:8765", so the documented default rejected every
    # legitimate client with 421. Operators then "fixed" it with "*", which turns
    # DNS-rebinding protection off entirely. Expanding each entry to also allow
    # any port keeps the protection on and makes the default usable as written.
    expanded: list[str] = []
    for host in hosts:
        expanded.append(host)
        # Already port-scoped, already a wildcard, or an IPv6 literal in brackets.
        if host.endswith(":*") or host == "*":
            continue
        expanded.append(f"{host}:*")
        # Also accept the bracket-less IPv6 spelling clients sometimes send.
        if host.startswith("[") and host.endswith("]"):
            expanded.append(f"{host[1:-1]}:*")

    # De-duplicate while preserving order.
    seen: set[str] = set()
    allowed_hosts = [h for h in expanded if not (h in seen or seen.add(h))]

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=origins,
    )


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
