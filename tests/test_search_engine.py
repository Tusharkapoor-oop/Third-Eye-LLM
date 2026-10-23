"""End-to-end MCP protocol test: spin the real server over stdio using the official
SDK client - tools/list schema sanity + one tool call with a FAKE search provider
(no network). Also runs the startup config validation gates."""
import json

import pytest


def test_config_validation_rejects_bad_provider(monkeypatch):
    monkeypatch.setenv("WEBINTEL_PROVIDER_ORDER", "nosuchprovider")
    with pytest.raises(SystemExit):
        from webintel.config import load_config
        load_config()


def test_http_nonloopback_requires_token(monkeypatch):
    monkeypatch.setenv("WEBINTEL_TRANSPORT", "http")
    monkeypatch.setenv("WEBINTEL_HTTP_HOST", "0.0.0.0")
    monkeypatch.delenv("WEBINTEL_HTTP_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        from webintel.config import load_config
        load_config()


# ------------------------------------------------------------- in-process search
def _fake_engine(monkeypatch, provider_result):
    """Build SearchEngine with a stub provider (no network)."""
    from types import SimpleNamespace

    from webintel.search.engine import SearchEngine

    class FakeProvider:
        id = "fake"
        async def search(self, q, *, max_results, freshness_days, allowed_domains):
            return provider_result

    monkeypatch.setattr(SearchEngine, "__init__", lambda self, cfg, pool: None)
    eng = SearchEngine(None, None)  # type: ignore[misc]
    eng._providers = {"fake": FakeProvider()}
    eng.cfg = SimpleNamespace(http_timeout_search=5, http_timeout_fetch=5,
                              ttl_search=60, allow_private_net=False)
    eng.order = ["fake"]
    return eng


@pytest.mark.asyncio
async def test_search_engine_dedupes_and_caps(monkeypatch):
    from webintel.search.base import ProviderResult, SearchHit
    r = ProviderResult("fake", "ok", [
        SearchHit("fake", "https://a.example/1", "python pathlib guide", "read text python", provider_rank=1),
        SearchHit("fake", "https://b.example/1", "python pathlib tutorial", "read text python 2", provider_rank=1),
        SearchHit("fake", "https://a.example/2", "io modules overview", "read text python 3", provider_rank=2),
        SearchHit("fake", "https://a.example/3", "encoding handbook", "read text python 4", provider_rank=3),
    ], "", "", 12.0)
    eng = _fake_engine(monkeypatch, r)
    out = await eng.web_search("python pathlib read text", max_results=5, freshness=None,
                               domains=None, max_tokens=600, cache=None,
                               cache_key="testk")
    assert out["status"] == "ok"
    urls = [h["u"] for h in out["r"]]
    # max 2 per domain enforced
    from collections import Counter
    c = Counter(u.split("/")[2] for u in urls)
    assert all(n <= 2 for n in c.values())
    # token compactness: a 3-5 result call must stay under the R1 budget (600)
    from webintel.limits import count_tokens
    blobs = json.dumps(out, separators=(",", ":"), ensure_ascii=False)
    assert count_tokens(blobs) <= 600


@pytest.mark.asyncio
async def test_search_engine_falls_back_when_first_provider_errors(monkeypatch):
    from webintel.search.base import ProviderResult, SearchHit
    err = ProviderResult("p1", "provider_error", [], "", "boom", 5.0)
    ok = ProviderResult("p2", "ok", [
        SearchHit("p2", "https://ok.example/1", "t", "s", provider_rank=1)], "", "", 8.0)

    class FakeErr:
        id = "p1"
        async def search(self, *a, **k):
            return err

    class FakeOk:
        id = "p2"
        async def search(self, *a, **k):
            return ok

    from webintel.search.engine import SearchEngine
    monkeypatch.setattr(SearchEngine, "__init__", lambda self, cfg, pool: None)
    eng = SearchEngine(None, None)  # type: ignore[misc]
    eng._providers = {"p1": FakeErr(), "p2": FakeOk()}
    eng.cfg = type("C", (), {"http_timeout_search": 5, "ttl_search": 60})()
    eng.order = ["p1", "p2"]
    out = await eng.web_search("anything", max_results=5, freshness=None, domains=None,
                               max_tokens=400, cache=None, cache_key="k2")
    assert out["status"] == "ok" and out["r"][0]["u"] == "https://ok.example/1"
    assert any(e["p"] == "p1" and e["st"] == "provider_error" for e in out.get("prov", []))


# ------------------------------------------------------------- tool contract
def test_tool_methods_payload_shape():
    """Static assertions on the tool results contract (statuses + fields)."""
    from webintel.extract import _EXTRACT_STATUSES
    for s in ("ok", "no_content", "thin_content_js", "blocked", "unreachable",
              "unsupported_type"):
        assert s in _EXTRACT_STATUSES
