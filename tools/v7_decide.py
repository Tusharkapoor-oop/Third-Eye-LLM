#!/usr/bin/env python
"""Mechanical keep/reject decision for cycle 1 plus generated cycle outputs.

Reads only ledger-backed result rows. Applies the pre-registered rule in code.
Writes evidence/cycles/1/decision.json, reports/loop/cycle-1.md and SUMMARY.md.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "evidence" / "raw"
OUT = ROOT / "evidence" / "cycles" / "1"
REPORTS = ROOT / "reports" / "loop"
SEED = 20261101


def load(rid: str) -> dict:
    return json.loads((RAW / rid / "result.json").read_text(encoding="utf-8"))


def mean(values):
    return sum(values) / len(values)


def pct(values, q):
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q / 100.0
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (1 - (pos - lo)) + ordered[hi] * (pos - lo)


def bootstrap_ci(values, resamples=10000, seed=SEED):
    rng = random.Random(seed)
    n = len(values)
    estimates = sorted(mean([values[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples))
    return pct(estimates, 2.5), pct(estimates, 97.5)


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(0, min(b, c) + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def recall(result: dict) -> float:
    rows = [r for r in result["rows"] if r["facts_total"] > 0]
    return sum(r["facts_found"] for r in rows) / sum(r["facts_total"] for r in rows)


def ledger_head() -> str:
    lines = [l for l in (ROOT / "evidence" / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return json.loads(lines[-1])["hash"]


before = load("EXP-101c")
after = load("EXP-102")
b_rows = {r["page"]: r for r in before["rows"]}
a_rows = {r["page"]: r for r in after["rows"]}
pages = sorted(set(b_rows) & set(a_rows))
diffs = [int(a_rows[p]["tail_found"]) - int(b_rows[p]["tail_found"]) for p in pages]
lo, hi = bootstrap_ci(diffs)
b = sum(1 for p in pages if not b_rows[p]["tail_found"] and a_rows[p]["tail_found"])
c = sum(1 for p in pages if b_rows[p]["tail_found"] and not a_rows[p]["tail_found"])
p_value = mcnemar_exact(b, c)

tokens_before = mean([b_rows[p]["tok"] for p in pages])
tokens_after = mean([a_rows[p]["tok"] for p in pages])
lat_before = pct([b_rows[p]["ms"] for p in pages], 95)
lat_after = pct([a_rows[p]["ms"] for p in pages], 95)

rec_before = recall(load("EXP-005"))
rec_after = recall(load("EXP-105"))
candidate_tests = load("EXP-104")["rows"][0]
post_revert_tests = load("EXP-107")["rows"][0]
ssrf = [r for r in load("EXP-106")["rows"] if r["blocked"] is not None and r["url_kind"] != "control"]
ssrf_ok = all(r["blocked"] for r in ssrf) and sum(r.get("fixture_hits_delta", 0) for r in ssrf) == 0

checks = {
    "target": "unqueried long-page tail reachability",
    "target_ci_excludes_zero": lo > 0,
    "target_difference": mean(diffs),
    "target_ci": [lo, hi],
    "mcnemar_p": p_value,
    "tail_before": sum(b_rows[p]["tail_found"] for p in pages),
    "tail_after": sum(a_rows[p]["tail_found"] for p in pages),
    "head_before": sum(b_rows[p]["head_found"] for p in pages),
    "head_after": sum(a_rows[p]["head_found"] for p in pages),
    "head_not_worse": sum(a_rows[p]["head_found"] for p in pages) >= sum(b_rows[p]["head_found"] for p in pages),
    "tokens_within_5pct": tokens_after <= tokens_before * 1.05,
    "tokens_mean_before": tokens_before,
    "tokens_mean_after": tokens_after,
    "p95_latency_within_10pct": lat_after <= lat_before * 1.10,
    "p95_latency_before": lat_before,
    "p95_latency_after": lat_after,
    "fixture_recall_not_worse_2pp": rec_after >= rec_before - 0.02,
    "fixture_recall_before": rec_before,
    "fixture_recall_after": rec_after,
    "candidate_tests_passed": candidate_tests["passed"],
    "candidate_tests_failed": candidate_tests["failed"],
    "tests_ok": candidate_tests["failed"] == 0,
    "ssrf_ok": ssrf_ok,
    "ssrf_attempts": len(ssrf),
    "post_revert_tests_passed": post_revert_tests["passed"],
    "post_revert_tests_failed": post_revert_tests["failed"],
    "post_revert_tests_skipped": post_revert_tests["skipped"],
}

guards = ["head_not_worse", "tokens_within_5pct", "p95_latency_within_10pct",
          "fixture_recall_not_worse_2pp", "tests_ok", "ssrf_ok"]
checks["guard_results"] = {g: checks[g] for g in guards}
checks["verdict"] = "KEEP" if checks["target_ci_excludes_zero"] and all(checks[g] for g in guards) else "REJECT"
checks["action"] = "REVERTED" if checks["verdict"] == "REJECT" else "KEPT"
checks["reject_reasons"] = [g for g in guards if not checks[g]] if checks["verdict"] == "REJECT" else []
checks["test_failure_cause"] = (
    "The two new tests used a trailing sentence shorter than the 40-character chunk minimum, so it was dropped before selection; "
    "the held-out pages use full sentences. The candidate test result is a test-fixture defect, not a product pass."
)
checks["stop_reason"] = "session wall-clock budget reached after one rejected cycle"
checks["ledger_head"] = ledger_head()
checks["patch"] = "evidence/cycles/1/rejected.patch"

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "decision.json").write_text(json.dumps(checks, indent=2, sort_keys=True), encoding="utf-8")

REPORTS.mkdir(parents=True, exist_ok=True)
lines = [
    "# Loop cycle 1",
    "",
    f"Verdict: **{checks['verdict']}**. Action: **{checks['action']}**.",
    "",
    "## Target",
    "",
    "Unqueried extraction of long pages, tail-fact reachability.",
    "",
    f"- Before: `{checks['tail_before']}/{len(pages)}` pages found the tail marker.",
    f"- After: `{checks['tail_after']}/{len(pages)}` pages found the tail marker.",
    f"- Paired difference: `{checks['target_difference']:.3f}` [95% CI `{lo:.3f}`, `{hi:.3f}`].",
    f"- McNemar exact p: `{p_value:.3g}`.",
    "",
    "## Guards",
    "",
]
for g in guards:
    lines.append(f"- `{g}`: `{checks[g]}`")
lines += [
    "",
    "## Why it was not kept",
    "",
    f"Failed guards: `{', '.join(checks['reject_reasons'])}`.",
    "",
    "The target effect is real on the held-out set, but the pre-registered rule also",
    "requires the guarded metrics to hold. p95 extraction latency rose from",
    f"`{lat_before:.1f} ms` to `{lat_after:.1f} ms` on separate runs, which exceeds the",
    "allowed ten percent. The two candidate test failures were caused by a test",
    "fixture with a trailing sentence below the documented chunk minimum; they are",
    "not a product pass, and they are not hidden.",
    "",
    "The candidate patch is preserved at `evidence/cycles/1/rejected.patch`; the",
    "working tree was reverted. The experiment remains in the ledger.",
    "",
    "## Measured context",
    "",
    f"- Tokens per call: `{tokens_before:.1f}` before, `{tokens_after:.1f}` after.",
    f"- Fixture extraction recall: `{rec_before:.3f}` before, `{rec_after:.3f}` after.",
    f"- Post-revert tests: `{checks['post_revert_tests_passed']}` passed, `{checks['post_revert_tests_failed']}` failed, `{checks['post_revert_tests_skipped']}` skipped.",
    f"- SSRF matrix: `{checks['ssrf_attempts']}` attempts, all blocked: `{ssrf_ok}`.",
    "",
    "## Scope",
    "",
    "Held-out pages are synthetic (SIMULATED), n=30. Not live-web evidence. No Tavily",
    "comparison was run. The change is not shipped, so the loss remains.",
    "",
]
(REPORTS / "cycle-1.md").write_text("\n".join(lines), encoding="utf-8")

summary = [
    "# Loop summary",
    "",
    f"Cycle 1: `{checks['verdict']}`. Kept `0`, rejected `1`.",
    f"Biggest remaining loss: long-page tail facts (unqueried extraction), still open.",
    f"Stop rule: {checks['stop_reason']}.",
    f"Ledger head: `{checks['ledger_head']}`.",
    "",
    "No cycle 2 was run. The stop rule fired on the session budget, not on a claim of success.",
    "Mandated applications: NOT RUN in this session.",
    "",
]
(REPORTS / "SUMMARY.md").write_text("\n".join(summary), encoding="utf-8")
print(json.dumps(checks, indent=2, sort_keys=True))
