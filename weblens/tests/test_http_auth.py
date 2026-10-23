from __future__ import annotations

import argparse

from weblens.cli import _BearerAuth, _serve_http


class DummyApp:
    def __init__(self):
        self.calls = 0

    async def __call__(self, scope, receive, send):
        self.calls += 1
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def _invoke(app, headers, scope_type="http"):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {"type": scope_type, "headers": headers}
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
