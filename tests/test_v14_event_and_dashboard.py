"""Verification of Persistent EventStore and Dashboard Metrics (V14 Section 8).

Verifies:
1. Persistent recording of operations across all capabilities.
2. Strict distinction between implemented, attempted, succeeded, failed, and blocked operations.
3. Zero fake/phantom metrics.
4. Token consumption aggregation and truth guarantee.
"""

from __future__ import annotations

import os
from pathlib import Path
import uuid
import pytest
import pytest_asyncio

from event_store import EventStore, OperationEvent


@pytest_asyncio.fixture
async def event_store_fixture():
    test_db_path = f"cache/test_events_{uuid.uuid4().hex[:8]}.db"
    store = EventStore(db_path=test_db_path)
    yield store
    await store.close()
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_event_recording_and_counts(event_store_fixture: EventStore):
    store = event_store_fixture

    # Record 3 search events: 2 success, 1 failed
    await store.record_event(
        OperationEvent(
            capability="search",
            operation="web_search",
            status="success",
            duration_ms=120.5,
            provider="local_searxng",
            tokens_consumed=450,
            details={"query": "python mcp"},
        )
    )
    await store.record_event(
        OperationEvent(
            capability="search",
            operation="web_search",
            status="success",
            duration_ms=85.0,
            provider="tavily",
            tokens_consumed=310,
            details={"query": "fastmcp test"},
        )
    )
    await store.record_event(
        OperationEvent(
            capability="search",
            operation="web_search",
            status="failed",
            duration_ms=250.0,
            provider="local_searxng",
            tokens_consumed=0,
            details={"query": "failing query", "error": "upstream timeout"},
        )
    )

    # Record 1 blocked extraction (SSRF block)
    await store.record_event(
        OperationEvent(
            capability="extract",
            operation="extract_url",
            status="blocked",
            duration_ms=5.0,
            provider="security_guard",
            tokens_consumed=0,
            details={"url": "http://127.0.0.1/admin", "reason": "SSRF violation"},
        )
    )

    metrics = await store.get_dashboard_metrics()

    # Total operations recorded
    assert metrics["total_operations_recorded"] == 4
    assert metrics["total_tokens_consumed"] == 760

    # Search capability breakdown
    search_stats = metrics["by_capability"]["search"]
    assert search_stats["success"] == 2
    assert search_stats["failed"] == 1
    assert search_stats["blocked"] == 0
    assert search_stats["total"] == 3

    # Extract capability breakdown
    extract_stats = metrics["by_capability"]["extract"]
    assert extract_stats["success"] == 0
    assert extract_stats["failed"] == 0
    assert extract_stats["blocked"] == 1
    assert extract_stats["total"] == 1

    # Zero fake counts: Unused capabilities must report exactly 0
    for cap in ("crawl", "map_geo", "map_web", "research", "browser", "document"):
        cap_stats = metrics["by_capability"][cap]
        assert cap_stats["total"] == 0
        assert cap_stats["success"] == 0
        assert cap_stats["failed"] == 0
        assert cap_stats["blocked"] == 0


@pytest.mark.asyncio
async def test_truth_guarantee_and_capabilities(event_store_fixture: EventStore):
    store = event_store_fixture
    metrics = await store.get_dashboard_metrics()

    assert "truth_guarantee" in metrics
    assert "Zero fabricated activity" in metrics["truth_guarantee"]
    assert len(metrics["implemented_capabilities"]) == 8
    assert "search" in metrics["implemented_capabilities"]
    assert "browser" in metrics["implemented_capabilities"]
    assert "document" in metrics["implemented_capabilities"]
