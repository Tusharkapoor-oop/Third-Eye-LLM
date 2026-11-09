from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import respx

from weblens.cache import Cache, cache_key
from weblens.config import Settings
from weblens.errors import ErrCode, FetchError, ProviderError
from weblens.extract.service import ExtractionService
from weblens.net import FetchResponse, SafeFetcher
from weblens.search.brave import BraveSearch
from weblens.search.searxng import SearXNGSsearch
from weblens.search.tavily import TavilySearch
from weblens.search.yahoo import YahooSearch
from weblens.urls import normalize_url

URL = "https://example.com/page"


def _settings(tmp_path, **kwargs) -> Settings:
    kwargs.setdefault("cache_enabled", True)
    kwargs.setdefault("search_providers", "ddg")
    kwargs.setdefault("allow_browser", False)
    kwargs.setdefault("total_timeout_s", 5.0)
    return Settings(cache_dir=tmp_path / "cache", **kwargs)


def _cached_response(url: str, body: bytes = b"cached", fetched_at: str = "2025-01-01T00:00:00Z") -> FetchResponse:
    return FetchResponse(
        url=url,
        final_url=url,
        status=200,
        headers={"content-type": "text/html"},
        body=body,
        fetched_at=fetched_at,
    )


async def _seed_stale(cache: Cache, url: str, body: bytes = b"cached", ttl: float = -1) -> str:
    current = normalize_url(url)
    key = cache_key("http", "GET", current, "", "")
    await cache.set(
        key,
        body,
        {
            "kind": "http",
            "final_url": current,
            "status": 200,
            "headers": {"content-type": "text/html"},
            "fetched_at": "2025-01-01T00:00:00Z",
            "truncated": False,
            "redirects": [],
        },
        ttl=ttl,
    )
    return key


@pytest.mark.asyncio
async def test_get_cached_exposes_stale_entry_within_grace(tmp_path):
    cache = Cache(_settings(tmp_path, cache_stale_grace_s=3600))
    try:
        await cache.set("k", b"old", {"kind": "http"}, ttl=-1)
        got = await cache.get_cached("k", 3600)
        assert got is not None
        body, meta, _created, expired = got
        assert body == b"old"
        assert meta["kind"] == "http"
        assert expired is True

        # The ordinary accessor still treats an expired entry as a miss.
        assert await cache.get("k") is None
        # Outside the grace window it is not offered at all.
        assert await cache.get_cached("k", -1) is None
        assert cache.stats()["stale_hits"] == 1
    finally:
        cache.close()


@pytest.mark.asyncio
async def test_fetch_serves_stale_copy_on_timeout(tmp_path):
    settings = _settings(tmp_path, cache_stale_grace_s=3600)
    cache = Cache(settings)
    fetcher = SafeFetcher(settings, cache)

    async def timeout(*args, **kwargs):
        raise FetchError("timeout", code=ErrCode.TIMEOUT, retryable=True)

    fetcher._request_once = timeout  # type: ignore[method-assign]
    try:
        await _seed_stale(cache, URL, b"old page")
        resp = await fetcher.fetch(URL, stale_ok=True)
        assert resp.stale is True
        assert resp.from_cache is True
        assert resp.body == b"old page"
        assert resp.fetched_at == "2025-01-01T00:00:00Z"
        assert resp.stale_age_s >= 0
    finally:
        await fetcher.close()
        cache.close()


@pytest.mark.asyncio
async def test_fetch_rejects_stale_without_opt_in(tmp_path):
    settings = _settings(tmp_path, cache_stale_grace_s=3600)
    cache = Cache(settings)
    fetcher = SafeFetcher(settings, cache)

    async def timeout(*args, **kwargs):
        raise FetchError("timeout", code=ErrCode.TIMEOUT, retryable=True)

    fetcher._request_once = timeout  # type: ignore[method-assign]
    try:
        await _seed_stale(cache, URL)
        with pytest.raises(FetchError):
            await fetcher.fetch(URL)
    finally:
        await fetcher.close()
        cache.close()


@pytest.mark.asyncio
async def test_fetch_does_not_use_stale_for_non_retryable_http(tmp_path):
    settings = _settings(tmp_path, cache_stale_grace_s=3600)
    cache = Cache(settings)
    fetcher = SafeFetcher(settings, cache)

    async def not_found(*args, **kwargs):
        raise FetchError("HTTP 404", code=ErrCode.HTTP, retryable=False)

    fetcher._request_once = not_found  # type: ignore[method-assign]
    try:
        await _seed_stale(cache, URL)
        with pytest.raises(FetchError):
            await fetcher.fetch(URL, stale_ok=True)
    finally:
        await fetcher.close()
        cache.close()


@pytest.mark.asyncio
async def test_fetch_does_not_use_stale_for_post(tmp_path):
    settings = _settings(tmp_path, cache_stale_grace_s=3600)
    cache = Cache(settings)
    fetcher = SafeFetcher(settings, cache)

    async def timeout(*args, **kwargs):
        raise FetchError("timeout", code=ErrCode.TIMEOUT, retryable=True)

    fetcher._request_once = timeout  # type: ignore[method-assign]
    try:
        current = normalize_url(URL)
        key = cache_key("http", "POST", current, "", "payload")
        await cache.set(
            key,
            b"old post",
            {"kind": "http", "final_url": current, "status": 200, "headers": {}, "fetched_at": "t"},
            ttl=-1,
        )
        with pytest.raises(FetchError):
            await fetcher.fetch(URL, method="POST", content=b"payload", stale_ok=True)
    finally:
        await fetcher.close()
        cache.close()


@pytest.mark.asyncio
async def test_fetch_does_not_use_stale_when_cache_ttl_is_zero(tmp_path):
    settings = _settings(tmp_path, cache_stale_grace_s=3600)
    cache = Cache(settings)
    fetcher = SafeFetcher(settings, cache)

    async def timeout(*args, **kwargs):
        raise FetchError("timeout", code=ErrCode.TIMEOUT, retryable=True)

    fetcher._request_once = timeout  # type: ignore[method-assign]
    try:
        await _seed_stale(cache, URL)
        with pytest.raises(FetchError):
            await fetcher.fetch(URL, cache_ttl=0, stale_ok=True)
    finally:
        await fetcher.close()
        cache.close()


@pytest.mark.asyncio
async def test_fetch_prefers_live_response_over_stale(tmp_path):
    settings = _settings(tmp_path, cache_stale_grace_s=3600)
    cache = Cache(settings)
    fetcher = SafeFetcher(settings, cache)

    async def live(*args, **kwargs):
        return _cached_response(URL, b"fresh page", fetched_at="2026-11-08T00:00:00Z")

    fetcher._request_once = live  # type: ignore[method-assign]
    try:
        await _seed_stale(cache, URL, b"old page")
        resp = await fetcher.fetch(URL, stale_ok=True)
        assert resp.stale is False
        assert resp.body == b"fresh page"
    finally:
        await fetcher.close()
        cache.close()


class _FakeStreamResponse:
    def __init__(self, body: bytes):
        self.status_code = 200
        self.headers = {"content-type": "text/html"}
        self._body = body

    async def aiter_bytes(self, _size: int):
        yield self._body


class _FakeStream:
    def __init__(self, body: bytes | None, error: Exception | None, delay: float = 0.0):
        self.body = body
        self.error = error
        self.delay = delay

    async def __aenter__(self):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return _FakeStreamResponse(self.body or b"")

    async def __aexit__(self, *exc):
        return False


class _FakeClient:
    def __init__(self, body: bytes | None = None, error: Exception | None = None, delay: float = 0.0):
        self.body = body
        self.error = error
        self.delay = delay

    def stream(self, *_args, **_kwargs):
        return _FakeStream(self.body, self.error, self.delay)

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_request_once_falls_back_to_http1_on_protocol_error(tmp_path):
    settings = _settings(tmp_path)
    cache = Cache(settings)
    fetcher = SafeFetcher(settings, cache)
    fetcher._client = _FakeClient(error=httpx.ProtocolError("h2 reset"))  # type: ignore[assignment]
    fetcher._client_h1 = _FakeClient(body=b"h1 body")  # type: ignore[assignment]
    try:
        resp = await fetcher._request_once(URL, {}, 1024)
        assert resp.body == b"h1 body"
    finally:
        await fetcher.close()
        cache.close()


@pytest.mark.asyncio
async def test_request_deadline_leaves_room_for_http1(tmp_path):
    settings = _settings(tmp_path)
    cache = Cache(settings)
    fetcher = SafeFetcher(settings, cache)
    # The primary pool never answers within its share; the fallback does.
    fetcher._client = _FakeClient(error=httpx.ReadError("slow h2"), delay=2.0)  # type: ignore[assignment]
    fetcher._client_h1 = _FakeClient(body=b"h1 body")  # type: ignore[assignment]
    try:
        started = time.perf_counter()
        resp = await fetcher._request_once(URL, {}, 1024, deadline=time.monotonic() + 0.4)
        elapsed = time.perf_counter() - started
        assert resp.body == b"h1 body"
        assert elapsed < 1.0
    finally:
        await fetcher.close()
        cache.close()


@pytest.mark.asyncio
async def test_extract_reports_stale_cache_warning(tmp_path):
    settings = _settings(tmp_path)
    cache = Cache(settings)
    fetcher = SafeFetcher(settings, cache)

    async def stale(*args, **kwargs):
        return FetchResponse(
            url=URL,
            final_url=URL,
            status=200,
            headers={"content-type": "text/html"},
            body=b"<html><body><p>hello stale world</p></body></html>",
            fetched_at="2025-01-01T00:00:00Z",
            stale=True,
            stale_age_s=3600,
        )

    fetcher.fetch = stale  # type: ignore[method-assign]
    service = ExtractionService(settings, fetcher, cache)
    try:
        doc = await service.fetch_doc(URL)
        assert "stale_cache_used" in doc.warnings
    finally:
        await fetcher.close()
        cache.close()


@pytest.mark.asyncio
async def test_fetch_error_includes_http_status(tmp_path):
    """HTTP error status must be available on FetchError for provider classification."""
    settings = _settings(tmp_path)
    cache = Cache(settings)
    fetcher = SafeFetcher(settings, cache)
    try:
        with respx.mock:
            respx.get("https://example.com/status_page").respond(429)
            with pytest.raises(FetchError) as exc_info:
                await fetcher.fetch("https://example.com/status_page", use_cache=False)
            assert exc_info.value.status == 429
    finally:
        await fetcher.close()
        cache.close()


@pytest.mark.asyncio
async def test_tavily_classifies_429_retryable_and_401_not(tmp_path):
    """Tavily provider must surface FetchError status as ProviderError retryability."""
    settings = _settings(tmp_path)
    cache = Cache(settings)
    fetcher = SafeFetcher(settings, cache)
    try:
        with respx.mock:
            respx.post("https://api.tavily.com/search").respond(401)
            tavily = TavilySearch(fetcher, api_key="test-key")
            with pytest.raises(ProviderError) as exc_info:
                await tavily.search("python asyncio")
            assert exc_info.value.code == ErrCode.PROVIDER
            assert exc_info.value.retryable is False

        with respx.mock:
            respx.post("https://api.tavily.com/search").respond(429)
            tavily = TavilySearch(fetcher, api_key="test-key")
            with pytest.raises(ProviderError) as exc_info:
                await tavily.search("python asyncio")
            assert exc_info.value.code == ErrCode.PROVIDER
            assert exc_info.value.retryable is True
    finally:
        await fetcher.close()
        cache.close()


@pytest.mark.asyncio
async def test_brave_classifies_429_retryable_and_401_not(tmp_path):
    """Brave provider must surface FetchError status as ProviderError retryability."""
    settings = _settings(tmp_path)
    cache = Cache(settings)
    fetcher = SafeFetcher(settings, cache)
    try:
        with respx.mock:
            respx.get(url__regex=r"https://api\.search\.brave\.com/.*").respond(401)
            brave = BraveSearch(fetcher, api_key="test-key")
            with pytest.raises(ProviderError) as exc_info:
                await brave.search("python asyncio")
            assert exc_info.value.code == ErrCode.PROVIDER
            assert exc_info.value.retryable is False

        with respx.mock:
            respx.get(url__regex=r"https://api\.search\.brave\.com/.*").respond(429)
            brave = BraveSearch(fetcher, api_key="test-key")
            with pytest.raises(ProviderError) as exc_info:
                await brave.search("python asyncio")
            assert exc_info.value.code == ErrCode.PROVIDER
            assert exc_info.value.retryable is True
    finally:
        await fetcher.close()
        cache.close()


@pytest.mark.asyncio
async def test_searxng_classifies_429_retryable_and_401_not(tmp_path):
    """SearXNG must not downgrade a retryable 429 into a non-retryable error."""
    settings = _settings(tmp_path, searxng_url="https://searx.example.org")
    cache = Cache(settings)
    fetcher = SafeFetcher(settings, cache)
    try:
        with respx.mock:
            respx.get(url__regex=r"https://searx\.example\.org/.*").respond(401)
            searxng = SearXNGSsearch(fetcher, "https://searx.example.org")
            with pytest.raises(ProviderError) as exc_info:
                await searxng.search("python asyncio")
            assert exc_info.value.code == ErrCode.PROVIDER
            assert exc_info.value.retryable is False

        with respx.mock:
            respx.get(url__regex=r"https://searx\.example\.org/.*").respond(429)
            searxng = SearXNGSsearch(fetcher, "https://searx.example.org")
            with pytest.raises(ProviderError) as exc_info:
                await searxng.search("python asyncio")
            assert exc_info.value.code == ErrCode.PROVIDER
            assert exc_info.value.retryable is True
    finally:
        await fetcher.close()
        cache.close()


@pytest.mark.asyncio
async def test_yahoo_classifies_429_retryable_and_401_not(tmp_path):
    """Yahoo must treat 401/403 as terminal and 429 as retryable."""
    settings = _settings(tmp_path)
    cache = Cache(settings)
    fetcher = SafeFetcher(settings, cache)
    try:
        with respx.mock:
            respx.get(url__regex=r"https://search\.yahoo\.(com|co\.jp)/.*").respond(401)
            yahoo = YahooSearch(fetcher)
            with pytest.raises(ProviderError) as exc_info:
                await yahoo.search("python asyncio")
            assert exc_info.value.code == ErrCode.PROVIDER
            assert exc_info.value.retryable is False

        with respx.mock:
            respx.get(url__regex=r"https://search\.yahoo\.(com|co\.jp)/.*").respond(429)
            yahoo = YahooSearch(fetcher)
            with pytest.raises(ProviderError) as exc_info:
                await yahoo.search("python asyncio")
            assert exc_info.value.code == ErrCode.PROVIDER
            assert exc_info.value.retryable is True
    finally:
        await fetcher.close()
        cache.close()
