"""SQLite-backed cache with TTL, gzip payloads and content hashes.

Failures are contained: a broken cache must never break a request.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
import time
import zlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import Settings

if TYPE_CHECKING:
    from .redis_cache import RedisCache


class Cache:
    def __init__(self, settings: Settings):
        self.s = settings
        self.path = settings.cache_dir / "cache.sqlite3"
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self.hits = 0
        self.stale_hits = 0
        self.misses = 0
        self.errors = 0
        self.evictions = 0
        # In-memory logical byte total, kept consistent with the DB so that
        # eviction is O(1) instead of a full SUM scan on every write. Pre-existing
        # rows are counted once at open; uncounted rows are tolerated gracefully.
        self._bytes_used: int = 0
        if settings.cache_enabled:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=5)
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS kv (
                        k TEXT PRIMARY KEY,
                        kind TEXT NOT NULL,
                        value BLOB NOT NULL,
                        meta TEXT NOT NULL,
                        created REAL NOT NULL,
                        expires REAL NOT NULL
                    )
                    """
                )
                self._conn.execute("CREATE INDEX IF NOT EXISTS idx_kv_expires ON kv(expires)")
                self._conn.commit()
                with self._lock:
                    self._bytes_used = self._logical_size_locked()
                    try:
                        self._enforce_limit_locked()
                    except sqlite3.Error:
                        with contextlib.suppress(sqlite3.Error):
                            self._conn.rollback()
                        self.errors += 1
            except (sqlite3.Error, OSError):
                self.errors += 1
                self._conn = None
                self._bytes_used = 0

    # -- synchronous core, called via to_thread -------------------------
    def _get_sync(self, key: str) -> tuple[bytes, dict[str, Any], float] | None:
        if self._conn is None:
            return None
        with self._lock:
            row = self._conn.execute("SELECT value, meta, created, expires FROM kv WHERE k=?", (key,)).fetchone()
        if not row:
            return None
        value, meta, created, expires = row
        if expires < time.time():
            return None
        try:
            raw = zlib.decompress(value)
            meta_d = json.loads(meta)
        except (zlib.error, json.JSONDecodeError):
            return None
        return raw, meta_d, float(created)

    def _get_cached_sync(self, key: str, grace_s: float) -> tuple[bytes, dict[str, Any], float, bool] | None:
        """Return an entry that is fresh or expired within ``grace_s``."""
        if self._conn is None:
            return None
        with self._lock:
            row = self._conn.execute("SELECT value, meta, created, expires FROM kv WHERE k=?", (key,)).fetchone()
        if not row:
            return None
        value, meta, created, expires = row
        now = time.time()
        expires = float(expires)
        if expires + max(0.0, float(grace_s)) < now:
            return None
        try:
            raw = zlib.decompress(value)
            meta_d = json.loads(meta)
        except (zlib.error, json.JSONDecodeError):
            return None
        return raw, meta_d, float(created), expires < now

    def _set_sync(self, key: str, value: bytes, meta: dict[str, Any], ttl: float) -> None:
        if self._conn is None:
            return
        now = time.time()
        blob = zlib.compress(value, 6)
        meta_text = json.dumps(meta)
        with self._lock:
            # Replace: the old entry (if any) is removed before eviction, so
            # its bytes no longer count toward the cap.
            old = self._conn.execute("SELECT value, meta FROM kv WHERE k=?", (key,)).fetchone()
            if old:
                self._bytes_used -= len(old[0]) + len(old[1])
            self._conn.execute(
                "INSERT OR REPLACE INTO kv(k, kind, value, meta, created, expires) VALUES(?,?,?,?,?,?)",
                (key, str(meta.get("kind", "")), blob, meta_text, now, now + ttl),
            )
            self._bytes_used += len(blob) + len(meta_text)
            self._conn.commit()
            try:
                self._enforce_limit_locked()
            except sqlite3.Error:
                with contextlib.suppress(sqlite3.Error):
                    self._conn.rollback()
                self.errors += 1

    def _logical_size_locked(self) -> int:
        if self._conn is None:
            return 0
        row = self._conn.execute("SELECT COALESCE(SUM(LENGTH(value) + LENGTH(meta)), 0) FROM kv").fetchone()
        return int(row[0]) if row else 0

    def _enforce_limit_locked(self) -> int:
        """Evict oldest entries until the logical payload is under the cap."""
        cap = self.s.cache_max_bytes
        if self._conn is None or cap <= 0:
            return 0
        # Reconcile once in case external writes or DDL changed the table.
        self._bytes_used = self._logical_size_locked()
        if self._bytes_used <= cap:
            return 0
        rows = self._conn.execute("SELECT k, value, meta FROM kv ORDER BY created ASC").fetchall()
        evicted = 0
        for key, blob, meta_text in rows:
            if self._bytes_used <= cap:
                break
            self._conn.execute("DELETE FROM kv WHERE k=?", (key,))
            self._bytes_used -= len(blob) + len(meta_text)
            evicted += 1
        if evicted:
            self._conn.commit()
            self.evictions += evicted
        return evicted

    def _purge_sync(self) -> int:
        if self._conn is None:
            return 0
        with self._lock:
            cur = self._conn.execute("DELETE FROM kv WHERE expires < ?", (time.time(),))
            self._conn.commit()
            removed = cur.rowcount
            if removed:
                self._bytes_used = self._logical_size_locked()
            return removed

    def _clear_sync(self) -> int:
        if self._conn is None:
            return 0
        with self._lock:
            cur = self._conn.execute("DELETE FROM kv")
            self._conn.commit()
            removed = cur.rowcount
            if removed:
                self._bytes_used = 0
            return removed

    # -- async wrappers --------------------------------------------------
    async def get(self, key: str) -> tuple[bytes, dict[str, Any], float] | None:
        try:
            import anyio

            out = await anyio.to_thread.run_sync(self._get_sync, key)
        except Exception:
            self.errors += 1
            return None
        if out is None:
            self.misses += 1
        else:
            self.hits += 1
        return out

    async def get_cached(self, key: str, grace_s: float = 0.0) -> tuple[bytes, dict[str, Any], float, bool] | None:
        """Return ``(value, meta, created, expired)`` or ``None``.

        Unlike :meth:`get`, this can return an entry whose TTL has passed as
        long as it is still inside ``grace_s``. The fourth item tells the
        caller whether the value is stale.
        """
        try:
            import anyio

            out = await anyio.to_thread.run_sync(self._get_cached_sync, key, grace_s)
        except Exception:
            self.errors += 1
            return None
        if out is None:
            self.misses += 1
        elif out[3]:
            self.stale_hits += 1
        else:
            self.hits += 1
        return out

    async def get_json(self, key: str) -> tuple[Any, dict[str, Any], float] | None:
        got = await self.get(key)
        if got is None:
            return None
        raw, meta, created = got
        try:
            return json.loads(raw), meta, created
        except json.JSONDecodeError:
            return None

    async def set(self, key: str, value: bytes, meta: dict[str, Any], ttl: float | None = None) -> None:
        try:
            import anyio

            await anyio.to_thread.run_sync(self._set_sync, key, value, meta, 600.0 if ttl is None else ttl)
        except Exception:
            self.errors += 1

    async def set_json(self, key: str, obj: Any, meta: dict[str, Any], ttl: float | None = None) -> None:
        await self.set(key, json.dumps(obj, separators=(",", ":")).encode(), meta, ttl)

    async def purge(self) -> int:
        try:
            import anyio

            return await anyio.to_thread.run_sync(self._purge_sync)
        except Exception:
            self.errors += 1
            return 0

    async def clear(self) -> int:
        try:
            import anyio

            return int(await anyio.to_thread.run_sync(self._clear_sync))
        except Exception:
            self.errors += 1
            return 0

    def stats(self) -> dict[str, int | float | bool | str | None]:
        total = self.hits + self.misses
        entries = 0
        logical_bytes = 0
        if self._conn is not None:
            try:
                with self._lock:
                    row = self._conn.execute(
                        "SELECT COUNT(*), COALESCE(SUM(LENGTH(value) + LENGTH(meta)), 0) FROM kv"
                    ).fetchone()
                if row:
                    entries, logical_bytes = int(row[0]), int(row[1])
                    self._bytes_used = logical_bytes
            except sqlite3.Error:
                self.errors += 1
        file_bytes = 0
        for suffix in ("", "-wal"):
            try:
                file_bytes += Path(f"{self.path}{suffix}").stat().st_size
            except OSError:
                pass
        return {
            "enabled": self._conn is not None,
            "backend": "sqlite",
            "shared": False,
            "hits": self.hits,
            "stale_hits": self.stale_hits,
            "misses": self.misses,
            "hit_rate_pct": round(100 * self.hits / total, 1) if total else 0.0,
            "errors": self.errors,
            "evictions": self.evictions,
            "entries": entries,
            "bytes": logical_bytes,
            "file_bytes": file_bytes,
            "max_bytes": self.s.cache_max_bytes,
        }

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None

    async def aclose(self) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - interpreter shutdown
        try:
            self.close()
        except Exception:
            pass


def build_cache(settings: Settings) -> Cache | RedisCache:
    """Select the configured cache backend without importing Redis by default."""

    if settings.cache_backend == "redis":
        from .redis_cache import RedisCache as RedisCacheBackend

        return RedisCacheBackend(settings)
    return Cache(settings)


def cache_key(*parts: str) -> str:
    import hashlib

    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", "replace"))
        h.update(b"\x00")
    return h.hexdigest()


def content_path(settings: Settings) -> Path:
    return settings.cache_dir / "pages"
