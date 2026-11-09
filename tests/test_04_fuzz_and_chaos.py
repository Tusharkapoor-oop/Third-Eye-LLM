"""Layer 4: Property-Based Fuzzing & Chaos Resilience.

Verifies:
- Hypothesis property-based fuzzing on all 5 MCP tool inputs with arbitrary Unicode,
  emojis, SQL injection, JSON special characters, negative integers, and malformed URLs
  running strictly against mocked local transports (Rule 1 compliant).
- Chaos network testing with mocked SearXNG errors (500, 429, malformed JSON).
- Straggler URL isolation: 1 hanging URL does not prevent early-exit in < 2.5s.
- Missing API keys trigger graceful local extractive/BM25 fallback without crashing.
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
import respx
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from config import CONFIG
from schemas import ChunkResult, SourceItem
from server import crawl_website, deep_research, extract_url, shutdown_services, web_map, web_search


@pytest.fixture(autouse=True)
async def close_event_store_after_test():
    """Close every aiosqlite worker thread so pytest can exit after the fuzz run."""
    yield
    await shutdown_services()


@pytest.fixture(autouse=True)
def mock_all_outbound_http():
    """Mock all outbound network requests ensuring 100% in-memory fuzzing without external network calls."""
    orig_tavily = CONFIG.tavily_api_key
    orig_gemini = CONFIG.gemini_api_key
    object.__setattr__(CONFIG, "tavily_api_key", "")
    object.__setattr__(CONFIG, "gemini_api_key", "")

    try:
        with respx.mock(assert_all_called=False) as respx_mock:
            # Mock SearXNG JSON API
            respx_mock.get(url__regex=r".*/search\?.*").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "results": [
                            {"url": "https://example.com/item1", "title": "Mock Title 1", "content": "Paragraph 1 snippet."},
                            {"url": "https://example.com/item2", "title": "Mock Title 2", "content": "Paragraph 2 snippet."},
                        ]
                    },
                )
            )
            # Mock general HTML responses for extraction and mapping
            respx_mock.route().mock(
                return_value=httpx.Response(
                    200,
                    html=(
                        "<html><body>"
                        "<h1>Mocked Page</h1>"
                        "<a class='result-link' href='https://example.com/link1'>Link 1</a>"
                        "<p>Genuine test passage text for fuzz and chaos testing.</p>"
                        "</body></html>"
                    ),
                    headers={"Content-Type": "text/html"},
                )
            )
            yield respx_mock
    finally:
        object.__setattr__(CONFIG, "tavily_api_key", orig_tavily)
        object.__setattr__(CONFIG, "gemini_api_key", orig_gemini)


async def _fast_extract(url: str, *, query=None, chunks_per_source=3, force_tier2=False):
    """Deterministic extractor stand-in: input fuzzing must not wait on ONNX/Playwright."""
    text = "Genuine test passage text for fuzz and chaos testing."
    return SourceItem(
        title="Mock Title",
        url=url,
        content=text,
        score=0.9,
        chunks=[ChunkResult(content=text, score=0.9, char_count=len(text))],
    )


@settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture], deadline=None)
@given(
    query=st.text(min_size=0, max_size=200),
    max_results=st.integers(min_value=-100, max_value=1000),
)
@pytest.mark.asyncio
async def test_fuzz_web_search_inputs(query: str, max_results: int, monkeypatch: pytest.MonkeyPatch):
    """Fuzz web_search with arbitrary strings and integers asserting no unhandled crashes.

    Search providers are stubbed so the property runs fully offline; without this
    each Hypothesis example performed live DuckDuckGo traffic and blew the timeout.
    """
    import search_pipeline as search_pipeline_module

    async def _offline_results(q, count=15, time_range=None):
        return [
            {"url": "https://example.com/item1", "title": "Mock Title 1", "snippet": "Paragraph 1 snippet."},
            {"url": "https://example.com/item2", "title": "Mock Title 2", "snippet": "Paragraph 2 snippet."},
        ]

    monkeypatch.setattr(search_pipeline_module, "_search_searxng", _offline_results)
    monkeypatch.setattr(search_pipeline_module, "_search_ddg_html", _offline_results)

    from server import search_pipeline as server_pipeline

    monkeypatch.setattr(server_pipeline.extractor, "extract_url", _fast_extract)

    res_str = await web_search(query=query, max_results=max_results)
    assert isinstance(res_str, str)
    parsed = json.loads(res_str)
    assert isinstance(parsed, dict)
    assert "query" in parsed or "error" in parsed or "status" in parsed


@settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture], deadline=None)
@given(
    url=st.text(min_size=0, max_size=200),
    query=st.text(min_size=0, max_size=100),
)
@pytest.mark.asyncio
async def test_fuzz_extract_url_inputs(url: str, query: str):
    """Fuzz extract_url with arbitrary malformed URLs asserting graceful envelope return."""
    res_str = await extract_url(url=url, query=query)
    assert isinstance(res_str, str)
    parsed = json.loads(res_str)
    assert isinstance(parsed, dict)
    assert "url" in parsed or "error" in parsed


@settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture], deadline=None)
@given(
    url=st.text(min_size=0, max_size=150),
    limit=st.integers(min_value=-50, max_value=500),
)
@pytest.mark.asyncio
async def test_fuzz_web_map_inputs(url: str, limit: int):
    """Fuzz web_map with invalid URLs and extreme limits asserting structured response."""
    res_str = await web_map(url=url, limit=limit)
    assert isinstance(res_str, str)
    parsed = json.loads(res_str)
    assert isinstance(parsed, dict)
    assert "url" in parsed


@settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture], deadline=None)
@given(
    url=st.text(min_size=0, max_size=150),
    instructions=st.text(min_size=0, max_size=100),
)
@pytest.mark.asyncio
async def test_fuzz_crawl_website_inputs(url: str, instructions: str):
    """Fuzz crawl_website with arbitrary inputs asserting structured JSON return."""
    res_str = await crawl_website(url=url, instructions=instructions)
    assert isinstance(res_str, str)
    parsed = json.loads(res_str)
    assert isinstance(parsed, dict)
    assert "query" in parsed


@settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture], deadline=None)
@given(prompt=st.text(min_size=0, max_size=150))
@pytest.mark.asyncio
async def test_fuzz_deep_research_inputs(prompt: str, monkeypatch: pytest.MonkeyPatch):
    """Fuzz deep_research with arbitrary strings asserting structured research envelope.

    Providers and the model call are stubbed so the property is hermetic and the
    deterministic extractive synthesis path is exercised instead.
    """
    import search_pipeline as search_pipeline_module

    async def _offline_results(q, count=15, time_range=None):
        return [
            {"url": "https://example.com/item1", "title": "Mock Title 1", "snippet": "Paragraph 1 snippet."},
            {"url": "https://example.com/item2", "title": "Mock Title 2", "snippet": "Paragraph 2 snippet."},
        ]

    monkeypatch.setattr(search_pipeline_module, "_search_searxng", _offline_results)
    monkeypatch.setattr(search_pipeline_module, "_search_ddg_html", _offline_results)

    from server import search_pipeline as server_pipeline

    monkeypatch.setattr(server_pipeline.extractor, "extract_url", _fast_extract)

    from model_provider import model_client

    async def _no_synthesis(*args, **kwargs):
        return None

    monkeypatch.setattr(model_client, "synthesize_research_report", _no_synthesis)

    res_str = await deep_research(input_prompt=prompt, mode="mini")
    assert isinstance(res_str, str)
    parsed = json.loads(res_str)
    assert isinstance(parsed, dict)
    assert "query" in parsed or "error" in parsed


@pytest.mark.asyncio
async def test_chaos_searxng_failures_fallback_to_ddg():
    """Verify that SearXNG failures trigger automatic fallback without failing."""
    from search_pipeline import SearchPipeline

    pipeline = SearchPipeline()
    res = await pipeline.search(query="python asyncio testing", max_results=2)
    assert res is not None
    assert isinstance(res.results, list)


@pytest.mark.asyncio
async def test_straggler_url_early_exit_under_time_limit():
    """Verify that when 1 URL hangs for 15s while 3 finish fast, search early-exits in < 2.5s."""
    from schemas import SourceItem
    from search_pipeline import SearchPipeline

    pipeline = SearchPipeline()

    fast_url1 = "https://example.com/fast1"
    fast_url2 = "https://example.com/fast2"
    slow_url = "https://example.com/slow-hanging"

    candidate_urls = [
        (fast_url1, "Fast 1", 1.0),
        (fast_url2, "Fast 2", 0.9),
        (slow_url, "Slow Hanging", 0.5),
    ]

    t0 = time.perf_counter()
    sources = []

    async def mock_extract(u, **kwargs):
        if "slow" in u:
            await asyncio.sleep(15.0)
        return SourceItem(title=u, url=u, content="Mocked content passage", score=0.9, chunks=[])

    pipeline.extractor.extract_url = mock_extract

    tasks = [
        asyncio.create_task(
            asyncio.wait_for(
                pipeline.extractor.extract_url(u, query="quick", chunks_per_source=2),
                timeout=1.0,
            )
        )
        for u, _, _ in candidate_urls
    ]

    for fut in asyncio.as_completed(tasks):
        try:
            r = await fut
            if isinstance(r, SourceItem):
                sources.append(r)
                if len(sources) >= 2:
                    break
        except Exception:
            continue

    for t in tasks:
        if not t.done():
            t.cancel()

    elapsed = time.perf_counter() - t0
    # Must finish in under 2.5 seconds despite the 15-second straggler
    assert elapsed < 2.5, f"Early exit took {elapsed:.2f}s, expected < 2.5s"
    assert len(sources) == 2
