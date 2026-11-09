"""Extra coverage tests for SafeFetcher.

Uses respx to mock httpx calls and covers: stale-while-error, redirect limits,
non-2xx handling, byte caps, HEAD requests, encoding paths, cached hits, and
upstream failure fallback.
"""

from __future__ import annotations

import pytest
from httpx import Response

from weblens.cache import Cache
from weblens.config import Settings
from weblens.errors import BlockedURLError, ErrCode, FetchError
from weblens.net.client import FetchResponse, SafeFetcher, _charset, _decode


@pytest.fixture
def fetcher(tmp_path):
    s = Settings(
        cache_dir=tmp_path,
        cache_enabled=True,
        max_redirects=2,
        max_response_bytes=1024,
        total_timeout_s=5.0,
        connect_timeout_s=1.0,
        read_timeout_s=1.0,
        per_host_concurrency=2,
        max_concurrency=2,
    )
    cache = Cache(s)
    fetcher = SafeFetcher(s, cache)
    try:
        yield fetcher
    finally:
        cache.close()


def test_charset_parses_directive():
    assert _charset("text/html; charset=UTF-8") == "UTF-8"
    assert _charset("text/html") == "utf-8"
    assert _charset("text/html; charset='iso-8859-1'") == "iso-8859-1"


def test_decode_replaces_bad_encoding():
    body = b"\xff\xfe"
    assert _decode(body, "text/html; charset=unknown-xyz") == "\ufffd\ufffd"


@pytest.mark.asyncio
async def test_cached_hit_returns_body_and_meta(fetcher, tmp_path, respx_mock):
    route = respx_mock.get("https://example.com/cached").mock(return_value=Response(200, text="cached"))
    first = await fetcher.fetch("https://example.com/cached")
    assert first.status == 200
    assert first.body == b"cached"
    assert route.called
    route.calls.clear()
    second = await fetcher.fetch("https://example.com/cached")
    assert second.from_cache is True
    assert route.called is False


@pytest.mark.asyncio
async def test_head_request_is_not_cached(fetcher, respx_mock):
    respx_mock.head("https://example.com/head").mock(return_value=Response(200, headers={"content-type": "text/html"}))
    resp = await fetcher.fetch("https://example.com/head", method="HEAD")
    assert resp.status == 200
    assert resp.body == b""


@pytest.mark.asyncio
async def test_non_2xx_raises_fetch_error(fetcher, respx_mock):
    respx_mock.get("https://example.com/not-found").mock(return_value=Response(404, text="missing"))
    with pytest.raises(FetchError) as exc:
        await fetcher.fetch("https://example.com/not-found")
    assert exc.value.code == ErrCode.HTTP
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_304_returns_cached_copy(fetcher, respx_mock):
    respx_mock.get("https://example.com/etag").mock(
        side_effect=[
            Response(200, text="body", headers={"etag": '"abc"', "content-type": "text/html"}),
            Response(304, headers={"content-type": "text/html"}),
        ]
    )
    first = await fetcher.fetch("https://example.com/etag")
    assert first.body == b"body"
    second = await fetcher.fetch("https://example.com/etag")
    assert second.from_cache is True
    assert second.body == b"body"


@pytest.mark.asyncio
async def test_redirect_limit_exceeded(fetcher, respx_mock):
    respx_mock.get("https://example.com/a").mock(
        return_value=Response(302, headers={"location": "https://example.com/b"})
    )
    respx_mock.get("https://example.com/b").mock(
        return_value=Response(302, headers={"location": "https://example.com/c"})
    )
    respx_mock.get("https://example.com/c").mock(
        return_value=Response(302, headers={"location": "https://example.com/d"})
    )
    with pytest.raises(FetchError) as exc:
        await fetcher.fetch("https://example.com/a")
    assert "too many redirects" in str(exc.value)


@pytest.mark.asyncio
async def test_redirect_loop_detected(fetcher, respx_mock):
    respx_mock.get("https://example.com/loop").mock(
        return_value=Response(302, headers={"location": "https://example.com/loop"})
    )
    with pytest.raises(FetchError) as exc:
        await fetcher.fetch("https://example.com/loop")
    assert "redirect loop" in str(exc.value)


@pytest.mark.asyncio
async def test_byte_cap_truncates(fetcher, respx_mock):
    body = b"x" * 2048
    respx_mock.get("https://example.com/huge").mock(return_value=Response(200, content=body))
    resp = await fetcher.fetch("https://example.com/huge")
    assert resp.status == 200
    assert len(resp.body) <= fetcher.s.max_response_bytes
    assert resp.truncated is True
    assert resp.sha256


@pytest.mark.asyncio
async def test_stale_while_error_serves_expired_cache(fetcher, respx_mock):
    route = respx_mock.get("https://example.com/flaky").mock(
        return_value=Response(200, text="fresh", headers={"content-type": "text/html"})
    )
    await fetcher.fetch(
        "https://example.com/flaky",
        cache_ttl=0.001,
    )
    # Wait for TTL to expire
    import time

    time.sleep(0.05)
    route.mock(return_value=Response(503, text="error"))
    # Stale-while-error only applies to transient failures (timeout/retryable 5xx);
    # 503 is retryable so it must hit the stale path and return instead of raising.
    resp = await fetcher.fetch(
        "https://example.com/flaky",
        cache_ttl=0.001,
        stale_ok=True,
    )
    assert resp.from_cache is True
    assert resp.stale is True
    assert resp.body == b"fresh"


@pytest.mark.asyncio
async def test_fetch_text_returns_tuple(fetcher, respx_mock):
    respx_mock.get("https://example.com/text").mock(return_value=Response(200, text="hello"))
    text, resp = await fetcher.fetch_text("https://example.com/text")
    assert text == "hello"
    assert isinstance(resp, FetchResponse)


@pytest.mark.asyncio
async def test_json_body_sets_content_type(fetcher, respx_mock):
    respx_mock.post("https://example.com/api").mock(return_value=Response(200, text="ok"))
    await fetcher.fetch("https://example.com/api", method="POST", json_body={"a": 1})
    request = respx_mock.calls.last.request
    assert request.headers["content-type"] == "application/json"


@pytest.mark.asyncio
async def test_fetch_rejects_disallowed_url(fetcher):
    with pytest.raises(BlockedURLError) as exc:
        await fetcher.fetch("http://169.254.169.254/latest/meta-data/")
    assert exc.value.code in {ErrCode.BLOCKED_URL, ErrCode.BAD_INPUT}
