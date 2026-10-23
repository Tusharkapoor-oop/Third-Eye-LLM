import asyncio

import pytest

from src.engine.crawl.crawler import WebsiteCrawler, is_trap_url
from src.engine.crawl.mapper import WebsiteMapper


def test_trap_detection():
    # Repeating directory segments
    assert is_trap_url("https://example.com/a/b/c/a/b/c/d") is True
    # Too many path segments
    assert is_trap_url("https://example.com/1/2/3/4/5/6/7/8/9") is True
    # Calendar query string explosion
    assert is_trap_url("https://example.com/events?date=2026-10-20&calendar=month") is True
    # Clean normal URL
    assert is_trap_url("https://example.com/blog/article-name") is False

@pytest.mark.asyncio
async def test_website_mapper_live():
    mapper = WebsiteMapper()
    res = await mapper.map_domain("https://www.python.org", limit=10)
    assert res["total_discovered"] > 0
    assert len(res["urls"]) <= 10
    assert "python.org" in res["domain"]

@pytest.mark.asyncio
async def test_website_crawler_bounded():
    crawler = WebsiteCrawler()
    res = await crawler.crawl("https://www.python.org/about/", max_depth=1, max_pages=3)
    if len(res.get("pages", [])) == 0:
        await asyncio.sleep(1.0)
        res = await crawler.crawl("https://www.python.org/about/", max_depth=1, max_pages=3)
    assert res["status"] == "completed"
    assert res["total_pages_crawled"] <= 3
    assert len(res["pages"]) > 0
