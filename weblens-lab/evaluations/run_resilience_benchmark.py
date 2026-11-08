"""Measure the Milestone 3.1 resilience and repeat-query optimizations.

This is an in-process, synthetic benchmark, not a production gate. It measures
three things that can be checked deterministically without a network:

1. stale-cache recovery: a transient fetch failure is answered from an expired
   cache entry, while 404s are never masked;
2. protocol fallback inside a caller deadline: a slow primary HTTP/2 attempt
   leaves enough budget for the HTTP/1.1 pool;
3. search-result cache: repeated identical queries avoid provider calls.

Example:
    python weblens-lab/evaluations/run_resilience_benchmark.py --samples 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "weblens" / "src"))

from weblens.cache import Cache, cache_key  # noqa: E402
from weblens.config import Settings  # noqa: E402
from weblens.errors import ErrCode, FetchError  # noqa: E402
from weblens.net import SafeFetcher  # noqa: E402
from weblens.search.base import Hit  # noqa: E402
from weblens.search.router import SearchRouter  # noqa: E402
from weblens.urls import normalize_url  # noqa: E402

URL = "https://example.com/page"


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[index]


def _settings(tmp_path: Path, **kwargs) -> Settings:
    kwargs.setdefault("cache_enabled", True)
    kwargs.setdefault("search_providers", "ddg")
    kwargs.setdefault("allow_browser", False)
    kwargs.setdefault("total_timeout_s", 1.0)
    return Settings(cache_dir=tmp_path / "cache", **kwargs)


async def _seed_stale(cache: Cache, url: str, body: bytes = b"cached") -> None:
    current = normalize_url(url)
    key = cache_key("http", "GET", current, "", "")
    await cache.set(
        key,
        body,
        {
            "kind": "http",
            "final_url": current,
            "status": 200,
            "headers": {"content-type": "text/html"},
            "fetched_at": "2025-01-01T00:00:00Z",
            "truncated": False,
            "redirects": [],
        },
        ttl=-1,
    )


async def _stale_recovery(samples: int) -> dict:
    failures = {
        "timeout": FetchError("timeout", code=ErrCode.TIMEOUT, retryable=True),
        "protocol": FetchError("protocol reset", code=ErrCode.HTTP, retryable=True),
        "http_503": FetchError("HTTP 503", code=ErrCode.HTTP, retryable=True),
    }
    recovered = 0
    recovered_latency: list[float] = []
    with tempfile.TemporaryDirectory() as tmp:
        settings = _settings(Path(tmp), cache_stale_grace_s=3600)
        cache = Cache(settings)
        fetcher = SafeFetcher(settings, cache)
        await _seed_stale(cache, URL)
        current_failure = failures["timeout"]

        async def fail(*_args, **_kwargs):
            raise current_failure

        fetcher._request_once = fail  # type: ignore[method-assign]
        try:
            names = list(failures)
            for i in range(samples):
                current_failure = failures[names[i % len(names)]]
                started = time.perf_counter()
                resp = await fetcher.fetch(URL, stale_ok=True)
                recovered_latency.append((time.perf_counter() - started) * 1000.0)
                if resp.stale and resp.body == b"cached":
                    recovered += 1
        finally:
            await fetcher.close()
            cache.close()

    # Opting out must expose the failure instead of silently serving stale data.
    opted_out = 0
    with tempfile.TemporaryDirectory() as tmp:
        settings = _settings(Path(tmp), cache_stale_grace_s=3600)
        cache = Cache(settings)
        fetcher = SafeFetcher(settings, cache)
        await _seed_stale(cache, URL)
        current_failure = failures["timeout"]

        async def fail(*_args, **_kwargs):
            raise current_failure

        fetcher._request_once = fail  # type: ignore[method-assign]
        try:
            for _ in range(samples):
                try:
                    await fetcher.fetch(URL)
                except FetchError:
                    opted_out += 1
        finally:
            await fetcher.close()
            cache.close()

    # A 404 is a real answer and must not be replaced with old content.
    masked = 0
    with tempfile.TemporaryDirectory() as tmp:
        settings = _settings(Path(tmp), cache_stale_grace_s=3600)
        cache = Cache(settings)
        fetcher = SafeFetcher(settings, cache)
        await _seed_stale(cache, URL)
        not_found = FetchError("HTTP 404", code=ErrCode.HTTP, retryable=False)

        async def fail(*_args, **_kwargs):
            raise not_found

        fetcher._request_once = fail  # type: ignore[method-assign]
        try:
            for _ in range(samples):
                try:
                    resp = await fetcher.fetch(URL, stale_ok=True)
                    if resp.stale:
                        masked += 1
                except FetchError:
                    pass
        finally:
            await fetcher.close()
            cache.close()

    return {
        "sample_size": samples,
        "transient_failures": samples,
        "recovered": recovered,
        "recovery_rate": recovered / samples if samples else 0.0,
        "opt_out_failures_raised": opted_out,
        "opt_out_failure_rate": opted_out / samples if samples else 0.0,
        "not_found_masked": masked,
        "not_found_mask_rate": masked / samples if samples else 0.0,
        "recovery_latency_ms": {
            "p50": round(statistics.median(recovered_latency), 3) if recovered_latency else 0.0,
            "p95": round(_percentile(recovered_latency, 95), 3),
        },
    }


class _FakeStreamResponse:
    def __init__(self, body: bytes):
        self.status_code = 200
        self.headers = {"content-type": "text/html"}
        self._body = body

    async def aiter_bytes(self, _size: int):
        yield self._body


class _FakeStream:
    def __init__(self, body: bytes | None, delay: float):
        self.body = body
        self.delay = delay

    async def __aenter__(self):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.body is None:
            raise httpx.ReadError("simulated protocol failure")
        return _FakeStreamResponse(self.body)

    async def __aexit__(self, *exc):
        return False


class _FakeClient:
    def __init__(self, body: bytes | None = None, delay: float = 0.0):
        self.body = body
        self.delay = delay

    def stream(self, *_args, **_kwargs):
        return _FakeStream(self.body, self.delay)

    async def aclose(self):
        return None


async def _deadline_fallback(samples: int, budget_s: float = 0.4) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        settings = _settings(Path(tmp))
        cache = Cache(settings)
        fetcher = SafeFetcher(settings, cache)
        # Primary HTTP/2 pool never answers within its share.
        fetcher._client = _FakeClient(body=None, delay=budget_s * 4)  # type: ignore[assignment]
        fetcher._client_h1 = _FakeClient(body=b"h1 body")  # type: ignore[assignment]
        successes = 0
        latencies: list[float] = []
        try:
            for _ in range(samples):
                started = time.perf_counter()
                try:
                    resp = await fetcher._request_once(
                        URL, {}, 1024, deadline=time.monotonic() + budget_s
                    )
                except Exception:
                    continue
                latencies.append((time.perf_counter() - started) * 1000.0)
                if resp.body == b"h1 body":
                    successes += 1
        finally:
            await fetcher.close()
            cache.close()
    return {
        "sample_size": samples,
        "budget_s": budget_s,
        "fallback_successes": successes,
        "fallback_success_rate": successes / samples if samples else 0.0,
        "latency_ms": {
            "p50": round(statistics.median(latencies), 3) if latencies else 0.0,
            "p95": round(_percentile(latencies, 95), 3),
        },
    }


class _CacheFetcher:
    def __init__(self, cache):
        self.cache = cache


class _FakeProvider:
    name = "fake"

    def __init__(self):
        self.calls = 0

    async def search(self, query, **_kwargs):
        self.calls += 1
        await asyncio.sleep(0.02)
        return [
            Hit(
                title="Example Domain",
                url="https://example.com/",
                snippet="example domain reference page",
                provider="fake",
                rank=0,
            )
        ]


async def _search_cache(samples: int) -> dict:
    cached_latency: list[float] = []
    uncached_latency: list[float] = []
    with tempfile.TemporaryDirectory() as tmp:
        settings = _settings(
            Path(tmp), search_mode="fallback", search_cache_ttl_s=60
        )
        cache = Cache(settings)
        provider = _FakeProvider()
        router = SearchRouter(settings, _CacheFetcher(cache))  # type: ignore[arg-type]
        router._providers = [provider]
        try:
            await router.search("example domain", k=5)  # warm the cache
            for _ in range(samples):
                started = time.perf_counter()
                out = await router.search("example domain", k=5)
                cached_latency.append((time.perf_counter() - started) * 1000.0)
                assert "search_cache_hit" in out.warnings
            cached_calls = provider.calls
        finally:
            cache.close()

        settings2 = _settings(
            Path(tmp) / "uncached", search_mode="fallback", search_cache_ttl_s=0
        )
        cache2 = Cache(settings2)
        provider2 = _FakeProvider()
        router2 = SearchRouter(settings2, _CacheFetcher(cache2))  # type: ignore[arg-type]
        router2._providers = [provider2]
        try:
            for _ in range(samples):
                started = time.perf_counter()
                await router2.search("example domain", k=5)
                uncached_latency.append((time.perf_counter() - started) * 1000.0)
            uncached_calls = provider2.calls
        finally:
            cache2.close()

    return {
        "sample_size": samples,
        "cached_provider_calls": cached_calls,
        "uncached_provider_calls": uncached_calls,
        "provider_calls_avoided": max(0, uncached_calls - cached_calls),
        "cache_hit_rate": 1.0 if cached_calls == 1 else 0.0,
        "cached_latency_ms": {
            "p50": round(statistics.median(cached_latency), 3) if cached_latency else 0.0,
            "p95": round(_percentile(cached_latency, 95), 3),
        },
        "uncached_latency_ms": {
            "p50": round(statistics.median(uncached_latency), 3) if uncached_latency else 0.0,
            "p95": round(_percentile(uncached_latency, 95), 3),
        },
    }


async def run(samples: int) -> dict:
    stale = await _stale_recovery(samples)
    deadline = await _deadline_fallback(samples)
    search = await _search_cache(samples)
    passed = (
        stale["recovery_rate"] == 1.0
        and stale["opt_out_failure_rate"] == 1.0
        and stale["not_found_mask_rate"] == 0.0
        and deadline["fallback_success_rate"] == 1.0
        and search["cache_hit_rate"] == 1.0
        and search["cached_provider_calls"] == 1
    )
    return {
        "non_production": True,
        "source": "synthetic in-process; no live network or provider calls",
        "samples_per_metric": samples,
        "stale_cache": stale,
        "deadline_fallback": deadline,
        "search_cache": search,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(run(max(1, args.samples)))
    print(json.dumps(result, indent=2 if args.pretty else None))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
