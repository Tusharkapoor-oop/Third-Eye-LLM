from __future__ import annotations

from weblens.crawl.crawler import (
    CrawledPage,
    CrawlOutcome,
    MapOutcome,
    SiteCrawler,
    crawlable,
    follow_threshold,
    path_affinity,
)
from weblens.extract.html import ExtractedDoc
from weblens.tokens import count_json_tokens


def _doc(url: str, text: str, links: list[tuple[str, str]] | None = None, published: str | None = None):
    return ExtractedDoc(
        url=url,
        final_url=url,
        title=url.rsplit("/", 1)[-1] or "root",
        text=text,
        fetched_at="2026-10-20T00:00:00Z",
        sha256="a" * 64,
        links=links or [],
        published=published,
    )


class FakeExtractor:
    def __init__(self, docs):
        self.docs = docs
        self.calls: list[str] = []

    async def fetch_doc(self, url, **kwargs):
        self.calls.append(url)
        return self.docs[url]


class FakeRobots:
    def __init__(self, denied=()):
        self.denied = set(denied)

    async def sitemaps(self, root):
        return [], ""

    async def allowed(self, url):
        return url not in self.denied, ""

    async def crawl_delay(self, url):
        return 0.0


def _crawler(settings, docs, denied=()):
    c = SiteCrawler(settings, fetcher=object(), extractor=FakeExtractor(docs))
    c.robots = FakeRobots(denied)
    return c


def test_path_affinity_prefers_siblings_then_directory_then_prefix():
    root = "https://docs.example/3/library/asyncio-task.html"
    assert path_affinity(root, "https://docs.example/3/library/asyncio-runner.html") == 4
    assert path_affinity(root, "https://docs.example/3/library/other.html") == 3
    assert path_affinity(root, "https://docs.example/3/tutorial.html") == 1
    assert path_affinity(root, "https://docs.example/other") == 0


def test_follow_threshold_is_strict_for_stem_pages():
    assert follow_threshold("https://docs.example/") == 0
    assert follow_threshold("https://docs.example/guide") == 3
    assert follow_threshold("https://docs.example/asyncio-task") == 4


def test_crawlable_rejects_assets_offsite_admin_calendar_and_big_queries():
    root = "https://example.com/docs/guide"
    assert crawlable("https://example.com/docs/a", root)
    assert not crawlable("https://other.com/docs/a", root)
    assert not crawlable("https://example.com/docs/pic.png", root)
    assert not crawlable("https://example.com/wp-admin/", root)
    assert not crawlable("https://example.com/blog/2026/10/20/", root)
    assert not crawlable("https://example.com/docs/a?" + "&".join(f"k{i}=v" for i in range(6)), root)
    assert not crawlable("https://example.com/docs/" + "a" * 600, root)


async def test_site_map_keeps_root_first_and_caps(settings, monkeypatch):
    root = "https://example.com/docs/guide"
    links = [(f"https://example.com/docs/{name}", name) for name in ("zeta", "alpha", "beta", "gamma", "delta")]
    docs = {root: _doc(root, "root page content", links)}
    c = _crawler(settings, docs)

    async def no_sitemap(url, cap, _warnings):
        return [], False

    monkeypatch.setattr(c, "_sitemap_urls", no_sitemap)
    out = await c.site_map(root, max_urls=3)
    assert out.url == root
    assert out.urls[0]["u"] == root
    assert 1 <= len(out.urls) <= 3
    assert out.status == "ok"
    payload = c.map_payload(out)
    assert payload["n"] == len(payload["urls"])
    assert count_json_tokens(payload) <= out.budget


async def test_site_map_no_links_reports_warning(settings, monkeypatch):
    root = "https://example.com/docs/guide"
    c = _crawler(settings, {root: _doc(root, "no links here")})

    async def no_sitemap(url, cap, _warnings):
        return [], False

    monkeypatch.setattr(c, "_sitemap_urls", no_sitemap)
    out = await c.site_map(root, max_urls=10)
    assert out.urls[0]["u"] == root
    assert "no_links_found" in out.warnings


async def test_crawl_respects_robots_depth_and_site_scope(settings):
    root = "https://example.com/docs/guide"
    a = "https://example.com/docs/a"
    b = "https://example.com/docs/b"
    docs = {
        root: _doc(
            root,
            "asyncio timeout guide. " * 20,
            [(a, "a"), (b, "b"), ("https://other.example/x", "x")],
        ),
        a: _doc(a, "asyncio timeout cancels the task and raises TimeoutError. " * 15),
        b: _doc(b, "different words entirely about cooking and music. " * 15),
    }
    c = _crawler(settings, docs, denied={b})
    out = await c.crawl(root, max_pages=5, max_depth=1, query="asyncio timeout", max_tokens=1500)
    assert out.url == root
    assert {p.url for p in out.pages} == {root, a}
    assert any(w == "robots_denied:1" for w in out.warnings)
    assert out.status in {"ok", "partial"}
    payload = c.payload(out)
    assert count_json_tokens(payload) <= 1500
    for page in payload["pages"]:
        for passage in page.get("ps", []):
            assert passage["s"][1] >= passage["s"][0]


async def test_crawl_page_cap_and_budget_are_strict(settings):
    root = "https://example.com/docs/guide"
    links = [(f"https://example.com/docs/{i}", str(i)) for i in range(10)]
    docs = {root: _doc(root, "asyncio timeout start. " * 30, links)}
    for i in range(10):
        docs[f"https://example.com/docs/{i}"] = _doc(
            f"https://example.com/docs/{i}",
            f"asyncio timeout page {i}. " * 40,
        )
    c = _crawler(settings, docs)
    out = await c.crawl(root, max_pages=2, max_depth=1, query="asyncio timeout", max_tokens=300)
    assert len(out.pages) <= 2
    payload = c.payload(out)
    assert count_json_tokens(payload) <= 300
    if len(out.pages) < 2 or payload.get("cut"):
        assert payload.get("cut") is True or len(out.pages) <= 2


def test_map_payload_drops_entries_under_budget(settings):
    c = _crawler(settings, {})
    out = MapOutcome(
        status="ok",
        url="https://example.com/",
        urls=[{"u": f"https://example.com/{i}", "t": "t"} for i in range(40)],
        elapsed_ms=1,
        tokens=0,
        budget=220,
    )
    payload = c.map_payload(out)
    assert count_json_tokens(payload) <= 220
    assert payload["n"] < 40
    assert payload["cut"] is True


def test_crawl_payload_drops_pages_under_budget(settings):
    c = _crawler(settings, {})
    pages = [
        CrawledPage(
            url=f"https://example.com/{i}",
            title="t",
            fetched_at="2026-10-20T00:00:00Z",
            status="ok",
            excerpt="x" * 500,
        )
        for i in range(10)
    ]
    out = CrawlOutcome(
        status="ok",
        url="https://example.com/",
        pages=pages,
        elapsed_ms=1,
        tokens=0,
        budget=250,
    )
    payload = c.payload(out)
    assert count_json_tokens(payload) <= 250
    assert payload["n"] < 10
    assert payload["cut"] is True
