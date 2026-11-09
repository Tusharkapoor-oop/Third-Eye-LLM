"""Regression guards for the 2026-11-09 hardening pass.

Covers:
- Tier-2 Playwright extraction refuses private/metadata/file targets before launch.
- safe_fetch_url connects to the validated IP while preserving Host and TLS identity.
- The Streamable HTTP transport rejects unauthenticated requests.
- Non-loopback binds cannot start without a configured token.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from security import SecurityValidationError, safe_fetch_url


@pytest.mark.asyncio
async def test_tier2_rejects_private_targets_before_browser_launch(monkeypatch):
    """Advanced search must not hand loopback/metadata/file URLs to Chromium."""
    from extractor import TieredExtractor

    extractor = object.__new__(TieredExtractor)

    async def _must_not_launch():
        raise AssertionError("browser launched for a forbidden target")

    monkeypatch.setattr(extractor, "_get_browser", _must_not_launch, raising=False)

    forbidden = [
        "http://127.0.0.1:9999/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/internal",
        "file:///C:/Windows/win.ini",
        "gopher://127.0.0.1:70/",
    ]
    for url in forbidden:
        with pytest.raises(SecurityValidationError):
            await extractor._extract_tier2_playwright(url)


@pytest.mark.asyncio
async def test_safe_fetch_url_pins_resolved_ip(monkeypatch):
    """The socket target is the validated IP; Host carries the public hostname."""
    monkeypatch.setattr("security.resolve_and_verify_host", lambda host, port: "93.184.216.34")

    with respx.mock(assert_all_called=False) as router:
        route = router.get("http://93.184.216.34/").mock(
            return_value=httpx.Response(200, text="pinned-ok")
        )
        status, _headers, body = await safe_fetch_url("http://example.com/")

    assert status == 200
    assert body == b"pinned-ok"
    request = route.calls[0].request
    assert request.headers["host"] == "example.com"


@pytest.mark.asyncio
async def test_http_bearer_guard_enforces_token():
    """HTTP transport returns 401 without the exact bearer token."""
    from server import _bearer_token_guard

    accepted: list[dict] = []

    async def inner(scope, receive, send):
        accepted.append(scope)

    async def receive():
        return {"type": "http.request"}

    async def call(headers):
        sent: list[dict] = []

        async def send(message):
            sent.append(message)

        guard = _bearer_token_guard(inner, "s3cret")
        await guard({"type": "http", "headers": headers}, receive, send)
        return sent

    assert (await call([]))[0]["status"] == 401
    assert (await call([(b"authorization", b"Bearer nope")]))[0]["status"] == 401
    await call([(b"authorization", b"Bearer s3cret")])
    assert len(accepted) == 1


def test_remote_bind_requires_authentication():
    """Only genuinely loopback addresses may bind the HTTP transport token-free."""
    from server import _is_loopback_host, _require_token_for_bind

    for host in ("127.0.0.1", "::1", "[::1]", "localhost", "0:0:0:0:0:0:0:1"):
        assert _is_loopback_host(host) is True, host
    for host in ("0.0.0.0", "10.0.0.4", "192.168.1.10", "example.com", ""):
        assert _is_loopback_host(host) is False, host

    _require_token_for_bind("127.0.0.1", "")
    _require_token_for_bind("0.0.0.0", "a-token")
    with pytest.raises(SystemExit):
        _require_token_for_bind("0.0.0.0", "")
