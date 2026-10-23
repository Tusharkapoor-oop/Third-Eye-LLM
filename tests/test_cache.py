"""Cache behavior: TTL expiry, cross-process visibility (autocommit), near-dupes."""
import pathlib

from webintel.cache import Cache


def test_put_get_roundtrip(tmp_path: pathlib.Path):
    c = Cache(tmp_path / "c.sqlite3")
    c.put("extract", "k1", {"status": "ok", "u": "https://x.example"})
    got = c.get("extract", "k1", ttl=99999)
    assert got and got["status"] == "ok"


def test_ttl_expires(tmp_path: pathlib.Path):
    c = Cache(tmp_path / "c.sqlite3")
    c.put("extract", "k2", {"a": 1})
    got = c.get("extract", "k2", ttl=-1)   # already expired
    assert got is None


def test_cross_process_visit(tmp_path: pathlib.Path):
    """Two Cache instances (as two MCP server processes would create) must see
    each other's entries: guards the implicit-transaction bug found in dev."""
    path = tmp_path / "c.sqlite3"
    a = Cache(path)
    b = Cache(path)
    a.put("search", "q", {"r": [1, 2]})
    b_hits = b.get("search", "q", ttl=99999)
    a.close()
    b.close()
    assert b_hits == {"r": [1, 2]}


def test_stats_hit_miss(tmp_path: pathlib.Path):
    c = Cache(tmp_path / "c.sqlite3")
    c.put("s", "k", {"z": 1})
    assert c.get("s", "k", 10) == {"z": 1}
    assert c.get("s", "missing", 10) is None
    st = c.stats()
    assert st["hits"] == 1 and st["misses"] == 1


def test_dedupe_by_fingerprint():
    from webintel.utils import fingerprint_url
    a = "https://www.example.com/page/1"
    b = "https://example.com/page/1"        # www stripped, same doc
    c = "https://example.com/other"
    assert fingerprint_url(a) == fingerprint_url(b)
    assert fingerprint_url(a) != fingerprint_url(c)


def test_track_params_stripped():
    from webintel.utils import track_params
    dirty = "https://x.example/p?utm_source=mail&id=42"
    clean = track_params(dirty)
    assert "utm_source" not in clean and "id=42" in clean
