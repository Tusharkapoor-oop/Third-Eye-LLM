"""Additional RedisCache tests using an in-memory fake client.

Covers import errors, malformed clients, stale-while-error paths, stats, and
non-pipeline set path.
"""

from __future__ import annotations

import time

from weblens.config import Settings
from weblens.redis_cache import RedisCache


class _FakeRedisNoPipeline:
    def __init__(self):
        self.data: dict[str, dict[bytes, bytes]] = {}
        self.expires: dict[str, float] = {}

    async def hset(self, key, *, mapping):
        self.data.setdefault(key, {}).update(mapping)
        return 1

    async def hgetall(self, key):
        return dict(self.data.get(key, {}))

    async def expire(self, key, ttl):
        self.expires[key] = time.time() + ttl
        return 1

    async def delete(self, *keys):
        removed = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                self.expires.pop(key, None)
                removed += 1
        return removed

    async def aclose(self):
        self.data.clear()


class _FakeRedisNoScan:
    def __init__(self):
        self.data: dict[str, dict[bytes, bytes]] = {}
        self.expires: dict[str, float] = {}

    async def hset(self, key, *, mapping):
        self.data.setdefault(key, {}).update(mapping)
        return 1

    async def hgetall(self, key):
        return dict(self.data.get(key, {}))

    async def expire(self, key, ttl):
        self.expires[key] = time.time() + ttl
        return 1

    async def delete(self, *keys):
        removed = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                self.expires.pop(key, None)
                removed += 1
        return removed

    async def keys(self, match):
        return list(self.data.keys())

    async def aclose(self):
        self.data.clear()


def _settings(tmp_path, **kwargs) -> Settings:
    kwargs.setdefault("cache_backend", "redis")
    kwargs.setdefault("cache_enabled", True)
    return Settings(cache_dir=tmp_path / "cache", **kwargs)


async def test_redis_set_uses_non_pipeline_branch(tmp_path):
    client = _FakeRedisNoPipeline()
    cache = RedisCache(_settings(tmp_path), client=client)
    await cache.set("page", b"x", {"kind": "http"}, ttl=60)
    assert "weblens:cache:page" in client.data


async def test_redis_clear_with_keys_fallback(tmp_path):
    client = _FakeRedisNoScan()
    cache = RedisCache(_settings(tmp_path), client=client)
    await cache.set("one", b"1", {"kind": "test"}, ttl=60)
    await cache.set("two", b"2", {"kind": "test"}, ttl=60)
    assert await cache.clear() == 2


async def test_redis_get_corrupt_meta_returns_none(tmp_path):
    client = _FakeRedisNoPipeline()
    cache = RedisCache(_settings(tmp_path), client=client)
    await cache.set("k", b"v", {"kind": "test"}, ttl=60)
    client.data["weblens:cache:k"][b"m"] = b"not-json"
    assert await cache.get("k") is None
    assert cache.errors >= 1


async def test_redis_get_decode_error_returns_none(tmp_path):
    client = _FakeRedisNoPipeline()
    cache = RedisCache(_settings(tmp_path), client=client)
    await cache.set("k", b"v", {"kind": "test"}, ttl=60)
    client.data["weblens:cache:k"][b"v"] = b"not-zlib"
    assert await cache.get("k") is None
    assert cache.errors >= 1


async def test_redis_get_json_bad_json_returns_none(tmp_path):
    client = _FakeRedisNoPipeline()
    cache = RedisCache(_settings(tmp_path), client=client)
    await cache.set_json("k", {"a": 1}, {"kind": "json"}, ttl=60)
    client.data["weblens:cache:k"][b"v"] = client.data["weblens:cache:k"][b"v"]
    assert await cache.get_json("k") is not None
    # Now corrupt the value to invalid JSON
    client.data["weblens:cache:k"][b"v"] = b"x"
    assert await cache.get_json("k") is None
    assert cache.errors >= 1


async def test_redis_stats_async_scan_error(tmp_path):
    class FailingScan:
        async def hset(self, *args, **kwargs):
            return 1

        async def hgetall(self, key):
            return {}

        async def scan_iter(self, *args, **kwargs):
            if False:  # pragma: no cover - makes this an async generator
                yield
            raise RuntimeError("scan failed")

        async def aclose(self):
            pass

    cache = RedisCache(_settings(tmp_path), client=FailingScan())
    stats = await cache.stats_async()
    assert stats["errors"] >= 1


async def test_redis_import_error_makes_cache_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr("weblens.redis_cache.Settings", lambda **kw: _settings(tmp_path))
    import sys

    original = sys.modules.get("redis")
    sys.modules["redis"] = None  # type: ignore[assignment]
    try:
        cache = RedisCache(_settings(tmp_path), client=None)
        assert cache._client_or_none() is None
        assert cache.errors >= 1
    finally:
        if original is not None:
            sys.modules["redis"] = original
        else:
            sys.modules.pop("redis", None)


async def test_redis_aclose_owned_client(tmp_path):
    class Closeable:
        def __init__(self):
            self.closed = False

        async def aclose(self):
            self.closed = True

    cache = RedisCache(_settings(tmp_path), client=None)
    client = Closeable()
    cache._client = client  # simulate a lazily-created, cache-owned client
    assert cache._owns_client is True
    await cache.aclose()
    assert client.closed is True


async def test_redis_close_sets_flag(tmp_path):
    cache = RedisCache(_settings(tmp_path), client=None)
    cache.close()
    assert cache._closed is True
