"""
Load & Concurrency Stress Testing Suite
Verifies stability under concurrent load, burst traffic, and sustained requests.
"""
from __future__ import annotations

import asyncio
import time

import psutil
import pytest

from src.engine.extract.extractor import DocumentExtractor
from src.engine.search.aggregator import SearchAggregator

QUERIES = [
    "capital of France",
    "speed of light",
    "Python asyncio gather",
    "PEP 703 free threading",
    "HTTP/3 QUIC protocol",
    "largest mammal on Earth",
    "chemical formula for water",
    "fourth planet from Sun",
    "creator of Linux kernel",
    "author of Neuromancer",
]

URLS = [
    "https://www.python.org/about/",
    "https://en.wikipedia.org/wiki/Python_(programming_language)",
]


# ---------------------------------------------------------------------------
# Concurrent search stress
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_search_10_parallel() -> None:
    aggregator = SearchAggregator()

    async def one_query(q: str) -> dict:
        t0 = time.perf_counter()
        try:
            resp = await aggregator.search(q, count=5, max_tokens=600)
            return {"query": q, "status": resp.status,
                    "results": len(resp.results),
                    "latency": time.perf_counter() - t0, "error": None}
        except Exception as e:
            return {"query": q, "status": "error", "results": 0,
                    "latency": time.perf_counter() - t0, "error": str(e)}

    t0 = time.perf_counter()
    results = await asyncio.gather(*[one_query(q) for q in QUERIES])
    total = time.perf_counter() - t0

    errors = [r for r in results if r["error"]]
    latencies = [r["latency"] for r in results if r["error"] is None]

    print(f"\nConcurrent search (10 parallel): total={total:.2f}s, errors={len(errors)}")
    if latencies:
        latencies.sort()
        print(f"  p50={latencies[len(latencies)//2]:.2f}s, "
              f"p99={latencies[int(len(latencies)*0.99)-1]:.2f}s, "
              f"avg={sum(latencies)/len(latencies):.2f}s")

    assert len(errors) == 0, f"Errors during concurrent search: {errors}"
    assert all(r["status"] in ("success", "no_reliable_result") for r in results)


# ---------------------------------------------------------------------------
# Concurrent extract stress
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_extract_10_parallel() -> None:
    extractor = DocumentExtractor()

    async def one_extract(url: str) -> dict:
        t0 = time.perf_counter()
        try:
            doc = await extractor.extract_url(url, query=None, mode="passages", max_tokens=1200)
            return {"url": url, "status": doc.status,
                    "passages": len(doc.passages),
                    "latency": time.perf_counter() - t0, "error": None}
        except Exception as e:
            return {"url": url, "status": "error", "passages": 0,
                    "latency": time.perf_counter() - t0, "error": str(e)}

    url_list = URLS * 5
    t0 = time.perf_counter()
    results = await asyncio.gather(*[one_extract(u) for u in url_list])
    total = time.perf_counter() - t0

    errors = [r for r in results if r["error"]]
    latencies = [r["latency"] for r in results if r["error"] is None]

    print(f"\nConcurrent extract (10 parallel): total={total:.2f}s, errors={len(errors)}")
    if latencies:
        latencies.sort()
        print(f"  p50={latencies[len(latencies)//2]:.2f}s, "
              f"p99={latencies[int(len(latencies)*0.99)-1]:.2f}s, "
              f"avg={sum(latencies)/len(latencies):.2f}s")

    assert len(errors) == 0, f"Errors during concurrent extract: {errors}"


# ---------------------------------------------------------------------------
# Mixed load stress
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mixed_load_stress() -> None:
    aggregator = SearchAggregator()
    extractor = DocumentExtractor()

    async def search_task(q: str):
        return await aggregator.search(q, count=3, max_tokens=400)

    async def extract_task(u: str):
        return await extractor.extract_url(u, query=None, mode="passages", max_tokens=800)

    tasks = []
    for q in QUERIES[:5]:
        tasks.append(search_task(q))
    for u in URLS:
        tasks.append(extract_task(u))

    t0 = time.perf_counter()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    total = time.perf_counter() - t0

    exceptions = [r for r in results if isinstance(r, Exception)]
    print(f"\nMixed load ({len(tasks)} tasks): total={total:.2f}s, exceptions={len(exceptions)}")

    assert len(exceptions) == 0, f"Exceptions during mixed load: {exceptions[:3]}"
    for r in results:
        status = getattr(r, "status", None)
        assert status in ("success", "no_reliable_result", "fetch_failed", "empty_content", "blocked"), f"Unexpected status: {status}"


# ---------------------------------------------------------------------------
# Sustained load test (memory check)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sustained_load_memory() -> None:
    aggregator = SearchAggregator()

    mem_before = psutil.Process().memory_info().rss / 1024 / 1024

    for i in range(20):
        await aggregator.search("Python programming", count=3, max_tokens=400)

    mem_after = psutil.Process().memory_info().rss / 1024 / 1024
    mem_growth = mem_after - mem_before

    print(f"\nSustained load (20 queries): mem_before={mem_before:.1f}MB, "
          f"mem_after={mem_after:.1f}MB, growth={mem_growth:.1f}MB")

    assert mem_growth < 100, f"Possible memory leak: {mem_growth:.1f}MB growth"


# ---------------------------------------------------------------------------
# Burst load test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_burst_load() -> None:
    aggregator = SearchAggregator()

    async def one_query(i: int):
        return await aggregator.search(f"query {i}", count=2, max_tokens=300)

    t0 = time.perf_counter()
    results = await asyncio.gather(*[one_query(i) for i in range(50)],
                                   return_exceptions=True)
    total = time.perf_counter() - t0

    exceptions = [r for r in results if isinstance(r, Exception)]
    successes = [r for r in results if not isinstance(r, Exception)]

    print(f"\nBurst load (50 queries): total={total:.2f}s, "
          f"successes={len(successes)}, exceptions={len(exceptions)}")
    assert len(exceptions) == 0, f"Exceptions during burst load: {exceptions[:3]}"
    assert total < 120, f"Burst load too slow: {total:.2f}s"
