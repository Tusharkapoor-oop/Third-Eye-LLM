from __future__ import annotations

import json

import pytest

from weblens.config import Settings
from weblens.errors import ProviderError
from weblens.net import FetchResponse
from weblens.search.base import Hit
from weblens.search.mwmbl import MwmblSearch
from weblens.search.relevance import domain_matches, domain_pattern, is_relevant
from weblens.search.router import SearchRouter


class FakeFetcher:
    def __init__(self, response: FetchResponse):
        self.response = response

    async def fetch(self, url: str, **kwargs):
        return self.response


def response(body: str, *, status: int = 200) -> FetchResponse:
    return FetchResponse(
        url="https://api.mwmbl.org/search/",
        final_url="https://api.mwmbl.org/search/",
        status=status,
        headers={"content-type": "application/json"},
        body=body.encode("utf-8"),
        fetched_at="2026-10-20T00:00:00Z",
    )


class FakeProvider:
    def __init__(self, name: str, hits: list[Hit]):
        self.name = name
        self.hits = hits
        self.calls = 0

    async def search(self, query: str, **kwargs):
        self.calls += 1
        return list(self.hits)


def hit(title: str, url: str, snippet: str = "", provider: str = "fake", rank: int = 0) -> Hit:
    return Hit(title=title, url=url, snippet=snippet, provider=provider, rank=rank)


class TimedProvider(FakeProvider):
    timeout_s = 1.25


def test_provider_timeout_override(settings):
    router = SearchRouter(settings, fetcher=None)  # type: ignore[arg-type]
    assert router._provider_timeout(TimedProvider("timed", [])) == 1.25
    assert router._provider_timeout(FakeProvider("plain", [])) == settings.provider_timeout_s


@pytest.mark.asyncio
async def test_mwmbl_joins_segment_arrays():
    body = json.dumps(
        [
            {
                "url": "https://docs.python.org/3/library/asyncio",
                "title": [
                    {"value": "asyncio", "is_bold": True},
                    {"value": " — Asynchronous I/O", "is_bold": False},
                ],
                "extract": [
                    {"value": "asyncio", "is_bold": True},
                    {"value": " is a library for concurrent code.", "is_bold": False},
                ],
                "source": "mwmbl",
            },
            {
                "url": "https://docs.python.org/3/library/asyncio",
                "title": [{"value": "duplicate", "is_bold": False}],
                "extract": [],
            },
        ]
    )
    p = MwmblSearch(FakeFetcher(response(body)))
    hits = await p.search("python asyncio", k=5)
    assert len(hits) == 1
    assert hits[0].title == "asyncio — Asynchronous I/O"
    assert hits[0].snippet == "asyncio is a library for concurrent code."
    assert hits[0].provider == "mwmbl"


@pytest.mark.asyncio
async def test_mwmbl_rejects_non_list_payload():
    p = MwmblSearch(FakeFetcher(response("{}")))
    with pytest.raises(ProviderError):
        await p.search("q")


def test_is_relevant_requires_half_of_terms_and_phrase():
    h = hit("SQLite WAL mode", "https://sqlite.org/wal.html", "Write-ahead logging")
    assert is_relevant(h, ["sqlite", "wal", "mode"], [])
    assert not is_relevant(h, ["sqlite", "backup", "encryption", "json"], [])
    assert is_relevant(h, ["sqlite"], ['"write-ahead logging"'])
    assert not is_relevant(h, ["sqlite"], ['"connection pool"'])


def test_authoritative_page_with_partial_term_coverage_is_kept():
    docs = hit(
        "asyncio — Asynchronous I/O — Python 3.15.0 documentation",
        "https://docs.python.org/3/library/asyncio.html",
        "asyncio is a library to write concurrent code.",
    )
    assert is_relevant(docs, ["python", "asyncio.timeout", "asyncio", "timeout", "usage"], [])


def test_domain_patterns():
    assert domain_pattern("https://www.Example.com/path?q=1") == "example.com"
    assert domain_pattern("sub.example.com") == "sub.example.com"
    assert domain_matches("docs.python.org", "python.org")
    assert not domain_matches("notpython.org", "python.org")


@pytest.mark.asyncio
async def test_router_discards_off_topic_and_continues_fallback(tmp_path):
    settings = Settings(
        cache_dir=tmp_path / "cache",
        cache_enabled=False,
        allow_browser=False,
        search_providers="ddg",
    )
    router = SearchRouter(settings, fetcher=None)  # type: ignore[arg-type]
    bad = FakeProvider(
        "bad",
        [hit("Unrelated video", "https://spam.example/watch", "adult trending content", provider="bad")],
    )
    good = FakeProvider(
        "good",
        [hit("Python asyncio", "https://docs.python.org/3/library/asyncio", "python async io", provider="good")],
    )
    router._providers = [bad, good]
    out = await router.search("python asyncio", k=5)
    assert out.status == "ok"
    assert [h.url for h in out.hits] == ["https://docs.python.org/3/library/asyncio"]
    assert bad.calls == 1 and good.calls == 1
    assert "off_topic_filtered:1" in out.warnings


@pytest.mark.asyncio
async def test_router_reports_no_reliable_result_when_all_filtered(tmp_path):
    settings = Settings(
        cache_dir=tmp_path / "cache",
        cache_enabled=False,
        allow_browser=False,
        search_providers="ddg",
    )
    router = SearchRouter(settings, fetcher=None)  # type: ignore[arg-type]
    router._providers = [
        FakeProvider("bad", [hit("Shopping deals", "https://shop.example/x", "unrelated", provider="bad")])
    ]
    out = await router.search("sqlite wal mode", k=5)
    assert out.status == "no_reliable_result"
    assert "no_query_match" in out.warnings


@pytest.mark.asyncio
async def test_router_enforces_domains_and_excludes(tmp_path):
    settings = Settings(
        cache_dir=tmp_path / "cache",
        cache_enabled=False,
        allow_browser=False,
        search_providers="ddg",
    )
    router = SearchRouter(settings, fetcher=None)  # type: ignore[arg-type]
    router._providers = [
        FakeProvider(
            "fake",
            [
                hit("Python docs", "https://docs.python.org/3/", "python documentation"),
                hit("Python mirror", "https://mirror.example/python", "python documentation"),
            ],
        )
    ]
    out = await router.search("python documentation", k=5, domains=["python.org"])
    assert [h.url for h in out.hits] == ["https://docs.python.org/3/"]
    assert "domain_filtered:1" in out.warnings

    out = await router.search("python documentation", k=5, exclude_domains=["python.org"])
    assert [h.url for h in out.hits] == ["https://mirror.example/python"]
