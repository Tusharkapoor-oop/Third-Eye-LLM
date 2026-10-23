
import pytest

from src.engine.search.aggregator import SearchAggregator, normalize_url


def test_url_normalization():
    raw_url = "https://example.com/blog/article/?utm_source=twitter&utm_medium=social&ref=ai_agent#heading-2"
    clean = normalize_url(raw_url)
    assert clean == "https://example.com/blog/article"

    raw_2 = "https://docs.python.org/3/library/asyncio.html?fbclid=12345"
    clean_2 = normalize_url(raw_2)
    assert clean_2 == "https://docs.python.org/3/library/asyncio.html"

@pytest.mark.asyncio
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
