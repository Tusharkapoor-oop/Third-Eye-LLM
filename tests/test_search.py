
import os

import pytest

from src.engine.search.aggregator import SearchAggregator, normalize_url

# Live providers are unreliable in CI (DDG blocks entire networks; keyless HTML
# providers rate-limit). Set WEBINTEL_LIVE_TESTS=0 for offline runs.
LIVE_NET = os.environ.get("WEBINTEL_LIVE_TESTS", "1").lower() in ("1", "true", "yes")


def test_url_normalization():
    raw_url = "https://example.com/blog/article/?utm_source=twitter&utm_medium=social&ref=ai_agent#heading-2"
    clean = normalize_url(raw_url)
    assert clean == "https://example.com/blog/article"

    raw_2 = "https://docs.python.org/3/library/asyncio.html?fbclid=12345"
    clean_2 = normalize_url(raw_2)
    assert clean_2 == "https://docs.python.org/3/library/asyncio.html"


def test_url_normalization_preserves_path_case():
    """Paths are case-sensitive; only scheme and host may change case."""
    assert normalize_url("https://Example.COM/Wiki/Foo?utm_source=x#h") == (
        "https://example.com/Wiki/Foo"
    )


def test_url_normalization_rejects_control_chars_and_bad_hosts():
    """urlsplit silently deletes tabs/newlines and keeps spaces in the authority."""
    assert normalize_url("http://exam\tple.com/") == "http://exam\tple.com/"
    assert normalize_url("http://exa mple.com/") == "http://exa mple.com/"
    assert normalize_url("javascript:alert(1)") == "javascript:alert(1)"


@pytest.mark.asyncio
@pytest.mark.skipif(not LIVE_NET, reason="needs live search providers (set WEBINTEL_LIVE_TESTS=1)")
async def test_search_aggregator_live():
    aggregator = SearchAggregator()
    resp = await aggregator.search("Python programming language official", count=3, max_tokens=500)
    assert resp.status == "success"
    assert len(resp.results) > 0
    assert resp.results[0].url.startswith("http")
    assert resp.latency_seconds > 0
    # Check token count compliance
    total_tokens = sum(len(aggregator.tokenizer.encode(r.snippet)) for r in resp.results)
    assert total_tokens <= 500
