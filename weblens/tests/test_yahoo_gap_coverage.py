"""Failure and merge-path coverage for the keyless Yahoo adapter."""

from __future__ import annotations

import pytest

from weblens.errors import ErrCode, FetchError, ProviderError
from weblens.net import FetchResponse
from weblens.search.yahoo import YahooSearch, unwrap


def _response(body: str) -> FetchResponse:
    return FetchResponse(
        url="https://search.yahoo.com",
        final_url="https://search.yahoo.com",
        status=200,
        headers={"content-type": "text/html; charset=utf-8"},
        body=body.encode(),
        fetched_at="2026-11-05T00:00:00Z",
    )


class HostFetcher:
    def __init__(self, us: str = "", jp: str = "", *, exc: Exception | None = None):
        self.us = us
        self.jp = jp
        self.exc = exc
        self.urls: list[str] = []

    async def fetch(self, url: str, **kwargs):
        self.urls.append(url)
        if self.exc is not None:
            raise self.exc
        return _response(self.jp if "yahoo.co.jp" in url else self.us)


_US_HTML = """
<div class="dd algo">
  <div class="compTitle"><a href="https://example.com/a"><h3>Title A</h3></a></div>
  <div class="compText">short</div>
</div>
<div class="dd algo">
  <div class="compTitle"><a href="https://example.com/b"><h3>Title B</h3></a></div>
</div>
"""

_JP_HTML = """
<div class="sw-Card Algo">
  <h3 class="sw-Card__titleMain"><a href="https://example.com/a">Title A JP</a></h3>
  <p class="sw-Card__summary">a much longer snippet from the Japanese edge</p>
</div>
"""


def test_yahoo_unwrap_covers_empty_protocol_and_direct_paths(monkeypatch):
    assert unwrap("") == ""
    assert unwrap("//r.search.yahoo.com/_ylt=x/RU=https%3a%2f%2fexample.com%2fa/RK=1") == "https://example.com/a"
    assert unwrap("https://example.com/a") == "https://example.com/a"
    assert unwrap("https://search.yahoo.com/search?p=x") == "https://search.yahoo.com/search?p=x"

    def broken(_):
        raise ValueError("bad url")

    monkeypatch.setattr("weblens.search.yahoo.urlsplit", broken)
    assert unwrap("https://example.com/a") == "https://example.com/a"


async def test_yahoo_search_builds_site_filters_and_freshness():
    fetcher = HostFetcher(_US_HTML, _JP_HTML)
    hits = await YahooSearch(fetcher).search(  # type: ignore[arg-type]
        "query",
        k=2,
        freshness="week",
        domains=["docs.example.com"],
        exclude_domains=["spam.example.com"],
    )
    assert hits
    assert all("site%3Adocs.example.com" in url for url in fetcher.urls)
    assert all("-site%3Aspam.example.com" in url for url in fetcher.urls)
    assert all("btf=w" in url for url in fetcher.urls)
    assert fetcher.urls[0].startswith("https://search.yahoo.com/search?p=")


async def test_yahoo_search_merges_duplicate_urls_and_keeps_longer_snippet():
    hits = await YahooSearch(HostFetcher(_US_HTML, _JP_HTML)).search("q", k=5)  # type: ignore[arg-type]
    by_url = {h.url: h for h in hits}
    assert set(by_url) == {"https://example.com/a", "https://example.com/b"}
    assert "Japanese edge" in by_url["https://example.com/a"].snippet
    assert [h.rank for h in hits] == [0, 1]


async def test_yahoo_parses_japanese_markup_when_us_markup_is_empty():
    hits = await YahooSearch(HostFetcher("", _JP_HTML)).search("q", k=5)  # type: ignore[arg-type]
    assert hits[0].title == "Title A JP"
    assert hits[0].snippet == "a much longer snippet from the Japanese edge"


@pytest.mark.parametrize(
    ("status", "message", "retryable"),
    [
        (429, "rate-limited", True),
        (403, "blocked", False),
        (500, "fetch failed", True),
    ],
)
async def test_yahoo_fetch_errors_become_provider_errors(status, message, retryable):
    exc = FetchError("upstream", status=status, retryable=True)
    with pytest.raises(ProviderError) as err:
        await YahooSearch(HostFetcher(exc=exc))._fetch_host(  # type: ignore[arg-type]
            "https://search.yahoo.com/search", "q", None, 5
        )
    assert message in str(err.value)
    assert err.value.retryable is retryable


async def test_yahoo_unusual_traffic_and_no_parseable_results():
    with pytest.raises(ProviderError) as err:
        await YahooSearch(HostFetcher("unusual traffic detected"))._fetch_host(  # type: ignore[arg-type]
            "https://search.yahoo.com/search", "q", None, 5
        )
    assert err.value.retryable is True

    with pytest.raises(ProviderError):
        await YahooSearch(HostFetcher("<html>nothing here</html>"))._fetch_host(  # type: ignore[arg-type]
            "https://search.yahoo.com/search", "q", None, 5
        )


async def test_yahoo_no_results_page_is_empty():
    no_results = "<html><body>No results</body></html>"
    hits = await YahooSearch(HostFetcher(no_results, no_results)).search("q", k=5)  # type: ignore[arg-type]
    assert hits == []


async def test_yahoo_parse_failure_is_provider_error(monkeypatch):
    def broken(*args, **kwargs):
        raise ValueError("bad html")

    monkeypatch.setattr("weblens.search.yahoo.lxml_html.fromstring", broken)
    with pytest.raises(ProviderError) as err:
        YahooSearch(HostFetcher("x"))._parse("x", 5)  # type: ignore[arg-type]
    assert err.value.code == ErrCode.PROVIDER


async def test_yahoo_search_propagates_provider_error_when_both_hosts_fail():
    exc = FetchError("upstream", status=403)
    with pytest.raises(ProviderError) as err:
        await YahooSearch(HostFetcher(exc=exc)).search("q")  # type: ignore[arg-type]
    assert "blocked" in str(err.value)


async def test_yahoo_search_wraps_non_provider_errors():
    with pytest.raises(ProviderError) as err:
        await YahooSearch(HostFetcher(exc=RuntimeError("socket"))).search("q")  # type: ignore[arg-type]
    assert "yahoo search failed" in str(err.value)
