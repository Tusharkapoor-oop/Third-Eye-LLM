"""Coverage for the WebLens facade's error boundary and payload shaping.

The heavy subsystems are replaced with tiny fakes; these tests assert that
errors are converted to stable tool payloads and that budgets remain bounded.
"""

from __future__ import annotations

from types import SimpleNamespace

from weblens.config import Settings
from weblens.errors import ErrCode, WebLensError
from weblens.extract.passages import Passage
from weblens.extract.service import ExtractionService, ExtractOutcome
from weblens.search.base import Hit
from weblens.search.router import SearchOutcome
from weblens.service import WebLens


def _new(settings: Settings | None = None) -> WebLens:
    svc = object.__new__(WebLens)
    svc.s = settings or Settings(cache_dir=".weblens-test", cache_enabled=False)
    return svc


def _outcome(status="ok", *, hits=None, warnings=None) -> SearchOutcome:
    return SearchOutcome(
        query="q",
        used_query="q",
        hits=hits or [],
        providers=["fake"],
        failures={},
        status=status,
        elapsed_ms=1,
        warnings=warnings or [],
    )


async def test_guard_converts_known_timeout_and_unknown_errors():
    svc = _new()

    async def bad_input():
        raise WebLensError("bad", code=ErrCode.BAD_INPUT)

    assert (await svc._guard(bad_input()))["err"] == str(ErrCode.BAD_INPUT)

    async def timeout():
        raise TimeoutError

    assert (await svc._guard(timeout()))["err"] == str(ErrCode.TIMEOUT)

    async def crash():
        raise RuntimeError("boom")

    out = await svc._guard(crash())
    assert out["err"] == str(ErrCode.INTERNAL)
    assert "RuntimeError" in out["msg"]

    svc.s = Settings(cache_dir=".weblens-test", cache_enabled=False, log_level="DEBUG")
    assert (await svc._guard(crash()))["status"] == "error"


async def test_close_uses_aclose_or_sync_close():
    class Extractor:
        closed = False

        async def close(self):
            self.closed = True

    class Fetcher:
        closed = False

        async def close(self):
            self.closed = True

    class AsyncCache:
        closed = False

        async def aclose(self):
            self.closed = True

    svc = _new()
    svc.extractor = Extractor()
    svc.fetcher = Fetcher()
    svc.cache = AsyncCache()
    await svc.close()
    assert svc.extractor.closed and svc.fetcher.closed and svc.cache.closed

    class SyncCache:
        closed = False

        def close(self):
            self.closed = True

    svc.cache = SyncCache()
    await svc.close()
    assert svc.cache.closed


async def test_enrich_search_snippets_replaces_generic_and_official():
    class Extractor:
        status = "ok"
        title = "Better title"
        passages = [Passage(0, 80, "asyncio timeout documentation explains the deadline behavior in detail")]

        async def extract(self, url, **kwargs):
            return self

    svc = _new()
    svc.s = Settings(
        cache_dir=".weblens-test",
        cache_enabled=False,
        search_enrich_top=2,
        search_enrich_timeout_s=5,
    )
    svc.extractor = Extractor()
    hit = Hit(title="Old", url="https://e.com/a", snippet="", provider="official")
    await svc._enrich_search_snippets([hit], query="asyncio timeout", budget=500)
    assert hit.snippet.startswith("asyncio timeout")
    assert hit.title == "Better title"

    long = Hit(title="Old", url="https://e.com/b", snippet="x" * 100, provider="web")
    await svc._enrich_search_snippets([long], query="unrelated", budget=500)
    assert long.snippet == "x" * 100


async def test_search_shapes_payload_and_honors_budget():
    class Router:
        async def search(self, query, **kwargs):
            hits = [Hit(title="A" * 200, url="https://e.com/a", snippet="S" * 400, date="2026-01-01")]
            return _outcome(hits=hits, warnings=["warn"])

    svc = _new()
    svc.s = Settings(cache_dir=".weblens-test", cache_enabled=False, max_search_tokens=120)
    svc.router = Router()
    svc.extractor = None
    out = await svc.search("q", max_tokens=120)
    assert out["status"] in {"ok", "partial"}
    assert out["n"] == 0 or out["n"] == 1
    assert out["prov"] == ["fake"]
    assert "warn" in out["warn"]

    class EmptyRouter:
        async def search(self, query, **kwargs):
            return _outcome(hits=[])

    svc.router = EmptyRouter()
    out = await svc.search("q", max_tokens=120)
    assert out["n"] == 0


async def test_extract_error_adds_error_code_and_message():
    class Extractor:
        async def extract(self, *args, **kwargs):
            return ExtractOutcome(
                status="error",
                url="https://e.com",
                final_url="https://e.com",
                title="",
                fetched_at="x",
                sha="a" * 64,
                kind="html",
            )

        def payload(self, out):
            return ExtractionService.payload(out)

    svc = _new()
    svc.extractor = Extractor()
    payload = await svc.extract("https://e.com")
    assert payload["err"] == str(ErrCode.EXTRACT)
    assert "no extractable text" in payload["msg"]


async def test_crawl_site_dispatch_map_and_crawl_errors():
    class Crawler:
        async def site_map(self, url, **kwargs):
            return SimpleNamespace()

        def map_payload(self, out):
            return {"status": "ok", "mode": "map"}

        async def crawl(self, url, **kwargs):
            return SimpleNamespace()

        def payload(self, out):
            return {"status": "ok", "mode": "crawl"}

    svc = _new()
    svc.crawler = Crawler()
    assert (await svc.crawl_site("https://e.com", mode="map"))["mode"] == "map"
    assert (await svc.crawl_site("https://e.com", mode="crawl"))["mode"] == "crawl"
    assert (await svc.crawl_site("https://e.com", mode="bad"))["err"] == str(ErrCode.BAD_INPUT)


async def test_deep_research_validates_and_returns_payload():
    class Research:
        async def research(self, query, **kwargs):
            return SimpleNamespace()

        def payload(self, out):
            return {"status": "ok", "q": "q"}

    svc = _new()
    svc.research = Research()
    assert (await svc.deep_research(""))["err"] == str(ErrCode.BAD_INPUT)
    assert (await svc.deep_research("x" * 2001))["err"] == str(ErrCode.BAD_INPUT)
    assert (await svc.deep_research("q"))["status"] == "ok"


async def test_synthesize_validates_and_returns_payload(monkeypatch):
    class Engine:
        def __init__(self, research):
            self.research = research

        async def run(self, query, **kwargs):
            return SimpleNamespace(payload=lambda: {"status": "ok", "q": query})

    monkeypatch.setattr("weblens.service.SynthesisEngine", Engine)
    svc = _new()
    svc.research = object()
    assert (await svc.synthesize(""))["err"] == str(ErrCode.BAD_INPUT)
    assert (await svc.synthesize("x" * 2001))["err"] == str(ErrCode.BAD_INPUT)
    assert (await svc.synthesize("q"))["status"] == "ok"


async def test_doctor_uses_async_stats_and_live_search():
    class Cache:
        async def stats_async(self):
            return {"backend": "sqlite"}

    class Router:
        provider_names = ["fake"]
        unavailable = {}

    svc = _new()
    svc.cache = Cache()
    svc.router = Router()

    async def fake_search(query, **kwargs):
        return {"status": "ok", "prov": ["fake"], "err": None}

    svc.search = fake_search  # type: ignore[method-assign]
    info = await svc.doctor(live=True)
    assert info["ok"] is True
    assert info["cache"] == {"backend": "sqlite"}
    assert info["live"]["status"] == "ok"
    assert info["live"]["providers"] == ["fake"]
    assert info["live"]["error"] is None


async def test_doctor_uses_sync_stats_when_async_missing():
    class Cache:
        def stats(self):
            return {"backend": "sqlite"}

    class Router:
        provider_names = []
        unavailable = {}

    svc = _new()
    svc.cache = Cache()
    svc.router = Router()
    info = await svc.doctor()
    assert info["cache"] == {"backend": "sqlite"}
    assert "live" not in info
