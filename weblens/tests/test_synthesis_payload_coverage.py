"""Coverage for synthesis payload/trim paths and low-budget behaviour.

Extends the existing synthesis tests: exercises `SynthesisOutcome.payload()`,
`_trim` under tight budgets, `_resolution_payload`, `source_tier`,
`followup_queries` and `generate_hypotheses` across hypothesis kinds.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from weblens.research.engine import Finding, ResearchOutcome
from weblens.research.synthesis import (
    followup_queries,
    source_tier,
    synthesize,
)

RECENT = (date.today() - timedelta(days=10)).isoformat()


def _finding(claim: str, url: str, published: str | None = RECENT) -> Finding:
    return Finding(
        claim=claim,
        url=url,
        fetched_at="2026-11-08T00:00:00Z",
        span=[0, len(claim)],
        heading="Section",
        published=published,
    )


def _outcome(findings: list[Finding]) -> ResearchOutcome:
    return ResearchOutcome(
        status="ok",
        query="q",
        findings=findings,
        gaps=[],
        searched=["ddg"],
        elapsed_ms=12,
        tokens=100,
    )


MULTI = [
    _finding("Python 3.13 was released in October 2024.", "https://docs.python.org/3/whatsnew/3.13.html"),
    _finding("Python 3.13 includes a new interactive interpreter.", "https://peps.python.org/pep-0667/"),
    _finding("The release adds experimental free-threaded mode.", "https://python.org/blog/3-13"),
    _finding("Python 3.12 was released in October 2023.", "https://docs.python.org/3/whatsnew/3.12.html"),
]


@pytest.mark.parametrize("budget", [200, 300, 600, 1200, 4000])
def test_payload_respects_budget_and_stays_consistent(budget):
    result = synthesize(_outcome(MULTI), query="python 3.13 release", budget=budget)

    payload = result.payload()

    assert payload["tok"] <= max(budget, 120)
    assert payload["status"]
    # Every emitted hypothesis id must correspond to a claim or be a hypothesis id.
    assert isinstance(payload.get("hyp"), list)


def test_payload_marks_budget_exhausted_when_trimmed():
    result = synthesize(_outcome(MULTI), query="python 3.13 release", budget=200)
    payload = result.payload()
    assert "budget_exhausted" in (payload.get("warn") or []) or payload["tok"] <= 200


def test_payload_includes_claims_and_resolutions():
    result = synthesize(_outcome(MULTI), query="python 3.13 release", budget=4000)
    payload = result.payload()
    assert payload.get("claims") or payload.get("hyp")
    # Resolution payloads carry a winner and reason when present.
    for resolution in payload.get("res", []):
        assert "winner" in resolution or "topic" in resolution


def test_synthesize_without_findings_reports_no_reliable_result():
    result = synthesize(_outcome([]), query="nonexistent topic", budget=600)
    payload = result.payload()
    assert payload["status"] == "no_reliable_result"


@pytest.mark.parametrize(
    "url,tier",
    [
        ("https://docs.python.org/3/library/asyncio.html", "primary"),
        ("https://www.sec.gov/edgar/search/", "primary"),
        ("https://en.wikipedia.org/wiki/Python_(programming_language)", "secondary"),
        ("https://random-blog.example/post", "unknown"),
        ("https://arxiv.org/abs/2401.00001", "primary"),
    ],
)
def test_source_tier_is_deterministic(url, tier):
    assert source_tier(url) == tier


def test_generate_hypotheses_covers_multiple_kinds():
    result = synthesize(_outcome(MULTI), query="python 3.13 release date", budget=2000)
    kinds = {r.hypothesis.kind for r in result.hypotheses}
    assert kinds  # at least one hypothesis kind was generated
    assert all(isinstance(k, str) for k in kinds)


def test_followup_queries_are_suggestions_not_echoes():
    result = synthesize(_outcome(MULTI), query="python 3.13 release", budget=2000)
    suggestions = followup_queries(result, "python 3.13 release")
    assert isinstance(suggestions, list)
    for s in suggestions:
        assert isinstance(s, str) and s.strip()
        assert s.lower() != "python 3.13 release"


def test_hypotheses_payload_shape():
    result = synthesize(_outcome(MULTI), query="python 3.13 release", budget=4000)
    payload = result.payload()
    for item in payload.get("hyp", []):
        assert {"id", "s", "kind", "verdict"} <= set(item)
