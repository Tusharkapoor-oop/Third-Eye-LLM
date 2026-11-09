"""Failure-path coverage for the SQLite and Redis cache backends.

The cache is deliberately allowed to fail without breaking a request, so these
tests exercise corrupt rows, close errors, optional-dependency gaps and the
batch/scan paths that normal happy-path tests never reach.
"""

from __future__ import annotations

import sqlite3
import time
import zlib

import pytest

from weblens.cache import Cache, build_cache, cache_key, content_path
from weblens.config import Settings
from weblens.redis_cache import RedisCache, _as_bytes, _compress, _decompress, _field


def _settings(tmp_path, **kwargs) -> Settings:
    kwargs.setdefault("cache_dir", tmp_path / "cache")
    kwargs.setdefault("cache_enabled", True)
    return Settings(**kwargs)


def _redis_cache(tmp_path, client) -> RedisCache:
    return RedisCache(_settings(tmp_path, cache_backend="redis"), client=client)


class FakeRedis:
    def __init__(self):
        self.data: dict[str, dict[bytes, bytes]] = {}
        self.deleted: list[tuple[str, ...]] = []
        self.scan_error: Exception | None = None
        self.delete_error: Exception | None = None
        self.hgetall_error: Exception | None = None
        self.keys_result: list[str] | None = None

    async def hset(self, key, *, mapping):
        self.data.setdefault(key, {}).update(mapping)
        return 1

    async def hgetall(self, key):
        if self.hgetall_error is not None:
            raise self.hgetall_error
        return dict(self.data.get(key, {}))

    async def expire(self, key, ttl):
        return 1

    async def delete(self, *keys):
        self.deleted.append(keys)
        if self.delete_error is not None:
            raise self.delete_error
        removed = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                removed += 1
        return removed

    async def scan_iter(self, match=None, count=None):
        if self.scan_error is not None:
            raise self.scan_error
        for key in list(self.data):
            yield key

    async def aclose(self):
        return None


def test_cache_disabled_helpers_and_content_path(tmp_path):
    s = _settings(tmp_path, cache_enabled=False)
    c = Cache(s)
    assert c._get_sync("x") is None
    assert c._get_cached_sync("x", 0) is None
    assert c._logical_size_locked() == 0
    assert c._purge_sync() == 0
    assert c._clear_sync() == 0
    assert content_path(s) == s.cache_dir / "pages"
    assert cache_key("a", "b") != cache_key("a", "c")
    assert build_cache(s) is not None
    c.close()


def test_cache_corrupt_rows_return_none(tmp_path):
    c = Cache(_settings(tmp_path))
    with c._lock:
        c._conn.execute(
            "INSERT INTO kv(k, kind, value, meta, created, expires) VALUES(?,?,?,?,?,?)",
            ("bad-zlib", "x", b"not-zlib", "{}", time.time(), time.time() + 60),
        )
        c._conn.execute(
            "INSERT INTO kv(k, kind, value, meta, created, expires) VALUES(?,?,?,?,?,?)",
            ("bad-meta", "x", zlib.compress(b"value"), "not-json", time.time(), time.time() + 60),
        )
        c._conn.commit()
    assert c._get_sync("bad-zlib") is None
    assert c._get_sync("bad-meta") is None
    assert c._get_cached_sync("bad-zlib", 0) is None
    assert c._get_cached_sync("bad-meta", 0) is None
    c.close()


async def test_cache_json_and_file_stats(tmp_path):
    c = Cache(_settings(tmp_path))
    await c.set_json("json", {"a": 1}, {"kind": "json"}, ttl=60)
    assert (await c.get_json("json"))[0] == {"a": 1}
    await c.set("not-json", b"not-json", {"kind": "raw"}, ttl=60)
    assert await c.get_json("not-json") is None
    stats = c.stats()
    assert stats["entries"] >= 2
    assert stats["file_bytes"] >= 0
    c.close()
    c.close()


async def test_cache_wrapper_errors_are_contained(tmp_path, monkeypatch):
    c = Cache(_settings(tmp_path))
    import anyio

    async def boom(*args, **kwargs):
        raise RuntimeError("thread failed")

    monkeypatch.setattr(anyio.to_thread, "run_sync", boom)
    assert await c.get("x") is None
    assert await c.get_cached("x") is None
    await c.set("x", b"v", {})
    assert await c.purge() == 0
    assert await c.clear() == 0
    assert c.errors >= 5
    c.close()


def test_cache_enforce_limit_errors_are_counted(tmp_path, monkeypatch):
    def boom(self):
        raise sqlite3.Error("limit failed")

    monkeypatch.setattr(Cache, "_enforce_limit_locked", boom)
    c = Cache(_settings(tmp_path))
    assert c.errors >= 1
    c._set_sync("x", b"v", {}, 60)
    assert c.errors >= 2
    c.close()


def test_cache_stats_and_close_sqlite_errors(tmp_path):
    class BrokenConn:
        def execute(self, *args, **kwargs):
            raise sqlite3.Error("broken")

        def close(self):
            raise sqlite3.Error("close failed")

    c = Cache(_settings(tmp_path))
    original = c._conn
    c._conn = BrokenConn()  # type: ignore[assignment]
    stats = c.stats()
    assert stats["entries"] == 0
    assert c.errors >= 1
    c.close()
    assert c._conn is None
    if original is not None:
        original.close()


async def test_redis_helpers_large_values_and_fields(tmp_path):
    payload = b"x" * (64 * 1024 + 1)
    assert await _decompress(zlib.compress(payload)) == payload
    assert _field({}, "missing") is None
    assert _as_bytes(bytearray(b"ab")) == b"ab"
    assert _as_bytes("ab") == b"ab"
    with pytest.raises(TypeError):
        _as_bytes(1)
    assert _redis_cache(tmp_path, FakeRedis())._client_or_none() is not None


async def test_redis_compress_decompress_large_roundtrip():
    payload = b"a" * (64 * 1024 + 10)
    blob = await _compress(payload)
    assert await _decompress(blob) == payload


def _row(value: bytes, meta: str = "{}", *, created: float | None = None, expires: float | None = None):
    now = time.time()
    return {
        b"v": zlib.compress(value),
        b"m": meta.encode(),
        b"c": str(now if created is None else created).encode(),
        b"e": str(now + 60 if expires is None else expires).encode(),
    }


async def test_redis_load_and_decode_failures(tmp_path):
    client = FakeRedis()
    cache = _redis_cache(tmp_path, client)
    client.hgetall_error = RuntimeError("down")
    assert await cache._load("x") is None
    assert cache.errors >= 1

    client.hgetall_error = None
    client.data["weblens:cache:bad"] = {b"v": b"x", b"m": b"{}", b"c": b"x", b"e": b"x"}
    assert await cache._load("bad") is None
    assert cache.errors >= 2

    client.data["weblens:cache:list"] = _row(b"value", "[]")
    assert await cache.get("list") is None
    assert cache.errors >= 3


async def test_redis_expired_delete_error_and_no_client(tmp_path):
    client = FakeRedis()
    cache = RedisCache(_settings(tmp_path, cache_backend="redis", cache_stale_grace_s=0), client=client)
    client.data["weblens:cache:old"] = _row(b"value", expires=time.time() - 10)
    client.delete_error = RuntimeError("delete failed")
    assert await cache.get("old") is None
    assert cache.errors >= 1
    assert cache.misses >= 1

    cache._closed = True
    await cache.set("x", b"v", {}, ttl=0)
    assert await cache.clear() == 0
    assert await cache.stats_async() == {
        "enabled": False,
        "backend": "redis",
        "shared": True,
        "hits": 0,
        "stale_hits": 0,
        "misses": 1,
        "hit_rate_pct": 0.0,
        "errors": 1,
        "evictions": 0,
        "entries": 0,
        "bytes": None,
        "file_bytes": None,
        "max_bytes": cache.s.cache_max_bytes,
        "last_error": cache.last_error,
    }


async def test_redis_get_cached_miss_json_error_and_zero_ttl(tmp_path):
    client = FakeRedis()
    cache = _redis_cache(tmp_path, client)
    assert await cache.get_cached("missing") is None
    assert cache.misses == 1

    await cache.set("raw", b"not-json", {"kind": "raw"}, ttl=60)
    assert await cache.get_json("raw") is None
    assert cache.errors >= 1

    client.data["weblens:cache:zero"] = _row(b"value")
    client.deleted.clear()
    await cache.set("zero", b"value", {}, ttl=0)
    assert client.deleted


async def test_redis_clear_batches_and_scan_error(tmp_path):
    client = FakeRedis()
    cache = _redis_cache(tmp_path, client)
    for i in range(501):
        client.data[f"weblens:cache:{i}"] = _row(b"v")
    assert await cache.clear() == 501
    assert len(client.deleted) == 2

    client.data["weblens:cache:x"] = _row(b"v")
    client.scan_error = RuntimeError("scan failed")
    assert await cache.clear() == 0
    assert cache.errors >= 1


async def test_redis_aclose_branches(tmp_path):
    class NoCloser:
        pass

    cache = RedisCache(_settings(tmp_path, cache_backend="redis"), client=None)
    cache._client = NoCloser()
    cache._owns_client = True
    await cache.aclose()
    assert cache._closed is True

    cache = _redis_cache(tmp_path, FakeRedis())
    cache._owns_client = False
    cache._client = FakeRedis()
    await cache.aclose()
    assert cache._client is None

    cache = _redis_cache(tmp_path, None)
    await cache.aclose()
    assert cache._closed is True
