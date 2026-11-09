"""Coverage for RedisCache error/degradation paths.

Uses in-memory fakes (no Redis server): import-missing fallback, client
construction failure, corrupt payloads, non-dict metadata, expired delete,
closed-client behaviour and stats.
"""

from __future__ import annotations

import time

import pytest

from weblens.config import Settings
from weblens.redis_cache import RedisCache, _as_bytes, _as_text, _field


class FakeRedis:
    def __init__(self):
        self.data: dict[str, dict[bytes, bytes]] = {}
        self.expires: dict[str, float] = {}
        self.raise_on: set[str] = set()

    async def hset(self, key, *, mapping):
        if "hset" in self.raise_on:
            raise RuntimeError("hset failed")
        self.data.setdefault(key, {}).update(mapping)
        return 1

    async def hgetall(self, key):
        if "hgetall" in self.raise_on:
            raise RuntimeError("hgetall failed")
        return dict(self.data.get(key, {}))

    async def expire(self, key, ttl):
        if "expire" in self.raise_on:
            raise RuntimeError("expire failed")
        self.expires[key] = time.time() + ttl
        return 1

    async def delete(self, *keys):
        if "delete" in self.raise_on:
            raise RuntimeError("delete failed")
        removed = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                self.expires.pop(key, None)
                removed += 1
        return removed

    async def aclose(self):
        self.data.clear()


def _cache(tmp_path, **kw) -> RedisCache:
    settings = Settings(cache_dir=tmp_path, redis_url="redis://localhost:6379/0", **kw)
    return RedisCache(settings, client=FakeRedis())


@pytest.mark.asyncio
async def test_set_then_get_roundtrip_compresses_and_stores_meta(tmp_path):
    cache = _cache(tmp_path)
    try:
        await cache.set("k1", b"payload", {"kind": "http"}, ttl=60)
        got = await cache.get("k1")
        assert got is not None
        value, meta, created = got
        assert value == b"payload"
        assert meta["kind"] == "http"
        assert created <= time.time()
    finally:
        cache.close()


@pytest.mark.asyncio
async def test_get_missing_key_returns_none(tmp_path):
    cache = _cache(tmp_path)
    try:
        assert await cache.get("absent") is None
    finally:
        cache.close()


@pytest.mark.asyncio
async def test_storage_errors_degrade_to_miss(tmp_path):
    cache = _cache(tmp_path)
    cache._client.raise_on = {"hset", "hgetall"}
    try:
        await cache.set("k", b"v", {}, ttl=30)
        assert await cache.get("k") is None
        assert cache.errors >= 1
    finally:
        cache.close()


@pytest.mark.asyncio
async def test_corrupt_metadata_is_discarded(tmp_path):
    cache = _cache(tmp_path)
    try:
        await cache.set("k", b"value", {"kind": "x"}, ttl=60)
        stored_key = cache._key("k")
        # Corrupt the metadata field so JSON parsing fails.
        cache._client.data[stored_key][b"m"] = b"not-json"
        assert await cache.get("k") is None
        assert cache.errors >= 1
    finally:
        cache.close()


@pytest.mark.asyncio
async def test_non_dict_metadata_is_rejected(tmp_path):
    import json

    cache = _cache(tmp_path)
    try:
        await cache.set("k", b"value", {}, ttl=60)
        stored_key = cache._key("k")
        cache._client.data[stored_key][b"m"] = json.dumps(["not", "a", "dict"]).encode()
        assert await cache.get("k") is None
        assert cache.errors >= 1
    finally:
        cache.close()


@pytest.mark.asyncio
async def test_expired_entry_beyond_grace_is_deleted(tmp_path):
    cache = _cache(tmp_path, cache_stale_grace_s=0.0)
    try:
        await cache.set("k", b"value", {}, ttl=1)
        stored_key = cache._key("k")
        cache._client.data[stored_key][b"e"] = str(time.time() - 3600).encode()
        assert await cache.get("k") is None
        assert stored_key not in cache._client.data
    finally:
        cache.close()


@pytest.mark.asyncio
async def test_stale_entry_within_grace_is_served(tmp_path):
    cache = _cache(tmp_path, cache_stale_grace_s=3600.0)
    try:
        await cache.set("k", b"value", {}, ttl=1)
        stored_key = cache._key("k")
        cache._client.data[stored_key][b"e"] = str(time.time() - 60).encode()
        # Stale entries are only served through the explicit grace-aware API;
        # get() keeps strict expiry semantics.
        served = await cache.get_cached("k", grace_s=3600.0)
        assert served is not None
        value, _meta, _created, expired = served
        assert value == b"value"
        assert expired is True
        assert cache.stale_hits == 1
    finally:
        cache.close()


@pytest.mark.asyncio
async def test_disabled_cache_is_a_miss(tmp_path):
    settings = Settings(cache_dir=tmp_path, redis_url="redis://localhost:6379/0", cache_enabled=False)
    cache = RedisCache(settings)
    try:
        await cache.set("k", b"v", {}, ttl=30)
        assert await cache.get("k") is None
    finally:
        cache.close()


@pytest.mark.asyncio
async def test_close_is_idempotent(tmp_path):
    cache = _cache(tmp_path)
    cache.close()
    cache.close()


def test_field_and_coercion_helpers():
    raw = {b"v": b"value", b"m": b"meta", "c": "created"}
    assert _field(raw, "v") == b"value"
    assert _field(raw, "m") == b"meta"
    assert _field(raw, "c") == "created"
    assert _field(raw, "absent") is None

    assert _as_bytes(b"x") == b"x"
    assert _as_bytes("x") == b"x"
    assert _as_bytes(bytearray(b"x")) == b"x"

    assert _as_text(b"text") == "text"
    assert _as_text("text") == "text"
