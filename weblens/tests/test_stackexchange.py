from __future__ import annotations

import asyncio
import json

import pytest

from weblens.errors import ProviderError
from weblens.net import FetchResponse
from weblens.search.base import Hit
from weblens.search.stackexchange import StackExchangeSearch, looks_technical


class FakeProvider:
    def __init__(self, name: str, hits: list[Hit]):
        self.name = name
        self.hits = hits

    async def search(self, query: str, **kwargs) -> list[Hit]:
        return list(self.hits)


def hit(title: str, url: str) -> Hit:
    return Hit(title=title, url=url, snippet="", provider="fake", rank=0)


class FakeFetcher:
    def __init__(self, payloads: list[dict]):
        self.payloads = list(payloads)
        self.urls: list[str] = []

    async def fetch(self, url: str, **kwargs) -> FetchResponse:
        self.urls.append(url)
        payload = self.payloads.pop(0) if self.payloads else {"items": []}
        return FetchResponse(
            url=url,
            final_url=url,
            status=200,
            headers={"content-type": "application/json"},
            body=json.dumps(payload).encode(),
            fetched_at="2026-01-01T00:00:00Z",
        )


def _item(title: str, link: str, *, score: int = 3, answers: int = 2, tags=None) -> dict:
    return {
        "title": title,
        "link": link,
        "score": score,
        "answer_count": answers,
        "is_answered": True,
        "tags": tags or ["python", "asyncio"],
        "last_activity_date": 1_700_000_000,
    }


def test_technical_query_returns_question_hits():
    fetcher = FakeFetcher(
        [
            {
                "items": [
                    _item(
                        "asyncio.gather vs asyncio.wait (vs asyncio.TaskGroup)",
                        "https://stackoverflow.com/questions/1/x",
                    ),
                    _item("Using nested asyncio.gather()", "https://stackoverflow.com/questions/2/y"),
                ],
                "quota_remaining": 299,
            }
        ]
    )
    provider = StackExchangeSearch(fetcher)
    hits = asyncio.run(provider.search("How does asyncio.gather differ from asyncio.TaskGroup in Python 3.11+?", k=5))
    assert [h.title for h in hits][0].startswith("asyncio.gather vs")
    assert hits[0].provider == "stackexchange"
    assert hits[0].date == "2023-11-14"
    assert "Score 3" in hits[0].snippet
    assert "tags: python, asyncio" in hits[0].snippet
    assert "title=asyncio.gather" in fetcher.urls[0]
    assert "tagged=python" in fetcher.urls[0]


def test_non_technical_query_skips_the_api():
    fetcher = FakeFetcher([])
    provider = StackExchangeSearch(fetcher)
    hits = asyncio.run(provider.search("What major announcements did Google make about Gemini in late 2024?", k=5))
    assert hits == []
    assert fetcher.urls == []


def test_domain_filter_blocks_unrelated_domains():
    fetcher = FakeFetcher([])
    provider = StackExchangeSearch(fetcher)
    hits = asyncio.run(provider.search("How does asyncio.gather work?", k=5, domains=["docs.python.org"]))
    assert hits == []
    assert fetcher.urls == []


def test_title_match_falls_back_to_free_text():
    fetcher = FakeFetcher(
        [
            {"items": [], "quota_remaining": 299},
            {
                "items": [
                    _item("How to use asyncio.gather", "https://stackoverflow.com/questions/3/z"),
                ],
                "quota_remaining": 298,
            },
        ]
    )
    provider = StackExchangeSearch(fetcher)
    hits = asyncio.run(provider.search("How does asyncio.gather work?", k=5))
    assert len(hits) == 1
    assert len(fetcher.urls) == 2
    assert "title=asyncio.gather" in fetcher.urls[0]
    assert "q=" in fetcher.urls[1]


def test_quota_exhausted_raises_provider_error():
    fetcher = FakeFetcher([{"items": [], "quota_remaining": 0}])
    provider = StackExchangeSearch(fetcher)
    with pytest.raises(ProviderError, match="quota"):
        asyncio.run(provider.search("How does asyncio.gather work?", k=5))


def test_freshness_sets_fromdate():
    fetcher = FakeFetcher([{"items": [], "quota_remaining": 299}])
    provider = StackExchangeSearch(fetcher)
    asyncio.run(provider.search("How does asyncio.gather work?", k=5, freshness="week"))
    assert "fromdate=" in fetcher.urls[0]


def test_looks_technical_recognizes_languages_and_identifiers():
    assert looks_technical("How does asyncio.gather differ from TaskGroup in Python?")
    assert looks_technical("What is a Rust lifetime?")
    assert looks_technical("Why does Docker fail with a permission error?")
    assert not looks_technical("What is the capital of France?")
    assert not looks_technical("What did Google announce in late 2024?")


def test_stackexchange_is_a_supplement_not_a_primary(tmp_path):
    from weblens.config import Settings
    from weblens.search.router import SearchRouter

    settings = Settings(
        cache_dir=tmp_path / "cache",
        search_providers="mwmbl",
        supplement_providers="stackexchange",
        tavily_api_key=None,
        auto_include_tavily=False,
    )
    router = SearchRouter(settings, fetcher=None)  # type: ignore[arg-type]
    assert router.provider_names == ["mwmbl"]
    assert router.supplement_names == ["stackexchange"]


def test_supplement_pass_runs_only_when_called(tmp_path):
    from weblens.config import Settings
    from weblens.search.router import SearchOutcome, SearchRouter

    settings = Settings(
        cache_dir=tmp_path / "cache",
        search_providers="mwmbl",
        supplement_providers="stackexchange",
        tavily_api_key=None,
        auto_include_tavily=False,
    )
    router = SearchRouter(settings, fetcher=None)  # type: ignore[arg-type]
    router._supplements = [  # type: ignore[list-item]
        FakeProvider("stackexchange", [hit("question", "https://stackoverflow.com/questions/1")])
    ]
    outcome = SearchOutcome(query="q", used_query="q", hits=[])

    merged = asyncio.run(
        router._supplement_pass(
            "q",
            k=5,
            freshness=None,
            domains=None,
            exclude_domains=None,
            outcome=outcome,
            accept=lambda hs: hs,
        )
    )
    assert [h.url for h in merged] == ["https://stackoverflow.com/questions/1"]
    assert outcome.providers == ["stackexchange"]
    assert outcome.warnings == ["supplement:stackexchange"]
    assert outcome.failures == {}


def test_supplement_failure_is_isolated(tmp_path):
    from weblens.config import Settings
    from weblens.search.router import SearchOutcome, SearchRouter

    settings = Settings(
        cache_dir=tmp_path / "cache",
        search_providers="mwmbl",
        supplement_providers="stackexchange",
        tavily_api_key=None,
        auto_include_tavily=False,
    )
    router = SearchRouter(settings, fetcher=None)  # type: ignore[arg-type]

    class Failing:
        name = "stackexchange"

        async def search(self, query, **kwargs):
            raise TimeoutError()

    router._supplements = [Failing()]  # type: ignore[list-item]
    outcome = SearchOutcome(query="q", used_query="q", hits=[])
    merged = asyncio.run(
        router._supplement_pass(
            "q",
            k=5,
            freshness=None,
            domains=None,
            exclude_domains=None,
            outcome=outcome,
            accept=lambda hs: hs,
        )
    )
    assert merged == []
    assert outcome.failures == {}
    assert outcome.providers == []
    assert outcome.status == "ok"


def test_supplement_fills_empty_slots_without_displacing_primary_hits(tmp_path):
    from weblens.config import Settings
    from weblens.search.router import SearchRouter

    settings = Settings(
        cache_dir=tmp_path / "cache",
        cache_enabled=False,
        allow_browser=False,
        search_providers="mwmbl",
        supplement_providers="stackexchange",
        tavily_api_key=None,
        auto_include_tavily=False,
        use_official_source_hints=False,
        fuse_soft_timeout_s=0,
    )
    router = SearchRouter(settings, fetcher=None)  # type: ignore[arg-type]
    primary_url = "https://docs.python.org/3/library/asyncio-task.html"
    se_url = "https://stackoverflow.com/questions/1/python-asyncio-gather"
    router._providers = [  # type: ignore[list-item]
        FakeProvider("mwmbl", [hit("python asyncio gather", primary_url)])
    ]
    router._supplements = [  # type: ignore[list-item]
        FakeProvider("stackexchange", [hit("python asyncio gather question", se_url)])
    ]

    outcome = asyncio.run(router.search("python asyncio gather", k=5))

    urls = [h.url for h in outcome.hits]
    assert urls[0] == primary_url
    assert se_url in urls
    assert "supplement:stackexchange" in outcome.warnings
