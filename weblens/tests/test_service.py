from __future__ import annotations

from types import SimpleNamespace

import pytest

from weblens.errors import ErrCode, WebLensError, resolve_budget
from weblens.search.base import Hit
from weblens.search.router import SearchOutcome
from weblens.service import WebLens
from weblens.tokens import count_json_tokens


class FakeRouter:
    def __init__(self, hits=None, *, status="ok", failures=None, warnings=None):
        self.hits = hits or []
        self.status = status
        self.failures = failures or []
        self.warnings = warnings or []
        self.calls: list[tuple[str, dict]] = []

    async def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return SearchOutcome(
            query=query,
            used_query=query,
            hits=list(self.hits),
            providers=["fake"],
            failures=self.failures,
            warnings=self.warnings,
            status=self.status,
            elapsed_ms=1,
        )


def _service(settings, router) -> WebLens:
    svc = object.__new__(WebLens)
    svc.s = settings
    svc.router = router
    return svc


def _hit(i: int, *, url_len: int = 30) -> Hit:
    return Hit(
        title=f"Title {i}",
        url="https://example.com/" + "x" * url_len,
        snippet=f"Snippet {i}",
        date=None,
        provider="fake",
        rank=i,
    )


class FakeExtractor:
    def __init__(self, text: str = "A relevant passage from the page."):
        self.text = text
        self.calls = []

    async def extract(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return SimpleNamespace(
            status="ok",
            title="Page title",
            passages=[SimpleNamespace(text=self.text)],
        )


async def test_search_replaces_only_top_snippets_with_extracted_passages(settings):
    settings.search_enrich_top = 2
    settings.search_enrich_timeout_s = 1.0
    svc = _service(settings, FakeRouter([_hit(1), _hit(2), _hit(3)]))
    extractor = FakeExtractor("Extracted passage with python and asyncio details.")
    svc.extractor = extractor

    out = await svc.search("python asyncio")

    assert out["res"][0]["s"].startswith("Extracted passage")
    assert out["res"][1]["s"].startswith("Extracted passage")
    assert out["res"][2]["s"] == "Snippet 3"
    assert len(extractor.calls) == 2
    assert all(call[1]["allow_browser"] is False for call in extractor.calls)


async def test_search_keeps_provider_snippet_when_enrichment_fails(settings):
    settings.search_enrich_top = 2

    class FailingExtractor:
        async def extract(self, url, **kwargs):
            raise TimeoutError("page too slow")

    svc = _service(settings, FakeRouter([_hit(1)]))
    svc.extractor = FailingExtractor()

    out = await svc.search("python asyncio")

    assert out["status"] == "ok"
    assert out["res"][0]["s"] == "Snippet 1"


def test_resolve_budget_contract():
    assert resolve_budget(None, 600, minimum=120, maximum=2000) == 600
    assert resolve_budget(200, 600, minimum=120, maximum=2000) == 200
    assert resolve_budget(9999, 600, minimum=120, maximum=2000) == 2000
    with pytest.raises(WebLensError) as e:
        resolve_budget(50, 600, minimum=120, maximum=2000)
    assert e.value.code == ErrCode.BAD_INPUT


async def test_search_rejects_tiny_budget_instead_of_silently_raising_it(settings):
    svc = _service(settings, FakeRouter([_hit(1)]))
    out = await svc.search("python asyncio", max_tokens=50)
    assert out["status"] == "error"
    assert out["err"] == "bad_input"
    assert "max_tokens" in out["msg"]


async def test_search_caps_results_and_strips_domains(settings):
    router = FakeRouter([_hit(i) for i in range(20)])
    svc = _service(settings, router)
    out = await svc.search(
        "q",
        max_results=99,
        domains=["a.com", " ", "b.com"],
        exclude_domains=[" c.com "],
    )
    assert out["status"] == "ok"
    q, kwargs = router.calls[-1]
    assert q == "q"
    assert kwargs["k"] == 10
    assert kwargs["domains"] == ["a.com", "b.com"]
    assert kwargs["exclude_domains"] == ["c.com"]


async def test_search_payload_respects_budget_and_reports_cut(settings):
    router = FakeRouter(
        [
            Hit(
                title="T" * 200,
                url="https://example.com/" + "x" * 200,
                snippet="S" * 400,
                date="2026-10-20",
                provider="fake",
                rank=i,
            )
            for i in range(30)
        ]
    )
    svc = _service(settings, router)
    out = await svc.search("python asyncio", max_tokens=200)
    assert count_json_tokens(out) <= 200
    assert out["cut"] is True
    assert out["n"] == len(out["res"])
    assert out["n"] < 30


async def test_search_budget_exhausted_becomes_partial_not_fake_success(settings):
    huge = Hit(
        title=" ".join(f"title{i}" for i in range(60)),
        url="https://example.com/" + "0123456789abcdef" * 30,
        snippet=" ".join(f"snippet{i}" for i in range(60)),
        date=None,
        provider="fake",
        rank=1,
    )
    router = FakeRouter([huge])
    svc = _service(settings, router)
    out = await svc.search("q", max_tokens=120)
    assert count_json_tokens(out) <= 120
    assert out["status"] == "partial"
    assert out["n"] == 0
    assert "budget_exhausted" in out["warn"]


async def test_search_bad_inputs_are_structured_errors(settings):
    svc = _service(settings, FakeRouter())
    empty = await svc.search("   ")
    assert empty["status"] == "error"
    assert empty["err"] == "bad_input"
    bad_fresh = await svc.search("q", freshness="decade")
    assert bad_fresh["status"] == "error"
    assert bad_fresh["err"] == "bad_input"


async def test_search_surfaces_provider_failures_and_warnings(settings):
    router = FakeRouter(
        [_hit(1)],
        status="partial",
        failures=["ddg: timeout", "bing: http_503"],
        warnings=["provider_timeout"],
    )
    svc = _service(settings, router)
    out = await svc.search("q")
    assert out["status"] == "partial"
    assert out["fail"] == ["ddg: timeout", "bing: http_503"]
    assert out["warn"] == ["provider_timeout"]


async def test_crawl_site_rejects_unknown_mode(settings):
    svc = _service(settings, FakeRouter())
    out = await svc.crawl_site("https://example.com", mode="everything")
    assert out["status"] == "error"
    assert out["err"] == "bad_input"


async def test_deep_research_rejects_empty_query(settings):
    svc = _service(settings, FakeRouter())
    out = await svc.deep_research("  ")
    assert out["status"] == "error"
    assert out["err"] == "bad_input"


async def test_guard_never_lets_a_tool_crash_the_transport(settings):
    svc = _service(settings, FakeRouter())

    async def boom():
        raise RuntimeError("boom")

    out = await svc._guard(boom())
    assert out["status"] == "error"
    assert out["err"] == "internal_error"
    assert out["retry"] is False
    assert "RuntimeError" in out["msg"]
