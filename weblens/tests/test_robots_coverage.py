"""Coverage tests for robots.txt handling.

Tests both fail-open and fail-closed modes, allow/disallow rules, malformed
robots, fetch failures, and caching.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

from weblens.config import Settings
from weblens.crawl.robots import RobotsPolicy


@dataclass
class FakeResponse:
    ok: bool
    status: int
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")


def ok(robots: str) -> FakeResponse:
    return FakeResponse(ok=True, status=200, body=robots.encode("utf-8"))


class BadTextResponse:
    ok = True
    status = 200
    body = b"invalid"

    @property
    def text(self) -> str:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad byte")


class FakeFetcher:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls: list[str] = []
        self.raise_on: str | None = None

    async def fetch(self, url, **kwargs):
        self.calls.append(url)
        if self.raise_on == url:
            raise ConnectionError("boom")
        return self.responses.get(url, FakeResponse(ok=False, status=404, body=b""))


async def test_allowed_path(tmp_path):
    robots = "User-agent: *\nDisallow: /private/\nSitemap: https://example.com/sitemap.xml"
    fetcher = FakeFetcher({"https://example.com/robots.txt": ok(robots)})
    p = RobotsPolicy(Settings(cache_dir=tmp_path, robots_cache_ttl_s=60), fetcher)
    allowed, warning = await p.allowed("https://example.com/public/page")
    assert allowed is True
    assert warning == ""


async def test_disallowed_path(tmp_path):
    robots = "User-agent: *\nDisallow: /private/\nAllow: /private/public.html"
    fetcher = FakeFetcher({"https://example.com/robots.txt": ok(robots)})
    p = RobotsPolicy(Settings(cache_dir=tmp_path, robots_cache_ttl_s=60), fetcher)
    assert (await p.allowed("https://example.com/private/secret"))[0] is False


async def test_fetch_failure_fail_open(tmp_path):
    fetcher = FakeFetcher()
    fetcher.raise_on = "https://example.com/robots.txt"
    p = RobotsPolicy(Settings(cache_dir=tmp_path, robots_fail_closed=False, robots_cache_ttl_s=60), fetcher)
    allowed, warning = await p.allowed("https://example.com/page")
    assert allowed is True
    assert "robots_fetch_failed" in warning


async def test_non_200_status_fail_open(tmp_path):
    fetcher = FakeFetcher({"https://example.com/robots.txt": FakeResponse(ok=False, status=500, body=b"")})
    p = RobotsPolicy(Settings(cache_dir=tmp_path, robots_fail_closed=False, robots_cache_ttl_s=60), fetcher)
    allowed, warning = await p.allowed("https://example.com/page")
    assert allowed is True
    assert "robots_http_status" in warning


async def test_non_200_status_fail_closed(tmp_path):
    fetcher = FakeFetcher({"https://example.com/robots.txt": FakeResponse(ok=False, status=500, body=b"")})
    p = RobotsPolicy(Settings(cache_dir=tmp_path, robots_fail_closed=True, robots_cache_ttl_s=60), fetcher)
    allowed, warning = await p.allowed("https://example.com/page")
    assert allowed is False
    assert "robots_http_status" in warning


async def test_empty_body_fail_open(tmp_path):
    fetcher = FakeFetcher({"https://example.com/robots.txt": FakeResponse(ok=True, status=200, body=b"")})
    p = RobotsPolicy(Settings(cache_dir=tmp_path, robots_fail_closed=False, robots_cache_ttl_s=60), fetcher)
    allowed, warning = await p.allowed("https://example.com/page")
    assert allowed is True
    assert "robots_empty_response" in warning


async def test_empty_body_fail_closed(tmp_path):
    fetcher = FakeFetcher({"https://example.com/robots.txt": FakeResponse(ok=True, status=200, body=b"")})
    p = RobotsPolicy(Settings(cache_dir=tmp_path, robots_fail_closed=True, robots_cache_ttl_s=60), fetcher)
    allowed, warning = await p.allowed("https://example.com/page")
    assert allowed is False
    assert "robots_empty_response" in warning


async def test_malformed_robots_fail_open(tmp_path):
    fetcher = FakeFetcher({"https://example.com/robots.txt": BadTextResponse()})
    p = RobotsPolicy(Settings(cache_dir=tmp_path, robots_fail_closed=False, robots_cache_ttl_s=60), fetcher)
    assert (await p.allowed("https://example.com/page"))[0] is True


async def test_malformed_robots_fail_closed(tmp_path):
    fetcher = FakeFetcher({"https://example.com/robots.txt": BadTextResponse()})
    p = RobotsPolicy(Settings(cache_dir=tmp_path, robots_fail_closed=True, robots_cache_ttl_s=60), fetcher)
    assert (await p.allowed("https://example.com/page"))[0] is False


async def test_sitemaps_discovered(tmp_path):
    robots = "User-agent: *\nDisallow:\nSitemap: https://example.com/sitemap.xml\nSitemap: https://example.com/s2.xml"
    fetcher = FakeFetcher({"https://example.com/robots.txt": ok(robots)})
    p = RobotsPolicy(Settings(cache_dir=tmp_path, robots_cache_ttl_s=60), fetcher)
    maps, warning = await p.sitemaps("https://example.com/page")
    assert maps == ["https://example.com/sitemap.xml", "https://example.com/s2.xml"]
    assert warning == ""


async def test_cache_reuses_entry(tmp_path):
    fetcher = AsyncMock()
    fetcher.fetch = AsyncMock(return_value=ok("User-agent: *\nDisallow: /private/"))
    s = Settings(cache_dir=tmp_path, robots_cache_ttl_s=60)
    p = RobotsPolicy(s, fetcher)
    await p.allowed("https://example.com/public")
    await p.allowed("https://example.com/private")
    assert fetcher.fetch.call_count == 1
