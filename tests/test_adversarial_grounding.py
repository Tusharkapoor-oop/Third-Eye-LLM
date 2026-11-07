"""Adversarial Factual Grounding & Honest Abstention Test Suite.

Verifies:
1. Unanswerable queries (sensitive, far-future, proprietary, exactness requirements).
2. False premises and non-existent entities (fictional markers, missing presence, ungrounded KB queries).
3. Conflicting sources (inter-domain numeric contradictions, heuristic conflict detection).
4. Verbatim provenance and honest abstention status codes ('no_reliable_result', 'not_found', 'not_available').
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from weblens.apps.company import CompanyResearcher
from weblens.apps.crawl2rag import Crawl2RAG
from weblens.apps.market import DISCLAIMER, MarketResearcher
from weblens.config import Settings
from weblens.extract.html import ExtractedDoc
from weblens.extract.passages import Passage
from weblens.research.engine import (
    Finding,
    ResearchEngine,
    ResearchOutcome,
    detect_conflicts,
    evidence_guard,
)
from weblens.search.base import Hit
from weblens.search.router import SearchOutcome
from weblens.service import WebLens


class MockSearchRouter:
    def __init__(self, hits: list[Hit] | None = None):
        self.hits = hits or []
        self.queries: list[str] = []

    async def search(self, query: str, **kwargs):
        self.queries.append(query)
        return SearchOutcome(
            query=query,
            used_query=query,
            hits=list(self.hits),
            providers=["mock"],
            status="ok" if self.hits else "no_reliable_result",
            elapsed_ms=1,
        )


class MockExtractor:
    def __init__(self, docs: dict[str, ExtractedDoc] | None = None):
        self.docs = docs or {}
        self.fetches: list[str] = []

    async def fetch_doc(self, url: str, **kwargs):
        self.fetches.append(url)
        if url in self.docs:
            return self.docs[url]
        raise ValueError(f"URL not in mock doc set: {url}")


def make_hit(url: str, title: str = "Title", snippet: str = "Snippet") -> Hit:
    return Hit(title=title, url=url, snippet=snippet, date=None, provider="mock", rank=1)


def make_doc(url: str, text: str, title: str = "Doc Title") -> ExtractedDoc:
    return ExtractedDoc(
        url=url,
        final_url=url,
        title=title,
        text=text,
        fetched_at="2026-11-05T12:00:00Z",
        sha256="0" * 64,
    )


# ==============================================================================
# Category A: Unanswerable Questions & Early Refusal
# ==============================================================================

@pytest.mark.asyncio
async def test_unanswerable_sensitive_credential_early_abstention():
    """Queries for private API keys, credentials, or personal secrets must be refused early."""
    router = MockSearchRouter()
    extractor = MockExtractor()
    engine = ResearchEngine(Settings(), router, extractor)

    sensitive_queries = [
        "private API key of the production cluster",
        "stolen credentials for internal auth gateway",
        "social security number of the chief executive officer",
        "credit card number of the account holder",
    ]

    for q in sensitive_queries:
        router.queries.clear()
        out = await engine.research(q, max_tokens=500)
        assert out.status == "no_reliable_result"
        assert "sensitive_query" in out.gaps
        assert len(out.findings) == 0
        assert len(router.queries) == 0, f"Network query executed for sensitive request: {q}"


@pytest.mark.asyncio
async def test_unanswerable_far_future_outcomes():
    """Future events beyond the current year cannot be reliably answered and must abstain."""
    router = MockSearchRouter()
    extractor = MockExtractor()
    engine = ResearchEngine(Settings(), router, extractor)

    future_queries = [
        "Nvidia stock price on December 31 2099",
        "who won the 2099 United States presidential election",
        "final score of the 2088 FIFA World Cup final",
    ]

    for q in future_queries:
        router.queries.clear()
        out = await engine.research(q, max_tokens=500)
        assert out.status == "no_reliable_result"
        assert any(gap.startswith("future_value_unknown:") for gap in out.gaps)
        assert len(out.findings) == 0
        assert len(router.queries) == 0


@pytest.mark.asyncio
async def test_unanswerable_proprietary_closed_source_request():
    """Queries demanding proprietary closed-source kernels or code must abstain."""
    router = MockSearchRouter()
    extractor = MockExtractor()
    engine = ResearchEngine(Settings(), router, extractor)

    q = "exact source code of the proprietary Windows kernel scheduler"
    out = await engine.research(q, max_tokens=500)
    assert out.status == "no_reliable_result"
    assert "proprietary_source_unavailable" in out.gaps
    assert len(out.findings) == 0
    assert len(router.queries) == 0


@pytest.mark.asyncio
async def test_unanswerable_exact_value_without_numeric_evidence():
    """Demanding an exact count/figure when sources only provide prose or estimates must abstain."""
    url = "https://earthscience.example/sand"
    text = "Scientists have spent decades contemplating how to estimate the total sand across global beaches."
    hit = make_hit(url, "Sand Studies")
    doc = make_doc(url, text)

    router = MockSearchRouter([hit])
    extractor = MockExtractor({url: doc})
    engine = ResearchEngine(Settings(), router, extractor)

    q = "exact number of grains of sand on Earth"
    out = await engine.research(q, max_tokens=500)
    assert out.status == "no_reliable_result"
    assert "exact_value_not_found" in out.gaps or "no_source_for:exact" in out.gaps
    assert len(out.findings) == 0


# ==============================================================================
# Category B: False Premises & Non-Existent Entities
# ==============================================================================

@pytest.mark.asyncio
async def test_false_premise_fictional_company_detection():
    """CompanyResearcher must detect fictional markers in search results and return not_found."""
    service = WebLens()
    comp = CompanyResearcher(service)

    mock_search = {
        "status": "ok",
        "res": [
            {
                "t": "Acme Corporation - Fictional Company Profile",
                "u": "https://fictionalcompanies.example/acme",
                "s": "Acme Corporation is a fictional company appearing in Looney Tunes cartoons known for dangerous contraptions.",
            }
        ],
    }

    with patch.object(service, "search", new=AsyncMock(return_value=mock_search)):
        res = await comp.research_company("Acme Cartoon Corp")
        assert res["status"] == "not_found"
        assert "fictional or non-commercial" in res["msg"]
        assert res["company"] == "Acme Cartoon Corp"


@pytest.mark.asyncio
async def test_non_existent_company_returns_not_found():
    """CompanyResearcher must return not_found when zero search results are discovered."""
    service = WebLens()
    comp = CompanyResearcher(service)

    mock_empty_search = {"status": "ok", "res": []}

    with patch.object(service, "search", new=AsyncMock(return_value=mock_empty_search)):
        res = await comp.research_company("QuantumVaporXYZNonExistent999")
        assert res["status"] == "not_found"
        assert "No verified web presence found" in res["msg"]


@pytest.mark.asyncio
async def test_non_existent_market_asset_returns_not_available():
    """MarketResearcher must return not_available when no authoritative filings exist."""
    service = WebLens()
    market = MarketResearcher(service)

    mock_empty_search = {"status": "ok", "res": []}

    with patch.object(service, "search", new=AsyncMock(return_value=mock_empty_search)):
        res = await market.analyze_asset("NONEXISTENT_TICKER_99")
        assert res["status"] == "not_available"
        assert "No authoritative filings or disclosures discovered" in res["msg"]
        assert res["disclaimer"] == DISCLAIMER


@pytest.mark.asyncio
async def test_crawl2rag_empty_crawl_abstention(tmp_path):
    """Crawl2RAG ingest must return no_reliable_result when 0 pages are indexed."""
    service = WebLens()
    kb = Crawl2RAG(service, db_path=tmp_path / "empty_kb.db")

    mock_crawl = MagicMock(pages=[], warnings=[])
    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=mock_crawl)):
        res = await kb.ingest("https://empty.example.com")
        assert res["status"] == "no_reliable_result"
        assert res["pages_indexed"] == 0
        assert res["passages_indexed"] == 0


@pytest.mark.asyncio
async def test_crawl2rag_ungrounded_query_returns_not_found(tmp_path):
    """Crawl2RAG query on ungrounded/absent topics must return status 'not_found' and 0 passages."""
    service = WebLens()
    kb = Crawl2RAG(service, db_path=tmp_path / "rag_test.db")

    page = MagicMock(
        url="https://docs.python.org/asyncio",
        title="Python Asyncio",
        text="asyncio is a library to write concurrent code using the async/await syntax.",
        tokens=30,
    )
    mock_crawl = MagicMock(pages=[page], warnings=[])

    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=mock_crawl)):
        await kb.ingest("https://docs.python.org/asyncio")

    # Query for absent entity / false premise
    res = await kb.query("medieval shipbuilding techniques in Baltic ports")
    assert res["status"] == "not_found"
    assert res["n"] == 0
    assert res["passages"] == []


# ==============================================================================
# Category C: Conflicting Sources & Numerical Contradictions
# ==============================================================================

@pytest.mark.asyncio
async def test_conflicting_sources_triggers_conflict_status():
    """Contradictory numeric figures from different domains must trigger 'conflicting_sources'."""
    url_a = "https://techbenchmark-a.example/fastapi"
    url_b = "https://perfreport-b.example/fastapi"

    text_a = "The measured p99 latency for FastAPI under full load is 12 ms in this test."
    text_b = "The measured p99 latency for FastAPI under full load is 48 ms in this test."

    hit_a = make_hit(url_a, "Benchmark A")
    hit_b = make_hit(url_b, "Benchmark B")
    doc_a = make_doc(url_a, text_a)
    doc_b = make_doc(url_b, text_b)

    router = MockSearchRouter([hit_a, hit_b])
    extractor = MockExtractor({url_a: doc_a, url_b: doc_b})
    engine = ResearchEngine(Settings(), router, extractor)

    out = await engine.research("FastAPI p99 latency under full load", max_tokens=1000)
    assert out.status == "conflicting_sources"
    assert len(out.conflicts) >= 1

    c = out.conflicts[0]
    assert c["unit"] == "ms"
    assert c["warn"] == "heuristic_numeric_conflict"
    assert "12 ms" in c["a"]["v"] or "48 ms" in c["a"]["v"]
    assert "12 ms" in c["b"]["v"] or "48 ms" in c["b"]["v"]


def test_conflict_detection_ignores_intra_domain_revisions():
    """Different numbers from the same registrable domain do not count as inter-domain conflict."""
    fa = Finding(
        claim="In our first run latency was 15 ms for the worker.",
        url="https://blog.example.com/post1",
        fetched_at="2026-11-05T12:00:00Z",
        span=[0, 48],
    )
    fb = Finding(
        claim="In our second run latency was 35 ms for the worker.",
        url="https://docs.example.com/post2",
        fetched_at="2026-11-05T12:00:00Z",
        span=[0, 49],
    )
    conflicts = detect_conflicts([fa, fb], "worker latency")
    assert conflicts == []


# ==============================================================================
# Category D: Verbatim Provenance & Zero-Guess Numeric Verification
# ==============================================================================

@pytest.mark.asyncio
async def test_verbatim_provenance_invariant():
    """All research findings must be exact character-matched slices of source text."""
    url = "https://sqlite.org/fts5.html"
    text = (
        "FTS5 is an SQLite virtual table module that provides full-text search functionality to database applications. "
        "It supports BM25 ranking functions and prefix queries."
    )
    hit = make_hit(url, "SQLite FTS5")
    doc = make_doc(url, text)

    router = MockSearchRouter([hit])
    extractor = MockExtractor({url: doc})
    engine = ResearchEngine(Settings(), router, extractor)

    out = await engine.research("what is SQLite FTS5 full-text search", max_tokens=600)
    assert out.status in {"ok", "partial"}
    assert len(out.findings) >= 1

    for finding in out.findings:
        span_slice = text[finding.span[0] : finding.span[1]]
        assert span_slice == finding.claim, f"Span slice mismatch: '{span_slice}' != '{finding.claim}'"
        assert finding.url == url
        assert finding.fetched_at == "2026-11-05T12:00:00Z"


@pytest.mark.asyncio
async def test_market_researcher_zero_guess_strict_regex():
    """Market researcher extracts only regex-verifiable numbers and never fabricates estimates."""
    service = WebLens()
    market = MarketResearcher(service)

    mock_search = {
        "status": "ok",
        "res": [
            {
                "t": "Acme 10-K Annual Report 2025",
                "u": "https://sec.gov/edgar/data/12345/acme10k",
                "d": "2026-02-15",
                "s": "For fiscal year 2025, total revenue was $4.5 billion, representing an increase of 14 percent over 2024.",
            }
        ],
    }

    with patch.object(service, "search", new=AsyncMock(return_value=mock_search)):
        res = await market.analyze_asset("ACME", question="annual revenue")
        assert res["status"] == "ok"
        assert res["disclosures_found"] == 1
        assert len(res["verified_metrics"]) >= 1

        values = [m["value"] for m in res["verified_metrics"]]
        assert "4.5" in values
        dollar_metrics = [m for m in res["verified_metrics"] if m["multiplier"] == "billion"]
        assert len(dollar_metrics) >= 1
        assert dollar_metrics[0]["currency"] == "$"
        assert dollar_metrics[0]["value"] == "4.5"
        assert dollar_metrics[0]["source_url"] == "https://sec.gov/edgar/data/12345/acme10k"
        assert res["disclaimer"] == DISCLAIMER
