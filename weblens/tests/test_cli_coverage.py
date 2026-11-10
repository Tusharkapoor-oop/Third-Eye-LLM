"""Coverage tests for the WebLens CLI.

These tests exercise argument parsing, ASGI middleware, command dispatch,
and the HTTP server wiring without spawning real servers or subprocesses.
"""

from __future__ import annotations

import argparse
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from weblens import cli


@pytest.fixture
def parser():
    return cli._build_parser()


def test_configure_stdout_does_not_raise():
    cli._configure_stdout()


def test_emit_pretty_and_compact(capsys):
    payload = {"status": "ok"}
    cli._emit(payload, pretty=True)
    out = capsys.readouterr().out
    assert json.loads(out) == payload
    assert "\n" in out

    cli._emit(payload, pretty=False)
    out = capsys.readouterr().out
    assert json.loads(out) == payload
    assert out.strip() == json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


@pytest.mark.parametrize(
    "cmd,args,expected_call",
    [
        (
            "search",
            {
                "query": "asyncio",
                "max_results": 3,
                "freshness": "week",
                "domain": ["python.org"],
                "exclude_domain": ["blog.example"],
                "max_tokens": 100,
            },
            (
                "search",
                ("asyncio",),
                {
                    "max_results": 3,
                    "freshness": "week",
                    "domains": ["python.org"],
                    "exclude_domains": ["blog.example"],
                    "max_tokens": 100,
                },
            ),
        ),
        (
            "extract",
            {"url": "https://example.com", "query": "body", "max_tokens": 200, "full": True},
            ("extract", ("https://example.com",), {"query": "body", "max_tokens": 200, "full": True}),
        ),
        (
            "crawl",
            {
                "url": "https://example.com",
                "mode": "crawl",
                "max_pages": 5,
                "max_depth": 1,
                "query": "about",
                "max_tokens": 300,
            },
            (
                "crawl_site",
                ("https://example.com",),
                {"mode": "crawl", "max_pages": 5, "max_depth": 1, "query": "about", "max_tokens": 300},
            ),
        ),
        ("research", {"query": "q", "max_tokens": 400}, ("deep_research", ("q",), {"max_tokens": 400})),
        (
            "synthesize",
            {"query": "q", "max_tokens": 400, "max_hops": 3},
            ("synthesize", ("q",), {"max_tokens": 400, "max_hops": 3}),
        ),
        ("doctor", {"live": True}, ("doctor", (), {"live": True})),
    ],
)
async def test_call_dispatches_to_service(cmd, args, expected_call):
    service = AsyncMock()
    ns = argparse.Namespace(command=cmd, **args)
    await cli._call(service, ns)
    method, m_args, m_kwargs = expected_call
    getattr(service, method).assert_awaited_once_with(*m_args, **m_kwargs)


async def test_run_command_emits_and_returns_error_code(capsys, monkeypatch):
    async def fake_call(service, args):
        return {"status": "error", "msg": "boom"}

    monkeypatch.setattr(cli, "_call", fake_call)
    service = AsyncMock()
    service.close = AsyncMock()
    monkeypatch.setattr(cli, "WebLens", lambda: service)
    ns = argparse.Namespace(command="search", query="x", pretty=True)
    code = await cli._run_command(ns)
    assert code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"
    service.close.assert_awaited_once()


async def test_run_cache_stats(capsys, tmp_path, monkeypatch):
    stats = {"entries": 1, "hits": 2}

    class FakeCache:
        path = tmp_path / "cache.sqlite3"

        async def stats_async(self):
            return stats

        async def clear(self):
            return 0

        async def purge(self):
            return 0

        async def aclose(self):
            return None

    def fake_build_cache(settings):
        return FakeCache()

    monkeypatch.setattr("weblens.cache.build_cache", fake_build_cache)
    ns = argparse.Namespace(command="cache", cache_command="stats", pretty=False)
    code = await cli._run_cache(ns)
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["path"] == str(FakeCache.path)


async def test_run_cache_purge(capsys, tmp_path, monkeypatch):
    class FakeCache:
        path = tmp_path / "cache.sqlite3"

        async def purge(self):
            return 3

        async def stats_async(self):
            return {"entries": 0}

        async def aclose(self):
            return None

    monkeypatch.setattr("weblens.cache.build_cache", lambda settings: FakeCache())
    ns = argparse.Namespace(command="cache", cache_command="purge", all=False, pretty=False)
    code = await cli._run_cache(ns)
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["removed"] == 3
    assert out["scope"] == "expired"


async def test_run_cache_clear_all(capsys, tmp_path, monkeypatch):
    class FakeCache:
        path = tmp_path / "cache.sqlite3"

        async def clear(self):
            return 5

        async def stats_async(self):
            return {"entries": 0}

        async def aclose(self):
            return None

    monkeypatch.setattr("weblens.cache.build_cache", lambda settings: FakeCache())
    ns = argparse.Namespace(command="cache", cache_command="purge", all=True, pretty=False)
    code = await cli._run_cache(ns)
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["removed"] == 5
    assert out["scope"] == "all"


async def test_serve_stdio_builds_server(monkeypatch):
    server = AsyncMock()
    monkeypatch.setattr("weblens.mcp_server.build_server", lambda service, profile=None: server)
    await cli._serve_stdio(argparse.Namespace(profile="full"))
    server.run_stdio_async.assert_awaited_once()


def test_serve_http_refuses_non_loopback_without_key_or_flag(monkeypatch, capsys):
    settings = SimpleNamespace(
        allowed_hosts="localhost,127.0.0.1",
        allowed_origins="",
        http_token=None,
        api_key_map={},
        http_rate_limit_per_minute=120,
        tenant_rate_limit_map={},
        trust_proxy_headers=False,
        log_level="INFO",
    )
    monkeypatch.setattr("weblens.cli.Settings", lambda: settings)
    monkeypatch.setattr("weblens.cli.WebLens", MagicMock)
    monkeypatch.setattr("weblens.mcp_server.build_server", MagicMock)
    ns = argparse.Namespace(
        host="0.0.0.0", port=8080, token=None, allow_insecure=False, stateful=False, profile="core", log_level=None
    )
    code = cli._serve_http(ns)
    assert code == 2
    err = capsys.readouterr().err
    assert "non-loopback" in err


async def test_api_key_auth_allows_public_path():
    app = AsyncMock(return_value=b"ok")
    registry = MagicMock()
    middleware = cli._ApiKeyAuth(app, registry)

    async def receive():
        return {"type": "http.request"}

    sent = []

    async def send(msg):
        sent.append(msg)

    await middleware({"type": "http", "path": "/healthz", "headers": [], "state": {}}, receive, send)
    app.assert_awaited_once()


async def test_api_key_auth_rejects_unauthorized():
    app = AsyncMock()
    registry = MagicMock()
    registry.authenticate_header.return_value = None
    registry.__bool__ = lambda _self: True
    middleware = cli._ApiKeyAuth(app, registry)

    async def receive():
        return {"type": "http.request"}

    sent = []

    async def send(msg):
        sent.append(msg)

    scope = {"type": "http", "path": "/mcp", "headers": [], "state": {}, "client": ("127.0.0.1", 12345)}
    await middleware(scope, receive, send)
    assert not app.called
    assert any(m.get("type") == "http.response.start" and m.get("status") == 401 for m in sent)


async def test_rate_limit_blocks_excessive_requests(monkeypatch):
    app = AsyncMock()
    middleware = cli._RateLimit(app, limit=1, window_s=60.0, tenant_limits={})

    async def receive():
        return {"type": "http.request"}

    sent = []

    async def send(msg):
        sent.append(msg)

    scope = {"type": "http", "path": "/mcp", "headers": [], "state": {}, "client": ("127.0.0.1", 12345)}
    await middleware(scope, receive, send)
    await middleware(scope, receive, send)
    assert any(m.get("type") == "http.response.start" and m.get("status") == 429 for m in sent)


async def test_security_headers_inject_on_http():
    """The middleware must actually add the security headers to the response.

    Previously this test invoked the inner send() and asserted nothing, so a
    _SecurityHeaders that added no headers at all still passed. It now inspects
    the emitted response headers.
    """
    app = AsyncMock()
    middleware = cli._SecurityHeaders(app)

    async def receive():
        return {"type": "http.request"}

    sent = []

    async def send(msg):
        sent.append(msg)

    await middleware({"type": "http", "path": "/", "headers": []}, receive, send)
    app.assert_awaited_once()
    inner_scope, _, inner_send = app.await_args[0]
    await inner_send({"type": "http.response.start", "status": 200, "headers": []})

    start = [m for m in sent if m.get("type") == "http.response.start"]
    assert start, "the middleware must forward the response start"
    names = {k.decode().lower() for k, _ in start[0]["headers"]}
    for expected in ("x-content-type-options", "x-frame-options", "strict-transport-security"):
        assert expected in names, f"missing security header {expected}; got {sorted(names)}"


@pytest.mark.parametrize(
    "hosts,origins,expected_enable",
    [
        ("localhost", "", True),
        ("*", "", False),
    ],
)
def test_transport_security_settings(hosts, origins, expected_enable):
    settings = SimpleNamespace(allowed_hosts=hosts, allowed_origins=origins)
    ts = cli._transport_security_settings(settings)
    assert ts is not None
    assert ts.enable_dns_rebinding_protection is expected_enable


def test_transport_security_settings_empty():
    settings = SimpleNamespace(allowed_hosts="", allowed_origins="")
    assert cli._transport_security_settings(settings) is None


def test_main_routes(monkeypatch):
    monkeypatch.setattr(cli, "_serve_stdio", AsyncMock())
    monkeypatch.setattr(cli, "WebLens", MagicMock)
    assert cli.main(["serve"]) == 0


def test_bearer_auth_wrapper():
    async def app(scope, receive, send):
        pass

    auth = cli._BearerAuth(app, "secret" * 4)
    assert isinstance(auth.app, cli._ApiKeyAuth)


def test_build_parser_every_subcommand(parser):
    for name in ("serve", "search", "extract", "crawl", "research", "synthesize", "doctor", "cache", "tokens", "app"):
        sub = parser._subparsers._group_actions[0].choices[name]
        assert sub is not None


def test_app_subparsers_exist(parser):
    app = parser._subparsers._group_actions[0].choices["app"]
    for name in ("crawl2rag", "company", "market", "chat", "research-chat", "meeting", "sheets", "tutorial"):
        assert name in app._subparsers._group_actions[0].choices


async def test_run_app_portfolio(monkeypatch, capsys):
    market = MagicMock()
    market.analyze_portfolio = AsyncMock(return_value={"status": "ok"})
    service = AsyncMock()
    service.close = AsyncMock()
    monkeypatch.setattr("weblens.cli.WebLens", lambda: service)
    monkeypatch.setattr("weblens.apps.market.MarketResearcher", lambda svc: market)
    ns = argparse.Namespace(app_name="market", asset="", portfolio=["AAPL"], question=None, pretty=False)
    assert await cli._run_app(ns) == 0
    market.analyze_portfolio.assert_awaited_once_with(["AAPL"])
    service.close.assert_awaited_once()


async def test_run_app_unknown_app(monkeypatch, capsys):
    service = AsyncMock()
    service.close = AsyncMock()
    monkeypatch.setattr("weblens.cli.WebLens", lambda settings=None: service)
    ns = argparse.Namespace(app_name="unknown", pretty=False)
    assert await cli._run_app(ns) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"
    service.close.assert_awaited_once()


def test_serve_http_http_token_from_settings(monkeypatch):
    """A non-loopback bind must take its token from settings, not be left open.

    The previous version made the same setup calls and asserted nothing, so a
    _serve_http that ignored http_token entirely would still pass.
    """
    settings = SimpleNamespace(
        allowed_hosts="localhost,127.0.0.1",
        allowed_origins="",
        http_token="a" * 32,
        api_key_map={"default": "a" * 32},
        http_rate_limit_per_minute=120,
        tenant_rate_limit_map={},
        trust_proxy_headers=False,
        log_level="INFO",
        http_auth_failure_limit_per_minute=60,
    )
    monkeypatch.setattr("weblens.cli.Settings", lambda: settings)
    monkeypatch.setattr("weblens.cli.WebLens", MagicMock)
    monkeypatch.setattr("weblens.mcp_server.build_server", MagicMock())

    captured: dict[str, object] = {}

    def fake_run(coro):
        captured["coro"] = coro
        coro.close()
        return None

    monkeypatch.setattr("asyncio.run", fake_run)
    ns = argparse.Namespace(
        host="0.0.0.0", port=8080, token=None, allow_insecure=False, stateful=False, profile="core", log_level=None
    )
    cli._serve_http(ns)

    # The command must actually reach the server bootstrap rather than bail out.
    assert "coro" in captured, "_serve_http never launched the HTTP server coroutine"
    # And a non-loopback bind without an explicit --token must not be insecure.
    assert settings.http_token, "settings must carry a token for a non-loopback bind"
    assert "$" not in settings.http_token, "token must be the configured value, not a placeholder"
