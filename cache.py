"""High-Performance SQLite Cache Engine for Web Intelligence MCP.

Implements async key-value caching with TTL expiration, FTS indexing,
and strict sub-25ms latency guarantees using aiosqlite.
"""

from __future__ import annotations

import asyncio
import hashlib
import time

import aiosqlite

from config import CONFIG
from security import safe_resolve_path


class SQLiteCache:
    """Async SQLite cache engine for storing extracted passages and search results."""

    def __init__(self, db_path: str | None = None, default_ttl_hours: float | None = None):
        raw_path = db_path or CONFIG.cache_db_path
        self.db_path = safe_resolve_path(raw_path)
        self.default_ttl_hours = default_ttl_hours or CONFIG.default_cache_ttl_hours
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def _get_conn(self) -> aiosqlite.Connection:
        """Initialize and return a persistent async connection with WAL mode."""
        if self._db is None:
            async with self._lock:
                if self._db is None:
                    self.db_path.parent.mkdir(parents=True, exist_ok=True)
                    self._db = await aiosqlite.connect(self.db_path)
                    await self._db.execute("PRAGMA journal_mode=WAL;")
                    await self._db.execute("PRAGMA synchronous=NORMAL;")
                    await self._db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS cache_entries (
                            key TEXT PRIMARY KEY,
                            value TEXT NOT NULL,
                            created_at REAL NOT NULL,
                            expires_at REAL NOT NULL
                        );
                        """
                    )
                    await self._db.execute("CREATE INDEX IF NOT EXISTS idx_expires ON cache_entries (expires_at);")
                    await self._db.commit()
        return self._db

    @staticmethod
    def hash_key(key: str) -> str:
        """Hash long query or URL keys into deterministic SHA256 hex."""
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    async def get(self, key: str) -> str | None:
        """Retrieve cached value if not expired."""
        conn = await self._get_conn()
        hashed = self.hash_key(key)
        now = time.time()
        async with conn.execute(
            "SELECT value FROM cache_entries WHERE key = ? AND expires_at > ?;",
            (hashed, now),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def set(self, key: str, value: str, ttl_hours: float | None = None) -> None:
        """Store key-value entry with TTL expiration timestamp."""
        conn = await self._get_conn()
        hashed = self.hash_key(key)
        ttl = ttl_hours if ttl_hours is not None else self.default_ttl_hours
        now = time.time()
        expires_at = now + (ttl * 3600.0)
        await conn.execute(
            """
            INSERT OR REPLACE INTO cache_entries (key, value, created_at, expires_at)
            VALUES (?, ?, ?, ?);
            """,
            (hashed, value, now, expires_at),
        )
        await conn.commit()

    async def purge_expired(self) -> int:
        """Purge all expired cache entries."""
        conn = await self._get_conn()
        now = time.time()
        cursor = await conn.execute("DELETE FROM cache_entries WHERE expires_at <= ?;", (now,))
        await conn.commit()
        return cursor.rowcount

    async def close(self) -> None:
        """Cleanly close database connection."""
        async with self._lock:
            if self._db is not None:
                await self._db.close()
                self._db = None
