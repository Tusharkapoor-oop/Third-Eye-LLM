"""SQLite-backed cache with TTL, gzip payloads and content hashes.

Failures are contained: a broken cache must never break a request.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import zlib
from pathlib import Path
from typing import Any

from .config import Settings


class Cache:
    def __init__(self, settings: Settings):
        self.s = settings
        self.path = settings.cache_dir / "cache.sqlite3"
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self.hits = 0
        self.misses = 0
        self.errors = 0
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
            except (sqlite3.Error, OSError):
                self.errors += 1
                self._conn = None

    # -- synchronous core, called via to_thread -------------------------
    def _get_sync(self, key: str) -> tuple[bytes, dict[str, Any], float] | None:
        if self._conn is None:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT value, meta, created, expires FROM kv WHERE k=?", (key,)
            ).fetchone()
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

    def _set_sync(self, key: str, value: bytes, meta: dict[str, Any], ttl: float) -> None:
        if self._conn is None:
            return
        now = time.time()
        blob = zlib.compress(value, 6)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO kv(k, kind, value, meta, created, expires) "
                "VALUES(?,?,?,?,?,?)",
                (key, str(meta.get("kind", "")), blob, json.dumps(meta), now, now + ttl),
            )
            self._conn.commit()

    def _purge_sync(self) -> int:
        if self._conn is None:
            return 0
        with self._lock:
            cur = self._conn.execute("DELETE FROM kv WHERE expires < ?", (time.time(),))
            self._conn.commit()
            return cur.rowcount

    def _clear_sync(self) -> None:
        if self._conn is None:
            return
        with self._lock:
            self._conn.execute("DELETE FROM kv")
            self._conn.commit()

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

    async def get_json(self, key: str) -> tuple[Any, dict[str, Any], float] | None:
        got = await self.get(key)
        if got is None:
            return None
        raw, meta, created = got
        try:
            return json.loads(raw), meta, created
        except json.JSONDecodeError:
            return None

    async def set(
        self, key: str, value: bytes, meta: dict[str, Any], ttl: float | None = None
    ) -> None:
        try:
            import anyio

            await anyio.to_thread.run_sync(self._set_sync, key, value, meta, ttl or 600.0)
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

    async def clear(self) -> None:
        try:
            import anyio

            await anyio.to_thread.run_sync(self._clear_sync)
        except Exception:
            self.errors += 1

    def stats(self) -> dict[str, int | bool]:
        total = self.hits + self.misses
        return {
            "enabled": self._conn is not None,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_pct": round(100 * self.hits / total, 1) if total else 0,
            "errors": self.errors,
        }

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None

    def __del__(self) -> None:  # pragma: no cover - interpreter shutdown
        try:
            self.close()
        except Exception:
            pass


def cache_key(*parts: str) -> str:
    import hashlib

    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", "replace"))
        h.update(b"\x00")
    return h.hexdigest()


def content_path(settings: Settings) -> Path:
    return settings.cache_dir / "pages"
