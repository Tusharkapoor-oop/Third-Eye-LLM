from __future__ import annotations

import argparse

from weblens.cli import _BearerAuth, _RateLimit, _SecurityHeaders, _serve_http


class DummyApp:
    def __init__(self):
        self.calls = 0

    async def __call__(self, scope, receive, send):
        self.calls += 1
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def _invoke(app, headers, scope_type="http", path="", client=("127.0.0.1", 1234)):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {"type": scope_type, "headers": headers, "path": path, "client": client}
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
    first = await _invoke(
        app, [(b"x-forwarded-for", b"spoofed-one, 203.0.113.7")]
    )
    second = await _invoke(
        app, [(b"x-forwarded-for", b"spoofed-two, 203.0.113.7")]
    )
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
