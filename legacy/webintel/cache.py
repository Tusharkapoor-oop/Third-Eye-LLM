"""SQLite TTL cache (stdlib only). Two tiers:
  - search results keyed by provider+query+params
  - fetched HTML keyed by normalized URL (lets extract re-chunk cheaply)
Also tracks instrumentation: hits/misses written into returned payloads?No - into
engine telemetry only (bench reads via OpenTelemetry-free counters)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import pathlib
from typing import Any, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
  k TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  ts REAL NOT NULL,
  payload BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cache_kind_ts ON cache(kind, ts);
"""


class Cache:
    def __init__(self, path: pathlib.Path):
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        conn: Optional[sqlite3.Connection] = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # isolation_level=None => real autocommit; without it each execute opens an
            # implicit transaction that never commits, and OTHER PROCESSES see nothing.
            conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)
        except (sqlite3.Error, OSError):
            # A read-only or otherwise unusable cache directory must degrade to
            # a cache miss, not prevent the MCP server from starting.
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            return
        self._conn = conn

    def get(self, kind: str, key: str, ttl: int) -> Optional[Any]:
        if self._conn is None:
            self.misses += 1
            return None
        now = time.time()
        k = f"{kind}:{key}"
        with self._lock:
            row = self._conn.execute(
                "SELECT ts, payload FROM cache WHERE k = ?", (k,)).fetchone()
        if row:
            ts, blob = float(row[0]), row[1]
            if ttl < 0:
                return None          # caller asserts "older than ttl" -> expired
            if ttl > 0 and (now - ts) > ttl:
                return None
            self.hits += 1
            try:
                return json.loads(bytes(blob).decode("utf-8"))
            except Exception:
                return None
        self.misses += 1
        return None

    def put(self, kind: str, key: str, payload: Any):
        if self._conn is None:
            return
        k = f"{kind}:{key}"
        ts = time.time()
        blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache(k, kind, ts, payload) VALUES(?,?,?,?)",
                (k, kind, ts, sqlite3.Binary(blob)))
            if time.time() - self._last_gc > 600:
                self._gc(now=ts)
                self._last_gc = ts

    _last_gc = 0.0

    def _gc(self, now: float):
        if self._conn is None:
            return
        # keep at most 300k rows globally, drop stale > 14 days for likely-unusual TTLs
        try:
            self._conn.execute(
                "DELETE FROM cache WHERE ts < ?", (now - 14 * 86400,))
            self._conn.execute(
                "DELETE FROM cache WHERE k IN (SELECT k FROM cache ORDER BY ts DESC LIMIT -1 OFFSET 300000);")
        except Exception:
            pass

    def stats(self):
        if self._conn is None:
            return {"hits": self.hits, "misses": self.misses, "rows": 0}
        with self._lock:
            n = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        return {"hits": self.hits, "misses": self.misses, "rows": n}

    def close(self):
        if self._conn is None:
            return
        with self._lock:
            self._conn.commit()
            self._conn.close()
            self._conn = None
