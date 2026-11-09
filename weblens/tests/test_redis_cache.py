from __future__ import annotations

import fnmatch
import time
from typing import Any

import pytest

from weblens.cache import Cache, build_cache
from weblens.config import Settings
from weblens.redis_cache import RedisCache


class FakePipeline:
    def __init__(self, client: FakeRedis):
        self.client = client
        self.ops: list[tuple[Any, ...]] = []

    def hset(self, key: str, mapping: dict[bytes, bytes]):
        self.ops.append(("hset", key, mapping))
        return self

    def expire(self, key: str, ttl: int):
        self.ops.append(("expire", key, ttl))
        return self

    async def execute(self):
        for op in self.ops:
            await getattr(self.client, op[0])(*op[1:])
        self.ops.clear()
        return [1 for _ in range(len(self.ops))]


class FakeRedis:
    def __init__(self):
        self.data: dict[str, dict[bytes, bytes]] = {}
        self.expires: dict[str, float] = {}

    def _expired(self, key: str) -> bool:
        deadline = self.expires.get(key)
        return deadline is not None and deadline <= time.time()

    async def hgetall(self, key: str):
        if self._expired(key):
            self.data.pop(key, None)
            self.expires.pop(key, None)
            return {}
        return dict(self.data.get(key, {}))

    async def hset(self, key: str, mapping: dict[bytes, bytes]):
        self.data.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def expire(self, key: str, ttl: int):
        self.expires[key] = time.time() + int(ttl)
        return 1

    async def delete(self, *keys: str):
        removed = 0
        for key in keys:
            if key in self.data:
                removed += 1
                self.data.pop(key, None)
                self.expires.pop(key, None)
        return removed

    async def scan_iter(self, match: str, count: int = 500):
        for key in list(self.data):
            if fnmatch.fnmatch(key, match):
                yield key

    def pipeline(self, transaction: bool = False):
        return FakePipeline(self)

    async def aclose(self):
        self.data.clear()


class BrokenRedis:
    async def hgetall(self, key):
        raise RuntimeError("redis down")

    async def hset(self, key, mapping):
        raise RuntimeError("redis down")

    async def expire(self, key, ttl):
        raise RuntimeError("redis down")

    def pipeline(self, transaction: bool = False):
        return BrokenPipeline()


class BrokenPipeline:
    def hset(self, *args, **kwargs):
        return self

    def expire(self, *args, **kwargs):
        return self

    async def execute(self):
        raise RuntimeError("redis down")


def _settings(tmp_path, **kwargs) -> Settings:
    kwargs.setdefault("cache_backend", "redis")
    kwargs.setdefault("cache_enabled", True)
    return Settings(cache_dir=tmp_path / "cache", **kwargs)


async def test_redis_cache_round_trip_and_json(tmp_path):
    client = FakeRedis()
    cache = RedisCache(_settings(tmp_path), client=client)
    await cache.set("k1", b"hello", {"kind": "test"}, ttl=60)
    got = await cache.get("k1")
    assert got is not None
    raw, meta, created = got
    assert raw == b"hello"
    assert meta["kind"] == "test"
    assert created <= time.time()

    await cache.set_json("k2", {"a": 1}, {"kind": "json"}, ttl=60)
    decoded = await cache.get_json("k2")
    assert decoded is not None
    assert decoded[0] == {"a": 1}

    stats = await cache.stats_async()
    assert stats["backend"] == "redis"
    assert stats["shared"] is True
    assert stats["entries"] == 2
    assert stats["hits"] == 2


async def test_redis_cache_ttl_zero_deletes_and_expired_values_are_miss(tmp_path):
    client = FakeRedis()
    cache = RedisCache(_settings(tmp_path), client=client)
    await cache.set("gone", b"x", {"kind": "test"}, ttl=0)
    assert await cache.get("gone") is None

    await cache.set("stale", b"x", {"kind": "test"}, ttl=60)
    client.expires["weblens:cache:stale"] = time.time() - 1
    assert await cache.get("stale") is None


async def test_redis_cache_serves_stale_within_grace(tmp_path):
    client = FakeRedis()
    cache = RedisCache(_settings(tmp_path, cache_stale_grace_s=3600), client=client)
    await cache.set("stale", b"x", {"kind": "test"}, ttl=60)
    key = "weblens:cache:stale"
    # Force the logical expiry into the past while the server-side key (kept
    # alive for the grace window) still exists.
    client.data[key][b"e"] = str(time.time() - 1).encode("ascii")

    assert await cache.get("stale") is None
    got = await cache.get_cached("stale", 3600)
    assert got is not None
    raw, meta, _created, expired = got
    assert raw == b"x"
    assert meta["kind"] == "test"
    assert expired is True
    assert await cache.get_cached("stale", -1) is None
    assert cache.stats()["stale_hits"] == 1


async def test_redis_cache_extends_only_http_keys_for_stale_grace(tmp_path):
    client = FakeRedis()
    cache = RedisCache(_settings(tmp_path, cache_stale_grace_s=3600), client=client)
    started = time.time()
    await cache.set("page", b"x", {"kind": "http"}, ttl=60)
    await cache.set("search", b"y", {"kind": "search"}, ttl=60)
    assert client.expires["weblens:cache:page"] >= started + 3600
    assert client.expires["weblens:cache:search"] <= started + 61


async def test_redis_cache_clear_only_touches_namespace(tmp_path):
    client = FakeRedis()
    cache = RedisCache(_settings(tmp_path), client=client)
    await cache.set("one", b"1", {"kind": "test"}, ttl=60)
    await cache.set("two", b"2", {"kind": "test"}, ttl=60)
    await client.hset("other:key", {b"v": b"keep"})

    assert await cache.clear() == 2
    assert "other:key" in client.data
    assert await cache.get("one") is None


async def test_redis_cache_failures_are_contained(tmp_path):
    cache = RedisCache(_settings(tmp_path), client=BrokenRedis())
    assert await cache.get("missing") is None
    await cache.set("key", b"value", {"kind": "test"}, ttl=60)
    assert cache.errors >= 2
    assert cache.last_error is not None
    stats = await cache.stats_async()
    assert stats["errors"] >= 2


def test_build_cache_selects_backend(tmp_path):
    assert isinstance(build_cache(Settings(cache_dir=tmp_path, cache_backend="sqlite")), Cache)
    redis_cache = build_cache(Settings(cache_dir=tmp_path, cache_backend="redis"))
    assert isinstance(redis_cache, RedisCache)


def test_redis_cache_disabled_is_a_noop(tmp_path):
    cache = RedisCache(_settings(tmp_path, cache_enabled=False), client=FakeRedis())

    async def run():
        await cache.set("k", b"v", {"kind": "test"}, ttl=60)
        assert await cache.get("k") is None
        assert await cache.clear() == 0

    import asyncio

    asyncio.run(run())


@pytest.mark.parametrize("value", [b"", b"compressed payload"])
async def test_redis_payload_is_compressed(tmp_path, value):
    client = FakeRedis()
    cache = RedisCache(_settings(tmp_path), client=client)
    await cache.set("k", value, {"kind": "test"}, ttl=60)
    stored = client.data["weblens:cache:k"][b"v"]
    assert stored != value or value == b""


async def test_redis_large_payload_round_trip_uses_offload_path(tmp_path):
    client = FakeRedis()
    cache = RedisCache(_settings(tmp_path), client=client)
    value = b"x" * (70 * 1024)
    await cache.set("large", value, {"kind": "test"}, ttl=60)
    got = await cache.get("large")
    assert got is not None
    assert got[0] == value
