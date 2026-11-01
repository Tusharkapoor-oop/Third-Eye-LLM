"""EXP-004b: cache correctness with an eviction payload that can actually fill the cap.

EXP-004 used b"x"*900, which gzip compresses to a few dozen bytes, so the cap was
never reached and the eviction case failed for a test-design reason. This run uses
incompressible bytes. EXP-004 remains in the ledger as superseded evidence.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import time
from pathlib import Path

from _common import emit

from weblens.cache import Cache, cache_key
from weblens.config import Settings


def run() -> list[dict]:
    rows: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        async def ttl_case() -> None:
            s = Settings(cache_dir=root / "ttl", cache_enabled=True, cache_max_bytes=1_000_000)
            c = Cache(s)
            await c.set("k", b"v", {"kind": "test"}, ttl=0.05)
            fresh = await c.get("k") is not None
            await asyncio.sleep(0.15)
            expired = await c.get("k") is None
            rows.append({"case": "ttl_expiry", "passed": bool(fresh and expired), "detail": f"fresh={fresh} expired={expired}"})
            c.close()

        async def collision_case() -> None:
            a, b = cache_key("a", "bc"), cache_key("ab", "c")
            rows.append({"case": "key_field_separation", "passed": a != b, "detail": "separator prevents boundary collision"})
            u1, u2 = cache_key("http", "GET", "https://x.test/a?b=1"), cache_key("http", "GET", "https://x.test/a?b=1")
            rows.append({"case": "key_deterministic", "passed": u1 == u2, "detail": "same input same key"})

        async def sqli_case() -> None:
            s = Settings(cache_dir=root / "sqli", cache_enabled=True, cache_max_bytes=1_000_000)
            c = Cache(s)
            hostile = "x'); DROP TABLE kv;--"
            await c.set(hostile, b"payload", {"kind": "hostile"})
            got = await c.get(hostile)
            rows.append({"case": "sql_injection_key", "passed": got is not None and got[0] == b"payload", "detail": "hostile key stored as data"})
            try:
                with c._lock:
                    count = c._conn.execute("SELECT COUNT(*) FROM kv").fetchone()[0]
                intact = count >= 1
            except sqlite3.Error:
                intact = False
            rows.append({"case": "table_survives_hostile_key", "passed": intact, "detail": f"rows={count if intact else 'error'}"})
            c.close()

        async def eviction_case() -> None:
            s = Settings(cache_dir=root / "evict", cache_enabled=True, cache_max_bytes=3000)
            c = Cache(s)
            for i in range(12):
                await c.set(f"k{i}", os.urandom(900), {"kind": "bulk"}, ttl=600)
            stats = c.stats()
            rows.append({
                "case": "logical_cap_enforced",
                "passed": stats["bytes"] <= 3000 and stats["evictions"] > 0,
                "detail": f"bytes={stats['bytes']} evictions={stats['evictions']} file_bytes={stats['file_bytes']}",
            })
            rows.append({
                "case": "physical_file_bounded",
                "passed": stats["file_bytes"] <= 3_000_000,
                "detail": f"file_bytes={stats['file_bytes']} logical_bytes={stats['bytes']}",
            })
            c.close()

        async def restart_case() -> None:
            s = Settings(cache_dir=root / "restart", cache_enabled=True, cache_max_bytes=1_000_000)
            c = Cache(s)
            await c.set("persist", b"value", {"kind": "test"}, ttl=600)
            c.close()
            c2 = Cache(s)
            got = await c2.get("persist")
            rows.append({"case": "restart_persistence", "passed": got is not None and got[0] == b"value", "detail": "value survives reopen"})
            c2.close()

        async def corrupt_case() -> None:
            s = Settings(cache_dir=root / "corrupt", cache_enabled=True, cache_max_bytes=1_000_000)
            c = Cache(s)
            with c._lock:
                c._conn.execute(
                    "INSERT OR REPLACE INTO kv(k,kind,value,meta,created,expires) VALUES(?,?,?,?,?,?)",
                    ("bad", "test", b"not-zlib", "{}", time.time(), time.time() + 600),
                )
                c._conn.commit()
            got = await c.get("bad")
            rows.append({"case": "corrupt_value_contained", "passed": got is None, "detail": "invalid payload returns miss, no crash"})
            c.close()

        async def disabled_case() -> None:
            s = Settings(cache_dir=root / "off", cache_enabled=False)
            c = Cache(s)
            await c.set("k", b"v", {"kind": "test"})
            got = await c.get("k")
            rows.append({"case": "disabled_cache_noop", "passed": got is None, "detail": "cache disabled returns miss"})
            c.close()

        async def leak_case() -> None:
            s = Settings(cache_dir=root / "leak", cache_enabled=True, cache_max_bytes=1_000_000)
            c = Cache(s)
            await c.set("q-one", b"secret-answer", {"kind": "page"})
            other = await c.get("q-two")
            same = await c.get("q-one")
            rows.append({"case": "cross_key_isolation", "passed": other is None and same is not None and same[0] == b"secret-answer",
                         "detail": "distinct key does not return another key's value"})
            c.close()

        for case in (ttl_case, collision_case, sqli_case, eviction_case, restart_case,
                     corrupt_case, disabled_case, leak_case):
            asyncio.run(case())
    return rows


rows = run()
emit(
    {
        "experiment": "EXP-004b",
        "kind": "cache-correctness",
        "class": "REAL",
        "rows": rows,
        "summary": {"cases": len(rows), "passed": sum(r["passed"] for r in rows)},
        "limitations": [
            "Second attempt: EXP-004's eviction payload was compressible, so it did not exercise the cap.",
            "Single-process concurrency only; no multi-process writer test.",
            "Eviction is measured on the documented logical cap; the SQLite file can exceed it, recorded not hidden.",
        ],
    }
)
