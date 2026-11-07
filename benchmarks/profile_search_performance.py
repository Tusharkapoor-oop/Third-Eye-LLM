"""
Empirical Profiling Script for Agent 03 - Search Performance Optimization.
Zero-Fabrication Directive: All metrics are directly measured and recorded.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Ensure repo root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx
import numpy as np

from src.engine.config import CONFIG
from src.engine.search.aggregator import SearchAggregator, normalize_url
from src.engine.search.base import SearchResult
from src.engine.search.bing_provider import BingSearchProvider
from src.engine.search.ddg_html_provider import DDGHTMLSearchProvider
from src.engine.search.ddgs_provider import DDGSearchProvider
from src.engine.search.tavily_provider import TavilySearchProvider
from src.engine.search.wiki_provider import WikipediaSearchProvider
from src.engine.search.brave_provider import SearXNGProvider
from src.engine.security import get_shared_http_client, close_shared_http_client


def calc_percentiles(latencies: list[float]) -> dict[str, float]:
    arr = np.array(latencies)
    return {
        "count": len(latencies),
        "min": float(np.min(arr)),
        "p50": float(np.percentile(arr, 50)),
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
    }


async def profile_individual_providers(test_queries: list[str]) -> dict:
    """Profiles individual providers directly without aggregator fallback."""
    print("--- Profiling Individual Providers ---")
    providers = {
        "wikipedia": WikipediaSearchProvider(),
        "bing": BingSearchProvider(),
        "tavily": TavilySearchProvider(),
        "ddgs": DDGSearchProvider(),
        "ddg_html": DDGHTMLSearchProvider(),
        "searxng_unconfigured": SearXNGProvider(""),
        "searxng_localhost": SearXNGProvider("http://127.0.0.1:8080"),
    }

    results = {}

    for name, prov in providers.items():
        print(f"Testing provider: {name}...")
        latencies = []
        counts = []
        errors = []

        # Test across first 5 representative queries
        for q in test_queries[:5]:
            t0 = time.perf_counter()
            try:
                # 6.0s timeout per attempt
                res = await asyncio.wait_for(prov.search(q, count=5), timeout=6.0)
                lat = time.perf_counter() - t0
                latencies.append(lat)
                counts.append(len(res))
            except Exception as e:
                lat = time.perf_counter() - t0
                latencies.append(lat)
                errors.append(f"{type(e).__name__}: {str(e)[:50]}")
                counts.append(0)

        results[name] = {
            "latencies": latencies,
            "avg_latency": float(np.mean(latencies)) if latencies else 0.0,
            "median_latency": float(np.median(latencies)) if latencies else 0.0,
            "min_latency": float(np.min(latencies)) if latencies else 0.0,
            "max_latency": float(np.max(latencies)) if latencies else 0.0,
            "avg_results": float(np.mean(counts)) if counts else 0.0,
            "error_count": len(errors),
            "errors": errors[:3],
        }
        print(f"  {name}: median={results[name]['median_latency']:.3f}s, errors={len(errors)}/{len(test_queries[:5])}")

    return results


async def profile_fixtures_latency(dataset: list[dict]) -> dict:
    """Runs all 50 fixtures through SearchAggregator and computes p50, p95, p99."""
    print("--- Running 50-Query Benchmark Fixtures ---")
    aggregator = SearchAggregator()
    # Disable cache for cold baseline measurements
    aggregator._cache.clear()

    latencies = []
    category_latencies: dict[str, list[float]] = {}
    results_summary = []

    for idx, item in enumerate(dataset):
        q = item["query"]
        cat = item["category"]
        if cat not in category_latencies:
            category_latencies[cat] = []

        t0 = time.perf_counter()
        resp = await aggregator.search(q, count=5)
        lat = time.perf_counter() - t0

        latencies.append(lat)
        category_latencies[cat].append(lat)

        results_summary.append({
            "id": item["id"],
            "query": q,
            "category": cat,
            "status": resp.status,
            "total_found": resp.total_found,
            "latency": lat,
            "provider_used": resp.results[0].provider if resp.results else "none",
        })

        if (idx + 1) % 10 == 0:
            print(f"  Processed {idx + 1}/{len(dataset)} queries... current p50: {np.percentile(latencies, 50):.3f}s")

    stats_overall = calc_percentiles(latencies)
    stats_by_category = {cat: calc_percentiles(lats) for cat, lats in category_latencies.items()}

    return {
        "overall": stats_overall,
        "by_category": stats_by_category,
        "raw_results": results_summary,
    }


async def profile_caching() -> dict:
    """Measures deduplication cache hit latency vs cold miss latency."""
    print("--- Profiling Deduplication Caching ---")
    aggregator = SearchAggregator()
    aggregator._cache.clear()
    query = "Python asyncio event loop architecture"

    # Cold run (cache miss)
    t0 = time.perf_counter()
    resp_cold = await aggregator.search(query, count=5)
    lat_cold = time.perf_counter() - t0

    # Hot runs (cache hits)
    hit_latencies = []
    for _ in range(5):
        t0 = time.perf_counter()
        resp_hot = await aggregator.search(query, count=5)
        lat_hot = time.perf_counter() - t0
        hit_latencies.append(lat_hot)

    speedup = lat_cold / np.mean(hit_latencies) if hit_latencies and np.mean(hit_latencies) > 0 else 0.0

    # Test URL normalization deduplication
    raw_urls = [
        "https://docs.python.org/3/library/asyncio.html?utm_source=twitter&utm_medium=social#tasks",
        "https://docs.python.org/3/library/asyncio.html?fbclid=12345",
        "https://docs.python.org/3/library/asyncio.html",
        "https://docs.python.org/3/library/asyncio.html#event-loop",
    ]
    normalized = [normalize_url(u) for u in raw_urls]
    deduped = list(set(normalized))

    return {
        "cold_miss_latency_s": lat_cold,
        "hot_hit_latencies_s": hit_latencies,
        "hot_hit_mean_s": float(np.mean(hit_latencies)),
        "speedup_factor": float(speedup),
        "url_dedup_test": {
            "raw_count": len(raw_urls),
            "deduped_count": len(deduped),
            "canonical_url": deduped[0] if deduped else "",
        }
    }


async def profile_concurrency(dataset: list[dict]) -> dict:
    """Evaluates search latency and throughput under concurrency levels (1, 3, 5, 10)."""
    print("--- Profiling Concurrency Levels ---")
    sample_queries = [d["query"] for d in dataset[:10]]
    concurrency_levels = [1, 3, 5, 10]
    concurrency_results = {}

    for c in concurrency_levels:
        aggregator = SearchAggregator()
        aggregator._cache.clear()
        sem = asyncio.Semaphore(c)

        async def worker(q: str):
            async with sem:
                t0 = time.perf_counter()
                resp = await aggregator.search(q, count=5)
                return time.perf_counter() - t0, resp.status

        t_start = time.perf_counter()
        task_res = await asyncio.gather(*(worker(q) for q in sample_queries))
        wall_time = time.perf_counter() - t_start

        lats = [r[0] for r in task_res]
        statuses = [r[1] for r in task_res]
        qps = len(sample_queries) / wall_time

        concurrency_results[str(c)] = {
            "concurrency": c,
            "wall_time_s": wall_time,
            "queries_per_second": qps,
            "p50_latency_s": float(np.percentile(lats, 50)),
            "p95_latency_s": float(np.percentile(lats, 95)),
            "mean_latency_s": float(np.mean(lats)),
            "success_rate": statuses.count("success") / len(statuses),
        }
        print(f"  Concurrency {c}: wall_time={wall_time:.2f}s, QPS={qps:.2f}, p50={np.percentile(lats, 50):.3f}s")

    return concurrency_results


async def profile_connection_pooling() -> dict:
    """Measures impact of shared HTTP client connection pooling vs fresh client per request."""
    print("--- Profiling Connection Pooling ---")
    url = "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=test&srlimit=1&format=json"
    headers = {"User-Agent": "WebIntelEngine/1.0 (performance-profiler)"}

    # 1. Fresh Client per request (no connection pooling / no TLS reuse)
    fresh_latencies = []
    for _ in range(5):
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
            _ = resp.status_code
        fresh_latencies.append(time.perf_counter() - t0)

    # 2. Shared Client with connection pooling
    pooled_latencies = []
    client = await get_shared_http_client()
    for _ in range(5):
        t0 = time.perf_counter()
        resp = await client.get(url, headers=headers)
        _ = resp.status_code
        pooled_latencies.append(time.perf_counter() - t0)

    return {
        "fresh_client_latencies_s": fresh_latencies,
        "fresh_client_mean_s": float(np.mean(fresh_latencies)),
        "pooled_client_latencies_s": pooled_latencies,
        "pooled_client_mean_s": float(np.mean(pooled_latencies)),
        "pooling_latency_reduction_pct": float((np.mean(fresh_latencies) - np.mean(pooled_latencies)) / np.mean(fresh_latencies) * 100),
    }


async def main():
    eval_file = ROOT / "benchmarks" / "eval_dataset.json"
    with open(eval_file, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    test_queries = [d["query"] for d in dataset]

    t_start = time.time()

    provider_profile = await profile_individual_providers(test_queries)
    fixtures_profile = await profile_fixtures_latency(dataset)
    cache_profile = await profile_caching()
    concurrency_profile = await profile_concurrency(dataset)
    pooling_profile = await profile_connection_pooling()

    total_duration = time.time() - t_start

    final_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_profiling_duration_s": total_duration,
        "providers": provider_profile,
        "fixtures": fixtures_profile,
        "caching": cache_profile,
        "concurrency": concurrency_profile,
        "connection_pooling": pooling_profile,
    }

    out_file = ROOT / "benchmarks" / "search_profiling_output.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(final_data, f, indent=2)

    print(f"\nProfiling complete in {total_duration:.2f}s. Results saved to {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
