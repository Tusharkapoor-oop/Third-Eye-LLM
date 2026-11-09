from __future__ import annotations

import argparse

from weblens.cli import (
    _ApiKeyAuth,
    _BearerAuth,
    _RateLimit,
    _SecurityHeaders,
    _serve_http,
)
from weblens.tenancy import ApiKeyRegistry, current_tenant


class DummyApp:
    def __init__(self):
        self.calls = 0

    async def __call__(self, scope, receive, send):
        self.calls += 1
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


class TenantApp:
    def __init__(self):
        self.scope_tenant = None
        self.context_tenant = None

    async def __call__(self, scope, receive, send):
        state = scope.get("state") or {}
        self.scope_tenant = state.get("tenant_id")
        self.context_tenant = current_tenant.get()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def _invoke(
    app,
    headers,
    scope_type="http",
    path="",
    client=("127.0.0.1", 1234),
    state=None,
):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": scope_type,
        "headers": headers,
        "path": path,
        "client": client,
        "state": state or {},
    }
    await app(scope, receive, send)
    return messages


async def test_bearer_middleware_rejects_missing_and_wrong_tokens():
    inner = DummyApp()
    app = _BearerAuth(inner, "secret-token")

    for headers in ([], [(b"authorization", b"Bearer wrong")]):
        messages = await _invoke(app, headers)
        assert messages[0]["status"] == 401
        assert messages[1]["body"] == b'{"error":"unauthorized"}'
        assert any(name == b"www-authenticate" for name, _ in messages[0]["headers"])
    assert inner.calls == 0


async def test_bearer_middleware_accepts_exact_token():
    inner = DummyApp()
    app = _BearerAuth(inner, "secret-token")
    messages = await _invoke(app, [(b"authorization", b"Bearer secret-token")])
    assert messages[0]["status"] == 200
    assert inner.calls == 1


async def test_bearer_middleware_ignores_non_http_scopes():
    inner = DummyApp()
    app = _BearerAuth(inner, "secret-token")
    await _invoke(app, [], scope_type="lifespan")
    assert inner.calls == 1


async def test_bearer_middleware_allows_public_health_checks():
    inner = DummyApp()
    app = _BearerAuth(inner, "secret-token")
    messages = await _invoke(app, [], path="/healthz")
    assert messages[0]["status"] == 200
    assert inner.calls == 1


async def test_api_key_auth_binds_tenant_and_resets_context():
    registry = ApiKeyRegistry({"acme": "12345678", "beta": "abcdefgh"})
    inner = TenantApp()
    app = _ApiKeyAuth(inner, registry)

    messages = await _invoke(app, [(b"authorization", b"Bearer abcdefgh")])
    assert messages[0]["status"] == 200
    assert inner.scope_tenant == "beta"
    assert inner.context_tenant == "beta"
    assert current_tenant.get() == "default"

    messages = await _invoke(app, [(b"x-api-key", b"12345678")])
    assert messages[0]["status"] == 200
    assert inner.scope_tenant == "acme"


async def test_api_key_auth_rejects_unknown_keys_and_keeps_health_public():
    inner = DummyApp()
    app = _ApiKeyAuth(inner, ApiKeyRegistry({"acme": "12345678"}))
    messages = await _invoke(app, [(b"authorization", b"Bearer nope")])
    assert messages[0]["status"] == 401
    assert inner.calls == 0
    messages = await _invoke(app, [], path="/healthz")
    assert messages[0]["status"] == 200
    assert inner.calls == 1


async def test_api_key_auth_rate_limits_repeated_failures():
    app = _ApiKeyAuth(
        DummyApp(),
        ApiKeyRegistry({"acme": "12345678"}),
        failure_limit=1,
    )
    first = await _invoke(app, [(b"authorization", b"Bearer wrong")])
    second = await _invoke(app, [(b"authorization", b"Bearer wrong")])
    assert first[0]["status"] == 401
    assert second[0]["status"] == 429
    headers = dict(second[0]["headers"])
    assert int(headers[b"retry-after"]) >= 1
    assert headers[b"x-ratelimit-limit"] == b"1"


async def test_rate_limit_is_per_tenant_and_emits_headers():
    app = _RateLimit(
        DummyApp(),
        limit=10,
        window_s=60,
        tenant_limits={"acme": 1, "beta": 2},
    )
    acme = await _invoke(app, [], state={"tenant_id": "acme"})
    assert acme[0]["status"] == 200
    assert dict(acme[0]["headers"])[b"x-ratelimit-limit"] == b"1"
    assert (await _invoke(app, [], state={"tenant_id": "acme"}))[0]["status"] == 429

    assert (await _invoke(app, [], state={"tenant_id": "beta"}))[0]["status"] == 200
    assert (await _invoke(app, [], state={"tenant_id": "beta"}))[0]["status"] == 200
    assert (await _invoke(app, [], state={"tenant_id": "beta"}))[0]["status"] == 429


async def test_rate_limit_ignores_ip_when_tenant_is_authenticated():
    app = _RateLimit(DummyApp(), limit=1, window_s=60)
    first = await _invoke(
        app,
        [(b"x-forwarded-for", b"203.0.113.7")],
        state={"tenant_id": "acme"},
    )
    second = await _invoke(
        app,
        [(b"x-forwarded-for", b"198.51.100.9")],
        state={"tenant_id": "acme"},
    )
    assert first[0]["status"] == 200
    assert second[0]["status"] == 429


async def test_security_headers_are_added_to_responses():
    messages = await _invoke(_SecurityHeaders(DummyApp()), [])
    headers = dict(messages[0]["headers"])
    assert headers[b"strict-transport-security"].startswith(b"max-age=")
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert headers[b"x-frame-options"] == b"DENY"


async def test_rate_limit_returns_429_after_burst():
    inner = DummyApp()
    app = _RateLimit(inner, limit=2, window_s=60)
    first = await _invoke(app, [])
    second = await _invoke(app, [])
    third = await _invoke(app, [])
    assert first[0]["status"] == 200
    assert second[0]["status"] == 200
    assert third[0]["status"] == 429
    assert inner.calls == 2
    assert any(name == b"retry-after" for name, _ in third[0]["headers"])


async def test_rate_limit_uses_the_trusted_forwarded_address():
    inner = DummyApp()
    app = _RateLimit(inner, limit=1, window_s=60)
    first = await _invoke(app, [(b"x-forwarded-for", b"spoofed-one, 203.0.113.7")])
    second = await _invoke(app, [(b"x-forwarded-for", b"spoofed-two, 203.0.113.7")])
    assert first[0]["status"] == 200
    assert second[0]["status"] == 429
    assert inner.calls == 1


def test_non_loopback_http_refuses_without_token(capsys):
    args = argparse.Namespace(
        host="0.0.0.0",
        port=8765,
        token=None,
        allow_insecure=False,
        stateless=False,
    )
    assert _serve_http(args) == 2
    err = capsys.readouterr().err
    assert "refusing to bind" in err
    assert "--token" in err
