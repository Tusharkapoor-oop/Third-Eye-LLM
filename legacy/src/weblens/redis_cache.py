"""Optional Redis cache backend for multi-instance deployments.

The public surface mirrors :class:`weblens.cache.Cache`: bytes plus metadata,
TTL, compressed payloads, and contained failures.  A Redis outage is a cache
miss, never a request failure.  The ``redis`` package is an optional extra.
"""

from __future__ import annotations

import inspect
import json
import math
import time
import zlib
from typing import Any

from .config import Settings

_OFFLOAD_THRESHOLD = 64 * 1024


async def _compress(value: bytes) -> bytes:
    if len(value) < _OFFLOAD_THRESHOLD:
        return zlib.compress(value, 6)
    import anyio

    return await anyio.to_thread.run_sync(zlib.compress, value, 6)


async def _decompress(blob: bytes) -> bytes:
    if len(blob) < _OFFLOAD_THRESHOLD:
        return zlib.decompress(blob)
    import anyio

    return await anyio.to_thread.run_sync(zlib.decompress, blob)


def _field(mapping: dict[Any, Any], name: str) -> Any:
    for key in (name.encode("utf-8"), name):
        if key in mapping:
            return mapping[key]
    return None


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8")
    raise TypeError(f"unexpected Redis field type: {type(value)!r}")


def _as_text(value: Any) -> str:
    return _as_bytes(value).decode("utf-8")


class RedisCache:
    """Redis-backed cache with the same call shape as the SQLite cache."""

    def __init__(self, settings: Settings, client: Any | None = None):
        self.s = settings
        self._client = client
        self._owns_client = client is None
        self._closed = False
        self._import_error: str | None = None
        self.last_error: str | None = None
        self._prefix = f"{settings.redis_namespace}:cache:"
        self.hits = 0
        self.stale_hits = 0
        self.misses = 0
        self.errors = 0
        self.evictions = 0

    @property
    def enabled(self) -> bool:
        return bool(self.s.cache_enabled) and not self._closed

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def _fail(self, exc: Exception) -> None:
        self.errors += 1
        self.last_error = f"{type(exc).__name__}: {str(exc)[:180]}"

    def _client_or_none(self) -> Any | None:
        if not self.enabled:
            return None
        if self._client is not None:
            return self._client
        if self._import_error is not None:
            return None
        try:
            from redis.asyncio import Redis  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            self._import_error = str(exc)
            self._fail(exc)
            return None
        try:
            self._client = Redis.from_url(
                self.s.redis_url,
                socket_timeout=self.s.redis_socket_timeout_s,
                socket_connect_timeout=self.s.redis_socket_timeout_s,
                max_connections=self.s.redis_max_connections,
                decode_responses=False,
            )
        except Exception as exc:  # pragma: no cover - malformed URL / client init
            self._fail(exc)
            return None
        return self._client

    async def _load(self, key: str) -> tuple[Any, bytes, str, float, float] | None:
        """Read and parse a hash without enforcing the logical TTL."""
        client = self._client_or_none()
        if client is None:
            return None
        try:
            raw = await client.hgetall(self._key(key))
        except Exception as exc:
            self._fail(exc)
            return None
        if not raw:
            return None
        try:
            blob = _as_bytes(_field(raw, "v"))
            meta_raw = _as_text(_field(raw, "m"))
            created = float(_as_text(_field(raw, "c")))
            expires = float(_as_text(_field(raw, "e")))
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            self._fail(exc)
            return None
        return client, blob, meta_raw, created, expires

    async def _delete_expired(self, client: Any, key: str, expires: float) -> None:
        if expires + max(0.0, float(self.s.cache_stale_grace_s)) > time.time():
            return
        try:
            await client.delete(self._key(key))
        except Exception as exc:
            self._fail(exc)

    async def _decode(self, blob: bytes, meta_raw: str) -> tuple[bytes, dict[str, Any]] | None:
        try:
            value = await _decompress(blob)
            meta = json.loads(meta_raw)
        except (zlib.error, json.JSONDecodeError) as exc:
            self._fail(exc)
            return None
        if not isinstance(meta, dict):
            self.errors += 1
            return None
        return value, meta

    async def get(self, key: str) -> tuple[bytes, dict[str, Any], float] | None:
        loaded = await self._load(key)
        if loaded is None:
            self.misses += 1
            return None
        client, blob, meta_raw, created, expires = loaded
        if expires <= time.time():
            # Redis TTL normally removes this key; the guard also covers a
            # server with expiry disabled and keeps parity with SQLite. When a
            # stale grace period is configured the key is kept for the
            # fallback path instead of being deleted immediately.
            await self._delete_expired(client, key, expires)
            self.misses += 1
            return None
        decoded = await self._decode(blob, meta_raw)
        if decoded is None:
            return None
        self.hits += 1
        return decoded[0], decoded[1], created

    async def get_cached(self, key: str, grace_s: float = 0.0) -> tuple[bytes, dict[str, Any], float, bool] | None:
        """Return ``(value, meta, created, expired)`` or ``None``."""
        loaded = await self._load(key)
        if loaded is None:
            self.misses += 1
            return None
        client, blob, meta_raw, created, expires = loaded
        now = time.time()
        if expires + max(0.0, float(grace_s)) < now:
            await self._delete_expired(client, key, expires)
            self.misses += 1
            return None
        decoded = await self._decode(blob, meta_raw)
        if decoded is None:
            return None
        expired = expires < now
        if expired:
            self.stale_hits += 1
        else:
            self.hits += 1
        return decoded[0], decoded[1], created, expired

    async def get_json(self, key: str) -> tuple[Any, dict[str, Any], float] | None:
        got = await self.get(key)
        if got is None:
            return None
        raw, meta, created = got
        try:
            return json.loads(raw), meta, created
        except json.JSONDecodeError:
            self.errors += 1
            return None

    async def set(self, key: str, value: bytes, meta: dict[str, Any], ttl: float | None = None) -> None:
        ttl = 600.0 if ttl is None else float(ttl)
        if ttl <= 0:
            await self._delete(key)
            return
        client = self._client_or_none()
        if client is None:
            return
        now = time.time()
        mapping = {
            b"v": await _compress(value),
            b"m": json.dumps(meta, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            b"c": str(now).encode("ascii"),
            b"e": str(now + ttl).encode("ascii"),
        }
        redis_key = self._key(key)
        # Keep HTTP keys alive past their logical expiry so the stale fallback
        # can use them when a live refetch fails. Other cache kinds keep their
        # normal TTL; the logical expiry remains in the ``e`` field and is
        # enforced by get()/get_cached().
        grace = max(0, int(self.s.cache_stale_grace_s)) if meta.get("kind") == "http" else 0
        server_ttl = ttl + grace
        try:
            pipeline = getattr(client, "pipeline", None)
            if pipeline is not None:
                pipe = pipeline(transaction=False)
                pipe.hset(redis_key, mapping=mapping)
                pipe.expire(redis_key, max(1, math.ceil(server_ttl)))
                await pipe.execute()
            else:  # pragma: no cover - minimal clients / tests
                await client.hset(redis_key, mapping=mapping)
                await client.expire(redis_key, max(1, math.ceil(server_ttl)))
        except Exception as exc:
            self._fail(exc)

    async def set_json(self, key: str, obj: Any, meta: dict[str, Any], ttl: float | None = None) -> None:
        await self.set(
            key,
            json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            meta,
            ttl,
        )

    async def _delete(self, key: str) -> None:
        client = self._client_or_none()
        if client is None:
            return
        try:
            await client.delete(self._key(key))
        except Exception as exc:
            self._fail(exc)

    async def purge(self) -> int:
        # Redis expires keys itself. A full scan on every purge would turn a
        # maintenance command into an O(keyspace) operation, so report zero and
        # leave expiry to the server.
        return 0

    async def _scan_keys(self, client: Any):
        match = f"{self._prefix}*"
        scan_iter = getattr(client, "scan_iter", None)
        if scan_iter is not None:
            async for key in scan_iter(match=match, count=500):
                yield key
            return
        keys = await client.keys(match)  # pragma: no cover - fallback for fakes
        for key in keys:
            yield key

    async def clear(self) -> int:
        client = self._client_or_none()
        if client is None:
            return 0
        removed = 0
        batch: list[Any] = []
        try:
            async for key in self._scan_keys(client):
                batch.append(key)
                if len(batch) >= 500:
                    removed += int(await client.delete(*batch))
                    batch.clear()
            if batch:
                removed += int(await client.delete(*batch))
        except Exception as exc:
            self._fail(exc)
        return removed

    def stats(self) -> dict[str, Any]:
        total = self.hits + self.misses
        return {
            "enabled": self.enabled,
            "backend": "redis",
            "shared": True,
            "hits": self.hits,
            "stale_hits": self.stale_hits,
            "misses": self.misses,
            "hit_rate_pct": round(100 * self.hits / total, 1) if total else 0.0,
            "errors": self.errors,
            "evictions": self.evictions,
            "entries": None,
            "bytes": None,
            "file_bytes": None,
            "max_bytes": self.s.cache_max_bytes,
            "last_error": self.last_error,
        }

    async def stats_async(self) -> dict[str, Any]:
        out = self.stats()
        client = self._client_or_none()
        if client is None:
            out["entries"] = 0
            return out
        count = 0
        truncated = False
        try:
            async for _ in self._scan_keys(client):
                count += 1
                if count >= 100_000:
                    truncated = True
                    break
        except Exception as exc:
            self._fail(exc)
            out["errors"] = self.errors
            out["last_error"] = self.last_error
        out["entries"] = count
        out["truncated"] = truncated
        return out

    async def aclose(self) -> None:
        self._closed = True
        client = self._client
        self._client = None
        if client is None or not self._owns_client:
            return
        closer = getattr(client, "aclose", None) or getattr(client, "close", None)
        if closer is None:
            return
        try:
            result = closer()
            if inspect.isawaitable(result):
                await result
        except Exception as exc:  # pragma: no cover - interpreter shutdown path
            self.last_error = f"{type(exc).__name__}: {str(exc)[:180]}"

    def close(self) -> None:
        # The async close path is authoritative. This exists so callers that
        # only know the SQLite interface cannot crash during cleanup.
        self._closed = True

    def __del__(self) -> None:  # pragma: no cover - interpreter shutdown
        try:
            self.close()
        except Exception:
            pass
