"""Command-line interface: serve MCP, call tools directly, measure schemas."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
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


async def _serve_stdio() -> None:
    from .mcp_server import build_server

    service = WebLens()
    server = build_server(service)
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


def _serve_http(args: argparse.Namespace) -> int:
    import uvicorn

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
    service = WebLens(settings)
    server = build_server(service)
    app = server.streamable_http_app(
        stateless_http=not args.stateful,
        json_response=False,
    )
    if token:
        app.add_middleware(_BearerAuth, token=token)

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


async def _schema_report() -> dict[str, Any]:
    from .mcp_server import build_server

    service = WebLens()
    try:
        server = build_server(service)
        tools = await server.list_tools()
    finally:
        await service.close()
    per: dict[str, int] = {}
    dumped: list[dict[str, Any]] = []
    for tool in tools:
        item = tool.model_dump(by_alias=True, exclude_none=True)
        dumped.append(item)
        per[tool.name] = count_tokens(json.dumps(item, separators=(",", ":"), ensure_ascii=False))
    total = count_json_tokens(dumped)
    return {
        "status": "ok",
        "tools": per,
        "total_tokens": total,
        "tokenizer": "cl100k_base",
        "budget": 1000,
        "within_budget": total <= 1000,
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="weblens",
        description="Local-first web intelligence for AI agents (MCP).",
    )
    p.add_argument("--version", action="version", version=f"weblens {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("serve", help="run the MCP server (stdio by default)")
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

    t = sub.add_parser("tokens", help="measure tools/list schema tokens")
    t.add_argument("--pretty", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    args = _build_parser().parse_args(argv)
    if args.command == "serve":
        if args.http:
            return _serve_http(args)
        asyncio.run(_serve_stdio())
        return 0
    if args.command == "tokens":
        report = asyncio.run(_schema_report())
        _emit(report, args.pretty)
        return 0
    return asyncio.run(_run_command(args))


if __name__ == "__main__":
    raise SystemExit(main())
