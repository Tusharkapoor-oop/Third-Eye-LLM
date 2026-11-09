from __future__ import annotations

import json

import pytest

from weblens.errors import FetchError, ProviderError
from weblens.net import FetchResponse
from weblens.search.base import Hit, dedupe, make_hit, parse_date
from weblens.search.bing import BingHTML
from weblens.search.brave import BraveSearch
from weblens.search.duckduckgo import DuckDuckGoLite, unwrap
from weblens.search.router import rank
from weblens.search.searxng import SearXNGSsearch
from weblens.search.tavily import TavilySearch
from weblens.search.wikipedia import WikipediaSearch
from weblens.search.yahoo import YahooSearch
from weblens.search.yahoo import unwrap as yahoo_unwrap


class FakeFetcher:
    def __init__(
        self,
        response: FetchResponse | None = None,
        *,
        exc: Exception | None = None,
    ):
        self.response = response
        self.exc = exc
        self.calls: list[tuple[str, dict]] = []

    async def fetch(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        if self.exc is not None:
            raise self.exc
        return self.response


def response(
    body: str,
    *,
    status: int = 200,
    content_type: str = "text/html; charset=utf-8",
) -> FetchResponse:
    return FetchResponse(
        url="https://example.com",
        final_url="https://example.com",
        status=status,
        headers={"content-type": content_type},
        body=body.encode("utf-8"),
        fetched_at="2026-10-20T00:00:00Z",
    )


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    monkeypatch.setattr(DuckDuckGoLite, "_min_interval", 0)
    monkeypatch.setattr(BingHTML, "_min_interval", 0)


async def test_ddg_parses_results_and_unwraps_redirects():
    html = """
    <html><body>
      <a class="result-link" href="https://lite.duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">Example A</a>
      <table><tr><td class="result-snippet">Snippet A</td></tr></table>
      <a class="result-link" href="https://example.com/b">Example B</a>
      <table><tr><td class="result-snippet">Snippet B</td></tr></table>
    </body></html>
    """
    p = DuckDuckGoLite(FakeFetcher(response(html)))
    hits = await p.search("q", k=2)
    assert [h.url for h in hits] == ["https://example.com/a", "https://example.com/b"]
    assert hits[0].snippet == "Snippet A"
    assert hits[0].provider == "ddg"


async def test_ddg_bot_challenge_raises():
    p = DuckDuckGoLite(FakeFetcher(response("bots use DuckDuckGo", status=202)))
    with pytest.raises(ProviderError):
        await p.search("q")


async def test_ddg_no_results_is_empty():
    p = DuckDuckGoLite(FakeFetcher(response("<html>No results.</html>")))
    assert await p.search("q") == []


def test_ddg_unwrap():
    assert unwrap("//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com") == "https://example.com"
    assert unwrap("https://example.com/x") == "https://example.com/x"


async def test_bing_parses_title_snippet_and_date():
    html = """
    <html><body>
      <li class="b_algo">
        <h2><a href="https://example.com/a">Example A</a></h2>
        <div class="b_caption"><p>Snippet A</p></div>
        <span class="news_dt">2026-10-01</span>
      </li>
    </body></html>
    """
    p = BingHTML(FakeFetcher(response(html)))
    hits = await p.search("q", k=1)
    assert len(hits) == 1
    assert hits[0].title == "Example A"
    assert hits[0].date == "2026-10-01"


async def test_brave_json_and_errors():
    body = json.dumps(
        {
            "web": {
                "results": [
                    {
                        "title": "Brave result",
                        "url": "https://example.com/b",
                        "description": "Brave snippet",
                        "page_age": "2026-09-01",
                    }
                ]
            }
        }
    )
    p = BraveSearch(FakeFetcher(response(body, content_type="application/json")), "key")
    hits = await p.search("q", k=1)
    assert hits[0].url == "https://example.com/b"
    assert hits[0].date == "2026-09-01"

    p = BraveSearch(
        FakeFetcher(exc=FetchError("brave rate limit", status=429, retryable=True)),
        "key",
    )
    with pytest.raises(ProviderError) as err:
        await p.search("q")
    assert err.value.retryable is True


async def test_tavily_discards_provider_score():
    body = json.dumps(
        {
            "results": [
                {
                    "title": "T",
                    "url": "https://example.com/t",
                    "content": "C",
                    "score": 0.99,
                    "published_date": "2026-10-01",
                }
            ]
        }
    )
    p = TavilySearch(FakeFetcher(response(body, content_type="application/json")), "key")
    hits = await p.search("q", k=1)
    assert hits[0].url == "https://example.com/t"
    assert not hasattr(hits[0], "score")


async def test_searxng_requires_json_content_type():
    p = SearXNGSsearch(FakeFetcher(response("not json", content_type="text/html")), "https://sx.example")
    with pytest.raises(ProviderError):
        await p.search("q")


async def test_searxng_parses_json():
    body = json.dumps({"results": [{"title": "S", "url": "https://example.com/s", "content": "C"}]})
    p = SearXNGSsearch(FakeFetcher(response(body, content_type="application/json")), "https://sx.example")
    hits = await p.search("q", k=1)
    assert hits[0].title == "S"


async def test_wikipedia_parses_and_respects_domain_filter():
    body = json.dumps(
        {
            "query": {
                "search": [
                    {
                        "title": "Asyncio",
                        "snippet": "<span>Asynchronous</span> I/O",
                        "timestamp": "2026-10-01T00:00:00Z",
                    }
                ]
            }
        }
    )
    p = WikipediaSearch(FakeFetcher(response(body, content_type="application/json")))
    hits = await p.search("asyncio", k=1)
    assert hits[0].url == "https://en.wikipedia.org/wiki/Asyncio"
    assert "Asynchronous" in hits[0].snippet
    assert await p.search("asyncio", k=1, domains=["example.com"]) == []


async def test_wikipedia_uses_query_language():
    body = json.dumps(
        {
            "query": {
                "search": [
                    {
                        "title": "Berlin",
                        "snippet": "Hauptstadt Deutschlands",
                        "timestamp": "2026-10-01T00:00:00Z",
                    }
                ]
            }
        }
    )
    fetcher = FakeFetcher(response(body, content_type="application/json"))
    p = WikipediaSearch(fetcher)
    hits = await p.search("Quelle est la capitale de l'Allemagne ?", k=1)
    assert "fr.wikipedia.org/w/api.php" in fetcher.calls[0][0]
    assert hits[0].url == "https://fr.wikipedia.org/wiki/Berlin"


async def test_wikipedia_language_heuristic_keeps_english_queries_english():
    body = json.dumps({"query": {"search": []}})
    fetcher = FakeFetcher(response(body, content_type="application/json"))
    p = WikipediaSearch(fetcher)
    await p.search("What is the capital of Germany?", k=1)
    assert "en.wikipedia.org/w/api.php" in fetcher.calls[0][0]


async def test_wikipedia_language_heuristic_checks_kana_before_kanji():
    body = json.dumps({"query": {"search": []}})
    fetcher = FakeFetcher(response(body, content_type="application/json"))
    p = WikipediaSearch(fetcher)
    await p.search("量子もつれとは何ですか？", k=1)
    assert "ja.wikipedia.org/w/api.php" in fetcher.calls[0][0]


async def test_wikipedia_language_heuristic_handles_chinese_and_korean():
    body = json.dumps({"query": {"search": []}})
    fetcher = FakeFetcher(response(body, content_type="application/json"))
    p = WikipediaSearch(fetcher)
    await p.search("量子纠缠是什么？", k=1)
    assert "zh.wikipedia.org/w/api.php" in fetcher.calls[0][0]
    fetcher.calls.clear()
    await p.search("양자 얽힘이란 무엇인가요?", k=1)
    assert "ko.wikipedia.org/w/api.php" in fetcher.calls[0][0]


async def test_yahoo_parses_results_and_unwraps_redirects():
    body = """
    <div class="dd algo">
      <div class="compTitle">
        <a href="https://r.search.yahoo.com/_ylt=x/RU=https%3a%2f%2fexample.com%2fdocs%2fstart/RK=2/RS=x">
          <h3>Example documentation</h3>
        </a>
      </div>
      <div class="compText"><p>Example <b>snippet</b>.</p></div>
    </div>
    """
    fetcher = FakeFetcher(response(body))
    p = YahooSearch(fetcher)
    hits = await p.search("example docs", k=1)
    assert fetcher.calls[0][0].startswith("https://search.yahoo.com/search?p=")
    assert hits[0].url == "https://example.com/docs/start"
    assert hits[0].title == "Example documentation"
    assert hits[0].snippet == "Example snippet."


def test_yahoo_unwrap_keeps_direct_urls():
    assert yahoo_unwrap("https://example.com/docs") == "https://example.com/docs"


def test_make_hit_and_dedupe():
    a = make_hit("Title", "https://example.com/a?utm_source=x", "Snippet", provider="p", rank=1)
    b = make_hit("Title", "https://example.com/a", "Other", provider="q", rank=2)
    assert a is not None and b is not None
    assert a.url == "https://example.com/a"
    assert len(dedupe([a, b])) == 1
    assert make_hit("", "https://example.com/a", "s", provider="p", rank=1).title == "https://example.com/a"
    assert make_hit("T", "javascript:alert(1)", "s", provider="p", rank=1) is None


def test_parse_date_formats():
    assert parse_date("2026-10-20") == "2026-10-20"
    assert parse_date("20 Oct 2026") == "2026-10-20"
    assert parse_date("Oct 20, 2026") == "2026-10-20"
    assert parse_date("not a date") is None


def test_rank_accepts_iso_date_strings_from_providers():
    hits = [
        Hit(title="A", url="https://docs.python.org/3/", snippet="", date="2026-10-01", provider="bing", rank=0),
        Hit(title="B", url="https://example.com/", snippet="", date=None, provider="bing", rank=1),
    ]
    ordered = rank(hits)
    assert [h.title for h in ordered] == ["A", "B"]
