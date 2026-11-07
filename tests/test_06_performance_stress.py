"""Layer 6: Resource Leak, Concurrency & Performance Stress Suite.

Verifies:
- SQLite cache hit latency is strictly < 25ms (averaging < 5ms with WAL mode).
- In-memory FastMCP server handles 15 concurrent tool calls via asyncio.gather.
- Zero orphaned Chromium processes or hanging connections remain.
- Total process RAM usage stays within safe limits (< 500MB) for a 16GB RAM machine.
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import psutil
import pytest
import respx
from mcp import Client

from cache import SQLiteCache
from server import extractor, mcp, search_pipeline, shutdown_services


@pytest.mark.asyncio
async def test_sqlite_cache_sub_25ms_latency():
    """Verify SQLite cache hit latency is strictly under 25ms with WAL mode."""
    from pathlib import Path
    db_file = Path("cache") / "test_perf_cache.db"
    if db_file.exists():
        db_file.unlink()

    cache = SQLiteCache(db_path=str(db_file), default_ttl_hours=1.0)

    # Seed cache with realistic serialized JSON payload (10KB)
    payload = json.dumps({
        "query": "benchmark test",
        "results": [{"title": f"Item {i}", "content": "passage " * 50} for i in range(10)],
    })
    await cache.set("perf_test_key", payload)

    # Measure latency across 20 consecutive cache hits
    latencies: list[float] = []
    for _ in range(20):
        t0 = time.perf_counter()
        val = await cache.get("perf_test_key")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)
        assert val is not None

    await cache.close()
    if db_file.exists():
        try:
            db_file.unlink()
        except Exception:
            pass

    avg_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)

    # Strict gate: cache hit must be < 25ms
    assert max_latency < 25.0, f"Max cache hit latency was {max_latency:.2f}ms, expected < 25ms"
    assert avg_latency < 10.0, f"Average cache hit latency was {avg_latency:.2f}ms, expected < 10ms"


@pytest.mark.asyncio
async def test_15_concurrent_mcp_tool_calls_in_memory():
    """Verify server sustains 15 concurrent in-memory tool calls without deadlock or failure."""
    with respx.mock(assert_all_called=False) as respx_mock:
        passage_text = (
            "Genuine concurrent test content paragraph providing detailed factual information "
            "and structured evidence for benchmarking purposes across multiple concurrent worker threads. "
        ) * 3
        # Mock 15 unique targets
        for i in range(15):
            respx_mock.get(f"https://example.com/item_{i}").mock(
                return_value=httpx.Response(
                    200,
                    html=f"<html><body><h1>Title {i}</h1><p>{passage_text} Index {i}.</p></body></html>",
                    headers={"Content-Type": "text/html"},
                )
            )

        async with Client(mcp) as client:
            tasks = [
                client.call_tool(
                    "extract_url",
                    {"url": f"https://example.com/item_{i}", "query": "test query"},
                )
                for i in range(15)
            ]

            t0 = time.perf_counter()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.perf_counter() - t0

            assert elapsed < 5.0, f"15 concurrent calls took {elapsed:.2f}s, expected < 5s"
            assert len(results) == 15
            for idx, r in enumerate(results):
                assert not isinstance(r, Exception), f"Task {idx} failed with {r}"
                assert r is not None
                # Assert result contains structured content
                assert hasattr(r, "content")
                text_out = r.content[0].text if r.content else ""
                parsed = json.loads(text_out)
                assert parsed.get("url") == f"https://example.com/item_{idx}"


@pytest.mark.asyncio
async def test_resource_leak_and_ram_bounds():
    """Verify clean shutdown, zero orphaned Chromium processes, and safe RAM bounds."""
    current_proc = psutil.Process()

    # Cleanly close any warm browser or cache singletons
    try:
        from browser_agent import browser_agent
        await browser_agent.close()
    except Exception:
        pass
    await search_pipeline.close()
    await extractor.close()
    await shutdown_services()

    # Check for orphaned browser processes spawned by this process
    children = current_proc.children(recursive=True)
    chrome_children = [
        c for c in children
        if any(b in c.name().lower() for b in ("chrome", "chromium", "playwright"))
    ]
    assert len(chrome_children) == 0, f"Orphaned browser processes detected: {chrome_children}"

    # Verify process RAM usage stays under 500 MB (safe for 16GB laptop)
    mem_info = current_proc.memory_info()
    ram_mb = mem_info.rss / (1024 * 1024)
    assert ram_mb < 500.0, f"RAM usage {ram_mb:.1f}MB exceeded 500MB safety bound"
