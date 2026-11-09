from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from weblens.cli import _call
from weblens.research.engine import Finding, ResearchOutcome
from weblens.research.synthesis import (
    SynthesisEngine,
    followup_queries,
    generate_hypotheses,
    source_tier,
    synthesize,
)
from weblens.service import WebLens

RECENT = (date.today() - timedelta(days=30)).isoformat()
MID = (date.today() - timedelta(days=400)).isoformat()
OLD = (date.today() - timedelta(days=800)).isoformat()


def _finding(claim: str, url: str, published: str | None = None) -> Finding:
    return Finding(
        claim=claim,
        url=url,
        fetched_at="2026-11-08T00:00:00Z",
        span=[0, len(claim)],
        heading=None,
        published=published,
    )


def _outcome(
    query: str,
    findings: list[Finding],
    *,
    gaps: list[str] | None = None,
    conflicts: list[dict] | None = None,
    status: str = "ok",
) -> ResearchOutcome:
    return ResearchOutcome(
        status=status,
        query=query,
        findings=findings,
        gaps=gaps or [],
        searched=[query],
        elapsed_ms=1,
        tokens=0,
        warnings=[],
        conflicts=conflicts or [],
        budget=4000,
    )


def _polar(outcome, polarity: str):
    matches = [r for r in outcome.hypotheses if r.hypothesis.kind == "polar" and r.hypothesis.polarity == polarity]
    assert matches, f"no {polarity} hypothesis"
    return matches[0]


def _entity(outcome, entity: str):
    matches = [r for r in outcome.hypotheses if r.hypothesis.entity and r.hypothesis.entity.lower() == entity.lower()]
    assert matches, f"no {entity} hypothesis"
    return matches[0]


def test_generate_hypotheses_polar() -> None:
    hyps = generate_hypotheses("Does asyncio.timeout cancel the task when the deadline expires?")
    assert [h.polarity for h in hyps] == ["affirmative", "negative"]
    assert all(h.kind == "polar" for h in hyps)
    assert "asyncio.timeout" in hyps[0].terms
    assert "cancel" in hyps[0].terms


def test_generate_hypotheses_comparison() -> None:
    hyps = generate_hypotheses("PostgreSQL vs MySQL for write-heavy workloads")
    entities = [h.entity for h in hyps if h.entity]
    assert entities == ["PostgreSQL", "MySQL"]
    assert any(h.kind == "definition" for h in hyps)
    assert all("workloads" in h.terms for h in hyps)


def test_generate_hypotheses_numeric_and_definition() -> None:
    numeric = generate_hypotheses("What is the maximum SQLite database size?")
    assert len(numeric) == 1
    assert numeric[0].kind == "numeric"
    timeout = generate_hypotheses("What is the timeout?")
    assert len(timeout) == 1
    assert timeout[0].kind == "numeric"
    definition = generate_hypotheses("What is the CAP theorem?")
    assert len(definition) == 1
    assert definition[0].kind == "definition"


def test_primary_source_resolves_polar_contradiction() -> None:
    query = "Does asyncio.timeout cancel the task when the deadline expires?"
    outcome = _outcome(
        query,
        [
            _finding(
                "asyncio.timeout() cancels the task when the deadline expires.",
                "https://docs.python.org/3/library/asyncio-task.html",
                RECENT,
            ),
            _finding(
                "asyncio.timeout does not cancel the task when the deadline expires.",
                "https://blog.example.com/asyncio",
                RECENT,
            ),
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    affirmative = _polar(result, "affirmative")
    negative = _polar(result, "negative")
    assert affirmative.verdict == "supported"
    assert negative.verdict == "refuted"
    assert affirmative.support > 0.5
    assert negative.support < 0.5
    assert affirmative.resolution is not None
    assert affirmative.resolution.reason == "primary_source_over_secondary"


def test_negation_supports_negative_hypothesis() -> None:
    query = "Does coffee cause dehydration?"
    outcome = _outcome(
        query,
        [
            _finding(
                "Coffee does not cause dehydration in moderate amounts.",
                "https://www.who.int/news-room/fact-sheets/detail/coffee",
                RECENT,
            )
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    assert _polar(result, "affirmative").verdict == "refuted"
    assert _polar(result, "negative").verdict == "supported"


def test_unrelated_negation_in_code_comment_is_neutral() -> None:
    query = "Does asyncio.timeout cancel the task when the deadline expires?"
    outcome = _outcome(
        query,
        [
            _finding(
                "If the task takes longer than the deadline, the context manager will cancel the task "
                "and raise TimeoutError.",
                "https://docs.python.org/3/library/asyncio-task.html",
                RECENT,
            ),
            _finding(
                "Example: async with asyncio.timeout(None) as cm: # We do not know the timeout when "
                "starting. Timeout context managers can be safely nested.",
                "https://docs.python.org/3/library/asyncio-task.html",
                RECENT,
            ),
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    assert _polar(result, "affirmative").verdict == "supported"
    assert _polar(result, "negative").verdict == "refuted"


def test_negation_after_predicate_does_not_refute() -> None:
    query = "Does asyncio.timeout cancel the task when the deadline expires?"
    outcome = _outcome(
        query,
        [
            _finding(
                "The context manager cancels the task; the deadline does not expire.",
                "https://docs.python.org/3/library/asyncio-task.html",
                RECENT,
            )
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    assert _polar(result, "affirmative").verdict == "supported"
    assert _polar(result, "negative").verdict == "refuted"


def test_uncertainty_is_neutral() -> None:
    query = "Does coffee cause dehydration?"
    outcome = _outcome(
        query,
        [
            _finding(
                "Coffee may cause dehydration if you drink too much.",
                "https://blog.example.com/coffee",
                RECENT,
            )
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    assert _polar(result, "affirmative").verdict == "insufficient"
    assert _polar(result, "negative").verdict == "insufficient"


def test_absence_of_evidence_is_not_refutation() -> None:
    query = "Does supplement X cure disease Y?"
    outcome = _outcome(
        query,
        [
            _finding(
                "There is no evidence that supplement X cures disease Y in controlled trials.",
                "https://www.nih.gov/supplement-x",
                RECENT,
            )
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    assert _polar(result, "affirmative").verdict == "insufficient"
    assert _polar(result, "negative").verdict == "insufficient"


def test_newer_source_resolves_tie() -> None:
    query = "Does coffee cause dehydration?"
    outcome = _outcome(
        query,
        [
            _finding(
                "Coffee causes dehydration in some people.",
                "https://news.example.com/new",
                RECENT,
            ),
            _finding(
                "Coffee does not cause dehydration in some people.",
                "https://news.example.org/old",
                OLD,
            ),
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    affirmative = _polar(result, "affirmative")
    assert affirmative.verdict == "supported"
    assert affirmative.resolution is not None
    assert affirmative.resolution.reason == "newer_source_over_older"


def test_unresolved_tie_is_conflicting() -> None:
    query = "Does coffee cause dehydration?"
    outcome = _outcome(
        query,
        [
            _finding("Coffee causes dehydration.", "https://blog.example.com/a", RECENT),
            _finding("Coffee does not cause dehydration.", "https://blog.example.org/b", RECENT),
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    affirmative = _polar(result, "affirmative")
    assert affirmative.verdict == "conflicting"
    assert affirmative.resolution is None
    assert result.status == "conflicting_sources"


def test_independent_domains_resolve_contradiction() -> None:
    query = "Does coffee cause dehydration?"
    outcome = _outcome(
        query,
        [
            _finding("Coffee causes dehydration in some people.", "https://www.reuters.com/a", RECENT),
            _finding("Coffee causes dehydration during exercise.", "https://apnews.com/b", RECENT),
            _finding("Coffee does not cause dehydration.", "https://www.bbc.com/c", RECENT),
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    affirmative = _polar(result, "affirmative")
    assert affirmative.verdict == "supported"
    assert affirmative.resolution is not None
    assert affirmative.resolution.reason == "independent_domain_majority"


def test_numeric_conflict_primary_resolution() -> None:
    query = "What is the maximum SQLite database size?"
    outcome = _outcome(
        query,
        [
            _finding(
                "The maximum SQLite database size is 281 TB.",
                "https://www.sqlite.org/limits.html",
                RECENT,
            ),
            _finding(
                "The SQLite database size limit is 140 TB.",
                "https://blog.example.com/sqlite",
                MID,
            ),
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    numeric = [r for r in result.hypotheses if r.hypothesis.kind == "numeric"][0]
    assert numeric.verdict == "supported"
    assert numeric.resolution is not None
    assert numeric.resolution.winner == "281 tb"
    assert numeric.resolution.reason == "primary_source_over_secondary"


def test_numeric_rejects_generic_overlap_from_unrelated_subject() -> None:
    query = "What is the maximum SQLite database size?"
    outcome = _outcome(
        query,
        [
            _finding(
                "In May 2022, the file upload limit was raised from 100 MB to 2 GB, "
                "and the maximum group size increased to 512 members.",
                "https://en.wikipedia.org/wiki/WhatsApp",
                RECENT,
            )
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    numeric = [r for r in result.hypotheses if r.hypothesis.kind == "numeric"][0]
    assert numeric.verdict == "insufficient"
    assert numeric.reason == "no_numeric_evidence"


def test_numeric_group_selection_prefers_subject_match() -> None:
    query = "What is the maximum SQLite database size?"
    outcome = _outcome(
        query,
        [
            _finding(
                "The maximum SQLite database size is 281 TB.",
                "https://www.sqlite.org/limits.html",
                RECENT,
            ),
            _finding(
                "The maximum string length is 1 GB in SQLite.",
                "https://www.sqlite.org/limits.html",
                RECENT,
            ),
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    numeric = [r for r in result.hypotheses if r.hypothesis.kind == "numeric"][0]
    assert numeric.verdict == "supported"
    assert "281 TB" in result.answer
    assert "1 GB" not in result.answer


def test_numeric_word_units_are_normalized_and_supported() -> None:
    query = "What is the maximum SQLite database size?"
    outcome = _outcome(
        query,
        [
            _finding(
                "The maximum supported size for an SQLite database file is 281 terabytes.",
                "https://en.wikipedia.org/wiki/SQLite",
                RECENT,
            )
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    numeric = [r for r in result.hypotheses if r.hypothesis.kind == "numeric"][0]
    assert numeric.verdict == "supported"
    assert "281 terabytes" in result.answer


def test_numeric_answer_quotes_the_value_from_a_long_claim() -> None:
    query = "What is the maximum SQLite database size?"
    claim = (
        "In May 2025, the 25th-anniversary release SQLite 3.50.0 introduced additional "
        "features, including new Unicode functions and a new API.\n\n"
        "The maximum supported size for an SQLite database file is 281 terabytes.\n\n"
        "SQLite normally stores every table and index in a single ordinary disk file."
    )
    outcome = _outcome(
        query,
        [_finding(claim, "https://en.wikipedia.org/wiki/SQLite", RECENT)],
    )
    result = synthesize(outcome, query=query, budget=4000)
    numeric = [r for r in result.hypotheses if r.hypothesis.kind == "numeric"][0]
    assert numeric.verdict == "supported"
    assert "281 terabytes" in result.answer
    assert "25th-anniversary" not in result.answer


def test_numeric_anchor_can_come_from_source_url() -> None:
    query = "What is the maximum SQLite database size?"
    outcome = _outcome(
        query,
        [
            _finding(
                "The maximum database size is 281 TB.",
                "https://www.sqlite.org/limits.html",
                RECENT,
            )
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    numeric = [r for r in result.hypotheses if r.hypothesis.kind == "numeric"][0]
    assert numeric.verdict == "supported"
    assert "281 TB" in result.answer


def test_numeric_seconds_are_normalized_in_resolution() -> None:
    query = "What is the maximum timeout in seconds?"
    outcome = _outcome(
        query,
        [
            _finding(
                "The maximum timeout is 10 seconds.",
                "https://docs.example.com/timeout",
                RECENT,
            ),
            _finding(
                "The maximum timeout is 5000 ms.",
                "https://blog.example.com/timeout",
                RECENT,
            ),
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    numeric = [r for r in result.hypotheses if r.hypothesis.kind == "numeric"][0]
    assert numeric.verdict == "supported"
    assert numeric.resolution is not None
    assert numeric.resolution.winner == "10000 ms"


def test_numeric_conflict_unresolved() -> None:
    query = "What is the p95 latency of the service?"
    outcome = _outcome(
        query,
        [
            _finding(
                "The p95 latency of the service is 10 ms in the benchmark.",
                "https://blog.example.com/a",
                RECENT,
            ),
            _finding(
                "The p95 latency of the service is 25 ms in the benchmark.",
                "https://blog.example.org/b",
                RECENT,
            ),
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    numeric = [r for r in result.hypotheses if r.hypothesis.kind == "numeric"][0]
    assert numeric.verdict == "conflicting"
    assert numeric.resolution is None
    assert result.status == "conflicting_sources"


def test_comparison_requires_entity_mention() -> None:
    query = "Kubernetes vs Docker for container orchestration"
    outcome = _outcome(
        query,
        [
            _finding(
                "Kubernetes provides container orchestration, scaling, and service discovery.",
                "https://kubernetes.io/docs/concepts/overview/",
                RECENT,
            )
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    assert _entity(result, "Kubernetes").verdict == "supported"
    assert _entity(result, "Docker").verdict == "insufficient"
    assert result.status == "partial"


def test_definition_supported() -> None:
    query = "What is the CAP theorem?"
    outcome = _outcome(
        query,
        [
            _finding(
                "The CAP theorem states that a distributed system cannot simultaneously guarantee "
                "consistency, availability, and partition tolerance.",
                "https://cs.example.edu/cap",
                RECENT,
            )
        ],
    )
    result = synthesize(outcome, query=query, budget=4000)
    assert result.hypotheses[0].verdict == "supported"
    assert result.status == "ok"


def test_no_findings_is_no_reliable_result() -> None:
    query = "What is the population of the fictional city Zephyria?"
    result = synthesize(
        _outcome(query, [], gaps=["no_search_results"], status="no_reliable_result"),
        query=query,
        budget=4000,
    )
    assert result.status == "no_reliable_result"
    assert all(r.verdict == "insufficient" for r in result.hypotheses)


def test_payload_budget_and_citations() -> None:
    query = "Does coffee cause dehydration?"
    claims = [
        _finding(
            f"Coffee causes dehydration in case {i} and this sentence is intentionally long to fill the budget.",
            f"https://blog.example.com/{i}",
            RECENT,
        )
        for i in range(6)
    ]
    result = synthesize(_outcome(query, claims), query=query, budget=300)
    payload = result.payload()
    assert payload["tok"] <= 300
    assert payload["support"]["citation_integrity"] == 1.0
    for claim in payload.get("claims", []):
        assert claim["u"] and claim["at"] and claim["s"]


def test_followup_queries() -> None:
    query = "Does supplement X cure disease Y?"
    insufficient = synthesize(
        _outcome(
            query,
            [_finding("There is no evidence that supplement X cures disease Y.", "https://www.nih.gov/x", RECENT)],
        ),
        query=query,
        budget=4000,
    )
    followups = followup_queries(insufficient)
    assert followups
    assert "supplement" in followups[0].lower()
    assert followup_queries(insufficient, already=followups) == []


def test_source_tier() -> None:
    assert source_tier("https://docs.python.org/3/library/asyncio-task.html") == "primary"
    assert source_tier("https://en.wikipedia.org/wiki/CAP_theorem") == "secondary"
    assert source_tier("https://blog.example.com/post") == "unknown"
    assert source_tier("https://www.reddit.com/r/python") == "social"


def test_claim_ids_stable_and_deduped() -> None:
    query = "Does coffee cause dehydration?"
    finding = _finding("Coffee causes dehydration.", "https://blog.example.com/a", RECENT)
    result = synthesize(_outcome(query, [finding, finding]), query=query, budget=4000)
    assert len(result.claims) == 1
    assert result.claims[0].id.startswith("c")


class FakeResearch:
    def __init__(self, outcomes: list[ResearchOutcome]):
        self.outcomes = outcomes
        self.queries: list[str] = []
        self.s = SimpleNamespace(max_research_tokens=4000)

    async def research(self, query: str, **kwargs) -> ResearchOutcome:
        self.queries.append(query)
        index = min(len(self.queries) - 1, len(self.outcomes) - 1)
        return self.outcomes[index]


@pytest.mark.asyncio
async def test_service_synthesize_returns_payload() -> None:
    query = "Does asyncio.timeout cancel the task when the deadline expires?"
    resolved = _outcome(
        query,
        [
            _finding(
                "asyncio.timeout() cancels the task when the deadline expires.",
                "https://docs.python.org/3/library/asyncio-task.html",
                RECENT,
            )
        ],
    )
    service = WebLens.__new__(WebLens)
    service.research = FakeResearch([resolved])
    service.s = SimpleNamespace(max_research_tokens=4000)
    payload = await service.synthesize(query, max_hops=1)
    assert payload["status"] == "ok"
    assert payload["q"] == query
    assert payload["tok"] <= 8000


@pytest.mark.asyncio
async def test_synthesis_engine_multihop() -> None:
    query = "Does asyncio.timeout cancel the task when the deadline expires?"
    first = _outcome(query, [], gaps=["no_search_results"], status="no_reliable_result")
    second = _outcome(
        query,
        [
            _finding(
                "asyncio.timeout() cancels the task when the deadline expires.",
                "https://docs.python.org/3/library/asyncio-task.html",
                RECENT,
            )
        ],
    )
    fake = FakeResearch([first, second])
    result = await SynthesisEngine(fake).run(query, max_hops=2)
    assert len(fake.queries) == 2
    assert len(result.hops) == 2
    assert result.hops[-1]["stop"] == "resolved"
    assert any(r.verdict == "supported" for r in result.hypotheses)


@pytest.mark.asyncio
async def test_synthesis_engine_stops_when_resolved() -> None:
    query = "Does asyncio.timeout cancel the task when the deadline expires?"
    resolved = _outcome(
        query,
        [
            _finding(
                "asyncio.timeout() cancels the task when the deadline expires.",
                "https://docs.python.org/3/library/asyncio-task.html",
                RECENT,
            )
        ],
    )
    fake = FakeResearch([resolved])
    result = await SynthesisEngine(fake).run(query, max_hops=2)
    assert len(fake.queries) == 1
    assert result.hops[0]["stop"] == "resolved"


@pytest.mark.asyncio
async def test_cli_synthesize_forwards() -> None:
    class FakeService:
        async def synthesize(self, query: str, **kwargs):
            return {"status": "ok", "q": query, **kwargs}

    args = SimpleNamespace(command="synthesize", query="q", max_tokens=500, max_hops=2)
    payload = await _call(FakeService(), args)
    assert payload["q"] == "q"
    assert payload["max_hops"] == 2
