"""Known-answer unit tests for the v11 WebLens-vs-Tavily metric functions.

These are pure-function tests: no network, no fixtures, no I/O. Every expected
value below is derived by hand (the derivation is in the docstring of each test)
so a bug in a metric cannot silently redefine its own expectation.

Run with:
    python -m pytest weblens-lab/evaluations/test_v11_metrics.py -q
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_weblens_vs_tavily_v11 as v11  # noqa: E402

LABELS = ["python.org", "wikipedia.org"]
REL = "https://docs.python.org/3/library/asyncio.html"
REL2 = "https://en.wikipedia.org/wiki/Python_(programming_language)"
IRREL = "https://spam.example/watch"
IRREL2 = "https://news.example.org/story"


# --------------------------------------------------------------------------- #
# relevance rule
# --------------------------------------------------------------------------- #
def test_host_and_registrable_domain_helpers():
    assert v11.host_of("https://en.wikipedia.org/wiki/X") == "en.wikipedia.org"
    assert v11.host_of("not a url") == ""
    assert v11.host_of("") == ""
    # Two-label public suffixes are resolved to eTLD+1.
    assert v11.registrable_domain("www.australia.gov.au") == "australia.gov.au"
    assert v11.registrable_domain("en.wikipedia.org") == "wikipedia.org"
    assert v11.registrable_domain("a.b.c.go.jp") == "c.go.jp"
    assert v11.registrable_domain("www.meti.go.jp") == "meti.go.jp"
    # A one-label host is returned unchanged (no exception, no empty string).
    assert v11.registrable_domain("localhost") == "localhost"
    # A registrable domain that is itself a label must round-trip.
    assert v11.registrable_domain("wikipedia.org") == "wikipedia.org"


def test_is_relevant_matches_host_domain_and_suffix():
    assert v11.is_relevant(REL, LABELS)
    assert v11.is_relevant(REL2, LABELS)
    # Label is the exact host.
    assert v11.is_relevant("https://python.org/", LABELS)
    # Label is a parent domain of the host.
    assert v11.is_relevant("https://www.python.org/", LABELS)
    # Subdomain label must NOT match an unrelated registrable domain.
    assert not v11.is_relevant(IRREL, LABELS)
    # "notpython.org" must not match "python.org" (suffix needs a dot boundary).
    assert not v11.is_relevant("https://notpython.org/x", LABELS)
    # Empty label list => nothing is relevant.
    assert not v11.is_relevant(REL, [])
    # Unparseable URL => not relevant, no exception.
    assert not v11.is_relevant("", LABELS)


# --------------------------------------------------------------------------- #
# Hit@5
# --------------------------------------------------------------------------- #
def test_hit_at_5_known_answers():
    # Relevant at rank 3 (1-indexed) => hit.
    assert v11.hit_at_k([IRREL, IRREL2, REL], LABELS) == 1.0
    # All irrelevant => miss.
    assert v11.hit_at_k([IRREL, IRREL2], LABELS) == 0.0
    # No results => miss.
    assert v11.hit_at_k([], LABELS) == 0.0
    # Relevant only at rank 6 => outside top-5 => miss.
    assert v11.hit_at_k([IRREL, IRREL2, IRREL, IRREL2, IRREL, REL], LABELS) == 0.0


# --------------------------------------------------------------------------- #
# P@5
# --------------------------------------------------------------------------- #
def test_precision_at_5_known_answers():
    # 2 of 5 relevant => 0.4 (denominator is k, not the number returned).
    assert v11.precision_at_k([REL, IRREL, REL2, IRREL2, IRREL], LABELS) == pytest.approx(0.4)
    # 0 of 5 => 0.0
    assert v11.precision_at_k([IRREL, IRREL2], LABELS) == 0.0
    # 1 result, relevant: P@5 is 1/5, not 1/1 — this is the documented convention.
    assert v11.precision_at_k([REL], LABELS) == pytest.approx(0.2)
    # Empty result list => 0.0
    assert v11.precision_at_k([], LABELS) == 0.0
    # Only the first k are counted.
    assert v11.precision_at_k([REL, REL2, IRREL, IRREL2, IRREL, REL], LABELS) == pytest.approx(0.4)


# --------------------------------------------------------------------------- #
# nDCG@5 (binary gain, log2 discount)
# --------------------------------------------------------------------------- #
def test_ndcg_at_5_known_answers():
    idcg5 = 1 / math.log2(2) + 1 / math.log2(3) + 1 / math.log2(4) + 1 / math.log2(5) + 1 / math.log2(6)

    # Single relevant hit at rank 1 => DCG = 1.0.
    assert v11.ndcg_at_k([REL, IRREL, IRREL2, IRREL, IRREL2], LABELS) == pytest.approx(1.0 / idcg5)
    # Single relevant hit at rank 2 => DCG = 1/log2(3).
    assert v11.ndcg_at_k([IRREL, REL, IRREL2, IRREL, IRREL2], LABELS) == pytest.approx((1 / math.log2(3)) / idcg5)
    # Two relevant hits at ranks 1 and 3 => 1.0 + 1/log2(4).
    assert v11.ndcg_at_k([REL, IRREL, REL2, IRREL2, IRREL], LABELS) == pytest.approx((1.0 + 1 / math.log2(4)) / idcg5)
    # No relevant hits => 0.0.
    assert v11.ndcg_at_k([IRREL, IRREL2], LABELS) == 0.0
    # Empty => 0.0.
    assert v11.ndcg_at_k([], LABELS) == 0.0
    # All five relevant => exactly 1.0.
    assert v11.ndcg_at_k([REL, REL2, REL, REL2, REL], LABELS) == pytest.approx(1.0)
    # A later relevant hit must score strictly lower than an earlier one.
    early = v11.ndcg_at_k([REL, IRREL, IRREL2, IRREL, IRREL2], LABELS)
    late = v11.ndcg_at_k([IRREL, IRREL2, IRREL, IRREL2, REL], LABELS)
    assert early > late


def test_ndcg_label_cap_sensitivity_variant():
    # Two distinct labels => IDCG assumes the top 2 discounts are achievable:
    # ideal = 1/log2(2) + 1/log2(3), so one relevant hit at rank 1 gives
    # 1.0 / (1 + 1/log2(3)).
    idcg2 = 1.0 + 1 / math.log2(3)
    assert v11.ndcg_at_k_label_cap([REL, IRREL, IRREL2, IRREL, IRREL2], LABELS) == pytest.approx(1.0 / idcg2)
    # The label-capped variant must be >= the full-k variant for the same row
    # (smaller IDCG => larger ratio), which is why it is only a sensitivity check.
    full = v11.ndcg_at_k([REL, IRREL, IRREL2, IRREL, IRREL2], LABELS)
    capped = v11.ndcg_at_k_label_cap([REL, IRREL, IRREL2, IRREL, IRREL2], LABELS)
    assert capped >= full
    # With exactly one label the capped IDCG is a single discount, so a rank-1
    # relevant hit is 1.0.
    assert v11.ndcg_at_k_label_cap([REL], ["python.org"]) == pytest.approx(1.0)
    # Still 0.0 when nothing is relevant.
    assert v11.ndcg_at_k_label_cap([IRREL], LABELS) == 0.0
    # Never exceeds 1.0 even with duplicated or empty label lists.
    assert v11.ndcg_at_k_label_cap([REL, REL2, REL, REL2, REL], ["a.com", "a.com", "a.com"]) <= 1.0
    assert v11.ndcg_at_k_label_cap([REL], []) == 0.0


# --------------------------------------------------------------------------- #
# MRR
# --------------------------------------------------------------------------- #
def test_mrr_known_answers():
    # Relevant at rank 1 => 1.0
    assert v11.mrr([REL, IRREL], LABELS) == 1.0
    # Relevant at rank 2 => 0.5
    assert v11.mrr([IRREL, REL], LABELS) == 0.5
    # Relevant at rank 4 => 0.25
    assert v11.mrr([IRREL, IRREL2, IRREL, REL], LABELS) == 0.25
    # First relevant wins even if later ones follow.
    assert v11.mrr([IRREL, REL, REL2], LABELS) == 0.5
    # No relevant => 0.0; empty => 0.0.
    assert v11.mrr([IRREL, IRREL2], LABELS) == 0.0
    assert v11.mrr([], LABELS) == 0.0


# --------------------------------------------------------------------------- #
# aggregates used in the report
# --------------------------------------------------------------------------- #
def test_percentile_known_answers_and_interpolation():
    assert v11.percentile([], 50) == 0.0
    assert v11.percentile([7.0], 95) == 7.0
    assert v11.percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50) == 3.0
    # Linear interpolation between the two middle order statistics.
    assert v11.percentile([1.0, 2.0, 3.0, 4.0], 50) == pytest.approx(2.5)
    # p95 of five points sits between 4 and 5 (position 3.8 => 4 + 0.8*(5-4)).
    assert v11.percentile([1.0, 2.0, 3.0, 4.0, 5.0], 95) == pytest.approx(4.8)
    # Percentiles must be order-independent.
    assert v11.percentile([5.0, 1.0, 3.0, 2.0], 50) == v11.percentile([1.0, 2.0, 3.0, 5.0], 50)


def test_bootstrap_ci_is_deterministic_and_brackets_the_mean():
    values = [0.0, 0.2, 0.4, 0.6, 1.0]
    lo, hi = v11.bootstrap_ci(values, iterations=500, seed=7)
    lo2, hi2 = v11.bootstrap_ci(values, iterations=500, seed=7)
    assert (lo, hi) == (lo2, hi2)  # seeded => reproducible
    assert lo <= sum(values) / len(values) <= hi
    # Degenerate input: constant values collapse the CI onto that value.
    assert v11.bootstrap_ci([0.5, 0.5, 0.5], iterations=200) == pytest.approx((0.5, 0.5))
    assert v11.bootstrap_ci([]) == (0.0, 0.0)


def test_paired_bootstrap_ci_known_answer():
    # a - b is exactly +0.2 on every row => CI collapses to 0.2.
    a = [0.2, 0.4, 0.6]
    b = [0.0, 0.2, 0.4]
    lo, hi = v11.paired_bootstrap_ci(a, b, iterations=300, seed=11)
    assert lo == pytest.approx(0.2) and hi == pytest.approx(0.2)
    # Length mismatch is a bug, and must return the neutral CI rather than crash.
    assert v11.paired_bootstrap_ci([0.1], [0.1, 0.2]) == (0.0, 0.0)


def test_dataset_selection_is_deterministic_and_heldout_first():
    first = v11.select_queries(limit=10)
    second = v11.select_queries(limit=10)
    assert [q["id"] for q in first] == [q["id"] for q in second]  # deterministic
    assert len(first) == 10
    # Every selected item must satisfy the eligibility rule.
    for item in first:
        assert not item.get("is_unanswerable", True)
        assert item.get("web_search_equivalent") is True
        assert item.get("acceptable_sources")
    # The selection rule states heldout precedes development, and the first 10
    # eligible heldout rows are all heldout in this dataset.
    assert {q["split"] for q in first} == {"heldout"}
    # A split filter is honoured.
    only_heldout = v11.select_queries(limit=5, split="heldout")
    assert all(q["split"] == "heldout" for q in only_heldout)
    dev = v11.select_queries(limit=5, split="development")
    assert all(q["split"] == "development" for q in dev)
    # Limit larger than the pool returns the pool, not an error.
    assert len(v11.select_queries(limit=10_000)) >= 100


# --------------------------------------------------------------------------- #
# WebLens-only runs must never masquerade as a head-to-head
# --------------------------------------------------------------------------- #
def test_find_anomalies_suppresses_tavily_reasons_when_arm_not_run():
    row = v11.Row(
        id="q1",
        query="q1",
        category="general",
        split="heldout",
        labels=LABELS,
        order=["weblens"],
        weblens_urls=[IRREL],
        weblens_status="ok",
        weblens_ms=12.0,
    )
    reasons = [r for a in v11.find_anomalies([row]) for r in a["reasons"]]
    # The skipped Tavily arm must not be reported as "returned nothing".
    assert "tavily_returned_nothing" not in reasons
    assert "no_relevant_result_from_either" not in reasons

    # A genuine WebLens-side problem is still flagged.
    broken = v11.Row(
        id="q2",
        query="q2",
        category="general",
        split="heldout",
        labels=LABELS,
        order=["weblens"],
        weblens_status="ok",
        weblens_error="boom",
    )
    assert any("weblens_error" in a["reasons"][0] for a in v11.find_anomalies([broken]))


def _weblens_only_summary() -> dict:
    """Minimal serialisable summary for the WebLens-only report branch."""
    wl = {
        "n": 3,
        "hit_at_5": 1.0,
        "p_at_5": 0.4,
        "p_at_5_ci95": [0.2, 0.6],
        "ndcg_at_5": 0.5,
        "ndcg_at_5_ci95": [0.3, 0.7],
        "ndcg_at_5_label_cap": 0.6,
        "mrr": 0.7,
        "mrr_ci95": [0.5, 0.9],
        "success_rate": 1.0,
        "p50_ms": 900.0,
        "p95_ms": 1800.0,
        "mean_tokens": 300.0,
        "mean_payload_tokens": 350.0,
    }
    return {
        "generated_at": "2026-11-09T00:00:00Z",
        "weblens_only": True,
        "tavily_arm_status": "NOT_RUN",
        "dataset": "weblens-lab/datasets/eval_benchmark_suite_v10.json",
        "dataset_sha256": "a" * 64,
        "selection_rule": "eligible rows, dataset order",
        "k": 5,
        "wall_clock_s": 1.0,
        "config": {
            "weblens_providers": ["mwmbl", "wikipedia"],
            "weblens_search_mode": "fuse",
            "per_query_timeout_s": 30.0,
            "concurrency": 2,
            "sleep_between_queries_s": 0.5,
            "weblens_official_source_hints": False,
        },
        "weblens": wl,
        "anomalies": [],
    }


def test_weblens_only_report_never_claims_a_tavily_win(tmp_path: Path):
    summary = _weblens_only_summary()
    v11.write_report(summary, tmp_path)

    text = (tmp_path / "REPORT.md").read_text(encoding="utf-8")
    # The arm that did not run must be labelled, not scored as a zero.
    assert "Tavily arm: NOT RUN" in text
    assert "WebLens vs Tavily" not in text
    assert "| Better |" not in text
    assert "0.000" not in text

    data = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert data["tavily_arm_status"] == "NOT_RUN"
    assert data["weblens_only"] is True
