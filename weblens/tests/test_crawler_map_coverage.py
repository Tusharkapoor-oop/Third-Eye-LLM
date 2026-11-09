"""Coverage for the sitemap discovery path in crawl/crawler.py.

Exercises `SiteCrawler._sitemap_urls` and `site_map` with a fake fetcher and a
stub extraction service, so no network or browser is used: sitemap index
expansion, plain urlset parsing, robots.txt sitemap hints, 404 fallback to
/sitemap.xml, malformed XML tolerance, and URL caps.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weblens.config import Settings
from weblens.crawl.crawler import SiteCrawler
from weblens.net import FetchResponse


class FakeFetcher:
    def __init__(self, responses: dict[str, FetchResponse]):
        self.responses = responses
        self.calls: list[str] = []

    async def fetch(self, url: str, **kwargs) -> FetchResponse:
        self.calls.append(url)
        if url in self.responses:
            return self.responses[url]
        return _resp(url, "not found", status=404, ctype="text/plain")

    async def close(self) -> None:
        return None


class StubDoc:
    def __init__(self, url: str, links=None, title: str = "Root"):
        self.url = url
        self.title = title
        self.links = links or []


class StubExtractor:
    """Minimal extraction service double for site_map()."""

    def __init__(self, doc: StubDoc):
        self._doc = doc

    async def fetch_doc(self, url: str, allow_browser: bool = False):
        return self._doc


def _resp(url: str, body: str, *, status: int = 200, ctype: str = "application/xml") -> FetchResponse:
    return FetchResponse(
        url=url,
        final_url=url,
        status=status,
        headers={"content-type": ctype},
        body=body.encode(),
        fetched_at="2025-01-01T00:00:00Z",
    )


ROBOTS_WITH_SITEMAP = """User-agent: *
Disallow: /private
Sitemap: https://example.com/sitemap.xml
"""

INDEX_XML = """<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sm-1.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sm-2.xml</loc></sitemap>
</sitemapindex>
"""


def urlset(*paths: str) -> str:
    entries = "".join(f"<url><loc>https://example.com/{p}</loc></url>" for p in paths)
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>'


def _crawler(tmp_path: Path, fetcher: FakeFetcher, links=None) -> SiteCrawler:
    settings = Settings(cache_dir=tmp_path, cache_enabled=False, allow_browser=False)
    doc = StubDoc("https://example.com/", links or [])
    return SiteCrawler(settings, fetcher, StubExtractor(doc))


@pytest.mark.asyncio
async def test_sitemap_urls_expands_index_and_collects_locs(tmp_path):
    fetcher = FakeFetcher(
        {
            "https://example.com/robots.txt": _resp(
                "https://example.com/robots.txt", ROBOTS_WITH_SITEMAP, ctype="text/plain"
            ),
            "https://example.com/sitemap.xml": _resp("https://example.com/sitemap.xml", INDEX_XML),
            "https://example.com/sm-1.xml": _resp("https://example.com/sm-1.xml", urlset("a", "b")),
            "https://example.com/sm-2.xml": _resp("https://example.com/sm-2.xml", urlset("c")),
        }
    )
    crawler = _crawler(tmp_path, fetcher)
    warnings: list[str] = []

    entries, sitemap_used = await crawler._sitemap_urls("https://example.com", cap=10, warnings=warnings)

    assert sitemap_used is True
    urls = {str(e["u"]) for e in entries}
    assert {"https://example.com/a", "https://example.com/b", "https://example.com/c"} <= urls
    assert "https://example.com/sm-1.xml" in fetcher.calls


@pytest.mark.asyncio
async def test_sitemap_urls_falls_back_to_default_when_robots_missing(tmp_path):
    fetcher = FakeFetcher(
        {
            "https://example.com/robots.txt": _resp(
                "https://example.com/robots.txt", "", status=404, ctype="text/plain"
            ),
            "https://example.com/sitemap.xml": _resp("https://example.com/sitemap.xml", urlset("x", "y")),
        }
    )
    crawler = _crawler(tmp_path, fetcher)

    entries, sitemap_used = await crawler._sitemap_urls("https://example.com", cap=10, warnings=[])

    assert "https://example.com/sitemap.xml" in fetcher.calls
    assert sitemap_used is True
    assert {str(e["u"]) for e in entries} >= {"https://example.com/x", "https://example.com/y"}


@pytest.mark.asyncio
async def test_sitemap_urls_tolerates_malformed_xml(tmp_path):
    fetcher = FakeFetcher(
        {
            "https://example.com/robots.txt": _resp(
                "https://example.com/robots.txt", "User-agent: *\nDisallow:\n", ctype="text/plain"
            ),
            "https://example.com/sitemap.xml": _resp("https://example.com/sitemap.xml", "<urlset><url><loc>broken"),
        }
    )
    crawler = _crawler(tmp_path, fetcher)

    entries, _ = await crawler._sitemap_urls("https://example.com", cap=5, warnings=[])

    assert isinstance(entries, list)  # no exception escapes


@pytest.mark.asyncio
async def test_sitemap_urls_respects_cap(tmp_path):
    many = urlset(*[f"p{i}" for i in range(30)])
    fetcher = FakeFetcher(
        {
            "https://example.com/robots.txt": _resp(
                "https://example.com/robots.txt", "User-agent: *\nDisallow:\n", ctype="text/plain"
            ),
            "https://example.com/sitemap.xml": _resp("https://example.com/sitemap.xml", many),
        }
    )
    crawler = _crawler(tmp_path, fetcher)

    entries, _ = await crawler._sitemap_urls("https://example.com", cap=3, warnings=[])

    assert len(entries) <= 3


@pytest.mark.asyncio
async def test_site_map_returns_root_first_and_caps_urls(tmp_path):
    links = [(f"https://example.com/page{i}", f"Page {i}") for i in range(10)]
    fetcher = FakeFetcher({})
    crawler = _crawler(tmp_path, fetcher, links=links)

    outcome = await crawler.site_map("https://example.com", max_urls=4)

    assert outcome.status == "ok"
    assert len(outcome.urls) <= 4
    first = outcome.urls[0]
    first_url = first["u"] if isinstance(first, dict) else str(first)
    assert str(first_url).rstrip("/") == "https://example.com"
    assert outcome.tokens is not None and outcome.tokens > 0


@pytest.mark.asyncio
async def test_site_map_rejects_invalid_url(tmp_path):
    from weblens.errors import WebLensError

    crawler = _crawler(tmp_path, FakeFetcher({}))

    with pytest.raises(WebLensError):
        await crawler.site_map("not-a-url")
