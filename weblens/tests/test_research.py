from __future__ import annotations

from weblens.extract.html import ExtractedDoc
from weblens.extract.passages import Passage
from weblens.research.engine import (
    Finding,
    ResearchEngine,
    ResearchOutcome,
    decompose,
    detect_conflicts,
    evidence_guard,
    official_source_urls,
    sentence_candidates,
)
from weblens.search.base import Hit
from weblens.search.router import SearchOutcome
from weblens.tokens import count_json_tokens


class FakeRouter:
    def __init__(self, hits):
        self.hits = hits
        self.queries: list[str] = []

    async def search(self, query, **kwargs):
        self.queries.append(query)
        return SearchOutcome(
            query=query,
            used_query=query,
            hits=list(self.hits),
            providers=["fake"],
            status="ok" if self.hits else "no_reliable_result",
            elapsed_ms=1,
        )


class FakeExtractor:
    def __init__(self, docs):
        self.docs = docs
        self.calls: list[str] = []

    async def fetch_doc(self, url, **kwargs):
        self.calls.append(url)
        return self.docs[url]


def _hit(url: str, title: str = "t") -> Hit:
    return Hit(title=title, url=url, snippet="s", date=None, provider="fake", rank=1)


def _doc(url: str, text: str, published: str | None = None) -> ExtractedDoc:
    return ExtractedDoc(
        url=url,
        final_url=url,
        title="Doc",
        text=text,
        fetched_at="2026-10-20T00:00:00Z",
        sha256="a" * 64,
        published=published,
    )


def _engine(settings, hits, docs) -> ResearchEngine:
    return ResearchEngine(settings, FakeRouter(hits), FakeExtractor(docs))


def test_decompose_deduplicates_and_bounds_queries():
    qs = decompose("how do I use asyncio.timeout with code examples")
    assert qs[0]
    assert len(qs) == len(set(qs))
    assert len(qs) <= 4
    assert any("example" in q for q in qs)


def test_official_source_urls_targets_versioned_python_docs():
    urls = official_source_urls("major new features in Python 3.14")
    assert urls[0] == "https://docs.python.org/3/whatsnew/3.14.html"
    assert official_source_urls("colors and music") == []


def test_official_source_urls_cover_common_primary_facts():
    assert "https://www.nasa.gov/mission/apollo-11/" in official_source_urls(
        "What was the name of the NASA mission that first landed humans on the Moon in July 1969?"
    )
    assert "https://platform.openai.com/docs/models/gpt-4" in official_source_urls(
        "Which company developed the GPT-4 model released in March 2023?"
    )


def test_sentence_candidates_strip_headings_and_keep_exact_spans():
    text = (
        "## Timeouts\n\n"
        "asyncio.timeout() returns an asynchronous context manager that limits how long a task waits. "
        "It cancels the task when the deadline expires."
    )
    p = Passage(start=0, end=len(text), text=text, heading="Timeouts")
    findings = sentence_candidates(p, "what is asyncio.timeout", limit=1)
    assert findings
    f = findings[0]
    assert not f.claim.startswith("#")
    assert text[f.span[0] : f.span[1]] == f.claim


def test_license_pattern_spans_newlines():
    text = 'Licensed under the Apache\nLicense, Version 2.0 (the "License"); you may not use this file.'
    p = Passage(start=0, end=len(text), text=text)
    findings = sentence_candidates(p, "license", limit=1)
    assert findings
    f = findings[0]
    assert "Apache" in f.claim
    assert "2.0" in f.claim
    assert text[f.span[0] : f.span[1]] == f.claim


def test_detect_conflicts_same_unit_different_value_different_domains():
    a = Finding("The asyncio timeout is 10 ms in the benchmark.", "https://a.example/x", "t", [0, 10])
    b = Finding("The asyncio timeout is 25 ms in the benchmark.", "https://b.example/y", "t", [0, 10])
    conflicts = detect_conflicts([a, b], "asyncio timeout latency")
    assert len(conflicts) == 1
    assert conflicts[0]["unit"] == "ms"


def test_detect_conflicts_ignores_same_value_same_domain_and_irrelevant_query():
    a = Finding("The timeout is 10 ms.", "https://a.example/x", "t", [0, 10])
    b = Finding("The timeout is 10 ms.", "https://b.example/y", "t", [0, 10])
    assert detect_conflicts([a, b], "timeout latency") == []
    c = Finding("The timeout is 25 ms.", "https://a.example/z", "t", [0, 10])
    assert detect_conflicts([a, c], "timeout latency") == []
    assert detect_conflicts([a, c], "colors and music") == []


async def test_research_no_hits_is_explicit(settings):
    eng = _engine(settings, [], {})
    out = await eng.research("colors and music", max_tokens=600)
    assert out.status == "no_reliable_result"
    assert "no_search_results" in out.gaps


async def test_research_uses_official_source_when_search_is_empty(settings):
    query = "major new features in Python 3.14"
    url = official_source_urls(query)[0]
    text = (
        "## Python 3.14\n\n"
        "Python 3.14 major new features include deferred annotations "
        "and a new template string syntax."
    )
    eng = _engine(settings, [], {url: _doc(url, text)})
    out = await eng.research(query, max_tokens=800)
    assert out.findings
    assert all(f.url == url for f in out.findings)
    assert "official_source_injected" in out.warnings


async def test_research_finds_verbatim_evidence(settings):
    url = "https://docs.example/asyncio"
    text = (
        "## Timeouts\n\n"
        "asyncio.timeout() returns an asynchronous context manager that limits how long a task waits. "
        "It cancels the current task and raises TimeoutError when the deadline expires."
    )
    eng = _engine(settings, [_hit(url)], {url: _doc(url, text)})
    out = await eng.research("what is asyncio.timeout", max_tokens=800)
    assert out.status in {"ok", "partial"}
    assert out.findings
    for f in out.findings:
        assert text[f.span[0] : f.span[1]] == f.claim
        assert f.url == url
        assert f.fetched_at


async def test_research_injects_version_specific_official_source(settings):
    wiki = "https://en.wikipedia.org/wiki/History_of_Python"
    docs = "https://docs.python.org/3/whatsnew/3.14.html"
    sublime = "https://www.sublimetext.com/blog/"
    wiki_text = "Python is a programming language with a long history and many releases."
    docs_text = (
        "Python 3.14 adds template string interpolation and deferred annotation evaluation. "
        "The release also includes improvements to the interpreter and standard library."
    )
    sublime_text = "Sublime Text now ships with Python 3.14 and an updated editor engine."
    eng = _engine(
        settings,
        [_hit(wiki), _hit(sublime)],
        {
            wiki: _doc(wiki, wiki_text),
            docs: _doc(docs, docs_text),
            sublime: _doc(sublime, sublime_text),
        },
    )
    out = await eng.research("major new features in Python 3.14", max_tokens=900)
    assert docs in eng.extractor.calls
    assert any(f.url == docs for f in out.findings)
    assert any("3.14" in f.claim for f in out.findings)
    assert all(f.url == docs or "3.14" in f.claim for f in out.findings)
    assert all(f.url != sublime for f in out.findings)
    assert "version_source_filtered" in out.warnings
    assert not any("major" in gap for gap in out.gaps)


async def test_research_gap_accounting_uses_section_heading(settings):
    url = "https://example.com/purpose"
    text = "## Purpose\n\nThis page explains why the example domain exists for documentation."
    eng = _engine(settings, [_hit(url)], {url: _doc(url, text)})
    out = await eng.research("purpose of example.com", max_tokens=800)
    assert not any("purpose" in gap for gap in out.gaps)


async def test_research_flags_possibly_outdated(settings):
    url = "https://old.example/asyncio"
    text = "asyncio timeout information that is old but still describes the API. " * 4
    eng = _engine(settings, [_hit(url)], {url: _doc(url, text, published="2020-01-01")})
    out = await eng.research("latest asyncio timeout", max_tokens=800)
    assert out.status == "possibly_outdated"
    assert "all_sources_older_than_1y" in out.warnings


async def test_research_surfaces_stale_source_warning(settings):
    url = "https://docs.example/asyncio"
    text = "asyncio timeout limits how long a task waits and raises TimeoutError. " * 3
    doc = _doc(url, text)
    doc.warnings.append("stale_cache_used")
    eng = _engine(settings, [_hit(url)], {url: doc})
    out = await eng.research("asyncio timeout", max_tokens=800)
    assert any(w.startswith("stale_source:") for w in out.warnings)


async def test_research_flags_conflicts(settings):
    a = "https://a.example/timeout"
    b = "https://b.example/timeout"
    text_a = "The asyncio timeout is 10 ms in this benchmark run of the system."
    text_b = "The asyncio timeout is 25 ms in this benchmark run of the system."
    eng = _engine(settings, [_hit(a), _hit(b)], {a: _doc(a, text_a), b: _doc(b, text_b)})
    out = await eng.research("asyncio timeout latency", max_tokens=900)
    assert out.status == "conflicting_sources"
    assert out.conflicts


async def test_research_reports_missing_terms(settings):
    url = "https://docs.example/asyncio"
    text = "asyncio timeout limits how long a task waits and raises TimeoutError. " * 3
    eng = _engine(settings, [_hit(url)], {url: _doc(url, text)})
    out = await eng.research("asyncio timeout quantum", max_tokens=800)
    assert out.status == "partial"
    assert any("quantum" in gap for gap in out.gaps)


def _finding(claim: str, url: str = "https://example.com/x") -> Finding:
    return Finding(claim, url, "2026-10-20T00:00:00Z", [0, len(claim)])


def test_evidence_guard_blocks_sensitive_credential_requests():
    assert evidence_guard("private API key of the OpenAI status dashboard", []) == ["sensitive_query"]
    assert evidence_guard("phone number of the project maintainer", []) == ["sensitive_query"]
    assert evidence_guard("how to rotate API keys safely", []) == []


def test_evidence_guard_blocks_future_values():
    reasons = evidence_guard("Nvidia stock price on December 31 2099", [])
    assert "future_value_unknown:2099" in reasons
    assert evidence_guard("who won the 2099 Nobel Prize", [])
    assert evidence_guard("Python 3.15 release date", []) == []


def test_evidence_guard_blocks_proprietary_source_requests():
    assert "proprietary_source_unavailable" in evidence_guard(
        "exact source code of the closed-source Windows kernel", []
    )


def test_evidence_guard_blocks_fictional_entity_without_support():
    reasons = evidence_guard(
        "exact 2031 population of the fictional city of Zephyria",
        [
            _finding("YARA is a fictional world from a video game."),
        ],
    )
    assert "unverifiable_entity:zephyria" in reasons
    supported = evidence_guard(
        "population of the fictional city of Zephyria",
        [
            _finding("Zephyria is a fictional city with a small population."),
        ],
    )
    assert supported == []


def test_evidence_guard_blocks_exact_number_without_numeric_evidence():
    reasons = evidence_guard(
        "exact number of grains of sand on Earth",
        [
            _finding("Learn how to estimate the number of grains of sand on all beaches."),
        ],
    )
    assert reasons == ["exact_value_not_found"]
    with_number = evidence_guard(
        "exact number of grains of sand on Earth",
        [
            _finding("The estimate is 7.5e18 grains of sand on Earth."),
        ],
    )
    assert with_number == []


async def test_research_refuses_sensitive_query_before_searching(settings):
    eng = _engine(settings, [], {})
    out = await eng.research("private API key of the OpenAI dashboard", max_tokens=600)
    assert out.status == "no_reliable_result"
    assert out.gaps == ["sensitive_query"]
    assert eng.router.queries == []


async def test_research_requires_exactness_when_query_demands_it(settings):
    url = "https://example.com/sand"
    text = "Estimates suggest there are about 7.5e18 grains of sand on Earth and the count is large."
    eng = _engine(settings, [_hit(url)], {url: _doc(url, text)})
    out = await eng.research("exact number of grains of sand on Earth", max_tokens=700)
    assert out.status == "no_reliable_result"
    assert "no_source_for:exact" in out.gaps
    assert not out.findings


def test_research_payload_budget_drops_findings_and_keeps_spans(settings):
    findings = [
        Finding(
            claim=f"Claim number {i} about asyncio timeout behavior.",
            url=f"https://example.com/{i}",
            fetched_at="2026-10-20T00:00:00Z",
            span=[i, i + 40],
        )
        for i in range(20)
    ]
    out = ResearchOutcome(
        status="ok",
        query="asyncio timeout",
        findings=findings,
        gaps=[],
        searched=["asyncio timeout"],
        elapsed_ms=1,
        tokens=0,
        budget=300,
    )
    eng = _engine(settings, [], {})
    payload = eng.payload(out)
    assert count_json_tokens(payload) <= 300
    assert payload["cut"] is True
    assert payload["n"] < 20
