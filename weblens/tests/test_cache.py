from __future__ import annotations

import os

import pytest

from weblens.cache import Cache
from weblens.config import Settings


def _cache(tmp_path, **kwargs) -> Cache:
    kwargs.setdefault("cache_enabled", True)
    settings = Settings(
        cache_dir=tmp_path / "cache",
        search_providers="ddg",
        **kwargs,
    )
    return Cache(settings)


@pytest.mark.asyncio
async def test_cache_evicts_oldest_when_over_cap(tmp_path):
    cache = _cache(tmp_path, cache_max_bytes=1_000)
    try:
        # Incompressible values make the logical size predictable enough for a
        # small test cap.
        await cache.set("old", os.urandom(700), {"kind": "test"}, ttl=60)
        await cache.set("new", os.urandom(700), {"kind": "test"}, ttl=60)

        assert await cache.get("old") is None
        assert await cache.get("new") is not None
        stats = cache.stats()
        assert stats["evictions"] == 1
        assert stats["entries"] == 1
        assert int(stats["bytes"]) <= 1_000
        assert int(stats["max_bytes"]) == 1_000
    finally:
        cache.close()


@pytest.mark.asyncio
async def test_cache_cap_is_applied_when_reopened(tmp_path):
    cache = _cache(tmp_path, cache_max_bytes=0)
    try:
        await cache.set("one", os.urandom(700), {"kind": "test"}, ttl=60)
        await cache.set("two", os.urandom(700), {"kind": "test"}, ttl=60)
    finally:
        cache.close()

    reopened = _cache(tmp_path, cache_max_bytes=1_000)
    try:
        stats = reopened.stats()
        assert stats["entries"] == 1
        assert stats["evictions"] == 1
        assert int(stats["bytes"]) <= 1_000
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_cache_purge_and_clear_report_removed_rows(tmp_path):
    cache = _cache(tmp_path)
    try:
        await cache.set("expired", b"expired", {"kind": "test"}, ttl=-1)
        await cache.set("live", b"live", {"kind": "test"}, ttl=60)

        assert await cache.purge() == 1
        assert await cache.get("expired") is None
        assert await cache.get("live") is not None
        assert cache.stats()["entries"] == 1

        assert await cache.clear() == 1
        assert cache.stats()["entries"] == 0
    finally:
        cache.close()


@pytest.mark.asyncio
async def test_disabled_cache_is_a_noop(tmp_path):
    cache = _cache(tmp_path, cache_enabled=False)
    try:
        await cache.set("key", b"value", {"kind": "test"}, ttl=60)
        assert await cache.get("key") is None
        assert await cache.purge() == 0
        assert await cache.clear() == 0
        stats = cache.stats()
        assert stats["enabled"] is False
        assert stats["entries"] == 0
    finally:
        cache.close()


def test_auth_fingerprint_isolation():
    from weblens.net.client import _auth_fingerprint

    assert _auth_fingerprint(None) == ""
    assert _auth_fingerprint({}) == ""
    assert _auth_fingerprint({"Content-Type": "application/json"}) == ""

    fp1 = _auth_fingerprint({"Authorization": "Bearer token-1"})
    fp2 = _auth_fingerprint({"authorization": "Bearer token-2"})
    fp1_dup = _auth_fingerprint({"AUTHORIZATION": "Bearer token-1"})

    assert fp1 != ""
    assert fp2 != ""
    assert fp1 != fp2
    assert fp1 == fp1_dup


def test_cache_key_partitions_by_authorization():
    from weblens.cache import cache_key
    from weblens.net.client import _auth_fingerprint

    url = "https://internal.service.local/api/profile"
    key_anon = cache_key("http", "GET", url, _auth_fingerprint(None), "")
    key_user_a = cache_key("http", "GET", url, _auth_fingerprint({"Authorization": "Bearer alice"}), "")
    key_user_b = cache_key("http", "GET", url, _auth_fingerprint({"Authorization": "Bearer bob"}), "")

    assert key_anon != key_user_a
    assert key_anon != key_user_b
    assert key_user_a != key_user_b
