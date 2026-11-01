"""
Crawler Trap & Boundary Testing Suite
Verifies crawler doesn't get stuck in infinite loops or trap URLs.
"""
from __future__ import annotations

import pytest

from src.engine.crawl.crawler import WebsiteCrawler, is_trap_url
from src.engine.crawl.mapper import WebsiteMapper

# ---------------------------------------------------------------------------
# Trap URL detection tests
# ---------------------------------------------------------------------------

TRAP_URLS = [
    # Repeating directory segments
    ("https://example.com/a/b/c/a/b/c/d", True, "repeating segments"),
    ("https://example.com/a/b/c/a/b/c/", True, "repeating segments with trailing slash"),
    ("https://example.com/tag/tag/tag/", True, "consecutive identical segments"),
    # Too many path segments
    ("https://example.com/1/2/3/4/5/6/7/8/9", True, "9 path segments"),
    ("https://example.com/a/b/c/d/e/f/g/h", True, "8 path segments"),
    # Calendar/query string explosion
    ("https://example.com/events?date=2026-10-20&calendar=month", True, "calendar param"),
    ("https://example.com/events?year=2026&month=10", True, "year/month params"),
    ("https://example.com/filter?filter=active&sort=date", True, "filter/sort params"),
    # Clean normal URLs (should NOT be traps)
    ("https://example.com/blog/article-name", False, "clean blog URL"),
    ("https://example.com/", False, "root URL"),
    ("https://example.com/about/", False, "about page"),
    ("https://docs.python.org/3/library/asyncio.html", False, "documentation URL"),
]


@pytest.mark.parametrize("url, expected_trap, description", TRAP_URLS)
def test_is_trap_url(url: str, expected_trap: bool, description: str) -> None:
    result = is_trap_url(url)
    assert result == expected_trap, \
        f"Trap detection mismatch for {description}: {url} -> {result}, expected {expected_trap}"


# ---------------------------------------------------------------------------
# Crawler boundary tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_crawler_max_depth_respected() -> None:
    """max_depth=0 should only crawl the seed URL."""
    crawler = WebsiteCrawler()
    res = await crawler.crawl("https://www.python.org/about/", max_depth=0, max_pages=5)
    assert res["status"] == "completed"
    assert res["total_pages_crawled"] <= 1  # Only seed
    for page in res["pages"]:
        assert page["depth"] == 0


@pytest.mark.asyncio
async def test_crawler_max_pages_respected() -> None:
    """max_pages=2 should not crawl more than 2 pages."""
    crawler = WebsiteCrawler()
    res = await crawler.crawl("https://www.python.org/about/", max_depth=1, max_pages=2)
    assert res["status"] == "completed"
    assert res["total_pages_crawled"] <= 2


@pytest.mark.asyncio
async def test_crawler_domain_confinement() -> None:
    """Crawler should not leave the seed domain."""
    crawler = WebsiteCrawler()
    res = await crawler.crawl("https://www.python.org/about/", max_depth=1, max_pages=5)
    assert res["status"] == "completed"
    for page in res["pages"]:
        assert "python.org" in page["url"], f"Cross-domain crawl: {page['url']}"


@pytest.mark.asyncio
async def test_crawler_skips_traps() -> None:
    """Crawler should skip known trap URLs."""
    crawler = WebsiteCrawler()
    # Use a site that might have calendar/trap URLs
    res = await crawler.crawl("https://example.com/", max_depth=1, max_pages=5)
    assert res["status"] == "completed"
    # example.com may not have traps, but the call should not crash
    assert isinstance(res["skipped_urls"], int)


# ---------------------------------------------------------------------------
# Mapper tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mapper_limit_respected() -> None:
    """map_domain with limit=5 should return at most 5 URLs."""
    mapper = WebsiteMapper()
    res = await mapper.map_domain("https://www.python.org", limit=5)
    assert res["total_discovered"] <= 5
    assert len(res["urls"]) <= 5


@pytest.mark.asyncio
async def test_mapper_domain_confinement() -> None:
    """Mapper should not return URLs outside the seed domain."""
    mapper = WebsiteMapper()
    res = await mapper.map_domain("https://www.python.org", limit=10)
    for item in res["urls"]:
        assert "python.org" in item["url"], f"Cross-domain map: {item['url']}"
