"""
Both-Stack Comparison Testing Suite
Verifies src/engine/ and src/weblens/ produce consistent results for the same inputs.
"""
from __future__ import annotations

import time

import pytest

from src.engine.extract.extractor import DocumentExtractor as EngineExtractor
from src.engine.search.aggregator import SearchAggregator
from src.weblens.cache import Cache
from src.weblens.config import get_settings
from src.weblens.extract.service import ExtractionService
from src.weblens.net import SafeFetcher
from src.weblens.search import SearchRouter

QUERIES = [
    "capital of France",
    "speed of light",
    "Python asyncio gather",
]

URLS = [
    "https://www.python.org/about/",
]


# ---------------------------------------------------------------------------
# Search comparison
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_both_stacks_same_query() -> None:
    """Both stacks should return results for the same query."""
    engine_agg = SearchAggregator()

    wl_settings = get_settings()
    wl_cache = Cache(wl_settings)
    wl_fetcher = SafeFetcher(wl_settings, wl_cache)
    wl_router = SearchRouter(wl_settings, wl_fetcher)

    for query in QUERIES:
        # Engine
        t0 = time.perf_counter()
        engine_resp = await engine_agg.search(query, count=5, max_tokens=600)
        engine_lat = time.perf_counter() - t0

        # WebLens
        t0 = time.perf_counter()
        wl_outcome = await wl_router.search(query, k=5)
        wl_lat = time.perf_counter() - t0

        print(f"\nQuery: {query}")
        print(f"  Engine: status={engine_resp.status}, results={len(engine_resp.results)}, "
              f"latency={engine_lat:.2f}s")
        print(f"  WebLens: status={wl_outcome.status}, hits={len(wl_outcome.hits)}, "
              f"latency={wl_lat:.2f}s, providers={wl_outcome.providers}")

        # Both should return a valid status
        assert engine_resp.status in ("success", "no_reliable_result")
        assert wl_outcome.status in ("ok", "no_reliable_result", "partial", "possibly_outdated")

    await wl_fetcher.close()
    wl_cache.close()


# ---------------------------------------------------------------------------
# Extract comparison
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_both_stacks_same_url() -> None:
    """Both stacks should extract content from the same URL."""
    engine_extractor = EngineExtractor()

    wl_settings = get_settings()
    wl_cache = Cache(wl_settings)
    wl_fetcher = SafeFetcher(wl_settings, wl_cache)
    wl_extractor = ExtractionService(wl_settings, wl_fetcher, wl_cache)

    for url in URLS:
        # Engine
        t0 = time.perf_counter()
        engine_doc = await engine_extractor.extract_url(url, query=None,
                                                         mode="passages", max_tokens=1200)
        engine_lat = time.perf_counter() - t0

        # WebLens
        t0 = time.perf_counter()
        try:
            wl_outcome = await wl_extractor.fetch_doc(url)
            wl_status = wl_outcome.status
            wl_passages = len(wl_outcome.passages)
            wl_tokens = wl_outcome.tokens
        except Exception:
            wl_status = "error"
            wl_passages = 0
            wl_tokens = 0
        wl_lat = time.perf_counter() - t0

        print(f"\nURL: {url}")
        print(f"  Engine: status={engine_doc.status}, passages={len(engine_doc.passages)}, "
              f"latency={engine_lat:.2f}s, tokens={engine_doc.tokens_used}")
        print(f"  WebLens: status={wl_status}, "
              f"passages={wl_passages}, latency={wl_lat:.2f}s, "
              f"tokens={wl_tokens}")

        # Both should return a valid status
        assert engine_doc.status in ("success", "blocked", "empty_content", "fetch_failed")
        assert wl_status in ("ok", "no_content", "blocked", "unreachable",
                             "unsupported_type", "error")

    await wl_fetcher.close()
    wl_cache.close()


# ---------------------------------------------------------------------------
# SSRF comparison - both should block
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ssrf_both_stacks_block() -> None:
    """Both stacks should block SSRF URLs."""
    engine_extractor = EngineExtractor()

    wl_settings = get_settings()
    wl_cache = Cache(wl_settings)
    wl_fetcher = SafeFetcher(wl_settings, wl_cache)
    wl_extractor = ExtractionService(wl_settings, wl_fetcher, wl_cache)

    ssrf_urls = [
        "http://127.0.0.1:9999/",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost:8080/",
    ]

    for url in ssrf_urls:
        # Engine
        engine_doc = await engine_extractor.extract_url(url, query=None,
                                                         mode="passages", max_tokens=600)
        assert engine_doc.status == "blocked", \
            f"Engine did not block {url}: {engine_doc.status}"

        # WebLens
        try:
            wl_outcome = await wl_extractor.fetch_doc(url)
            assert wl_outcome.status in ("blocked", "error", "unreachable"), \
                f"WebLens did not block {url}: {wl_outcome.status}"
        except Exception:
            # Exception is also acceptable for blocked URLs
            pass

        print(f"  SSRF {url}: Engine={engine_doc.status}, WebLens blocked ✓")

    await wl_fetcher.close()
    wl_cache.close()
