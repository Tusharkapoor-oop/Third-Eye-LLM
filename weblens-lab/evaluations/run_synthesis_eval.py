"""Run the curated synthesis evaluation.

This is a local, deterministic, non-production gate. It feeds curated evidence
into the synthesis layer, compares each hypothesis verdict with a labeled
expectation, and checks that every reportable claim has a URL, fetch timestamp,
and character span. No network, LLM, or model download is involved.

Example:
    python weblens-lab/evaluations/run_synthesis_eval.py \
        --dataset weblens-lab/datasets/synthesis_complex_v1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "weblens" / "src"))

from weblens.research.engine import Finding, ResearchOutcome  # noqa: E402
from weblens.research.synthesis import synthesize  # noqa: E402

FETCHED_AT = "2026-11-08T00:00:00Z"


def _key(kind: str, polarity: str | None = None, entity: str | None = None) -> tuple[str, str, str]:
    if kind == "polar":
        return (kind, polarity or "", "")
    if kind == "comparison":
        return (kind, "", (entity or "").lower())
    return (kind, "", "")


def _actual_key(hypothesis) -> tuple[str, str, str]:
    return _key(hypothesis.kind, hypothesis.polarity, hypothesis.entity)


def _finding(raw: dict) -> Finding:
    claim = raw["claim"]
    return Finding(
        claim=claim,
        url=raw["url"],
        fetched_at=FETCHED_AT,
        span=[0, len(claim)],
        heading=raw.get("heading"),
        published=raw.get("published"),
    )


def _is_cited(claim) -> bool:
    f = claim.finding
    span = f.span
    return bool(f.url) and bool(f.fetched_at) and isinstance(span, list) and len(span) == 2 and 0 <= span[0] < span[1]


def _run_case(case: dict) -> dict:
    findings = [_finding(raw) for raw in case["findings"]]
    outcome = ResearchOutcome(
        status="ok",
        query=case["query"],
        findings=findings,
        gaps=[],
        searched=[case["query"]],
        elapsed_ms=0,
        tokens=0,
        budget=8000,
    )
    result = synthesize(outcome, query=case["query"], budget=8000)
    actual = {_actual_key(r.hypothesis): r for r in result.hypotheses}

    rows: list[dict] = []
    matched = 0
    for expected in case["expected"]:
        key = _key(expected["kind"], expected.get("polarity"), expected.get("entity"))
        row = actual.get(key)
        ok = row is not None and row.verdict == expected["verdict"]
        matched += int(ok)
        rows.append(
            {
                "kind": expected["kind"],
                "polarity": expected.get("polarity"),
                "entity": expected.get("entity"),
                "expected": expected["verdict"],
                "actual": row.verdict if row is not None else None,
                "match": ok,
                "reason": row.reason if row is not None else None,
                "resolution": (
                    {
                        "winner": row.resolution.winner,
                        "reason": row.resolution.reason,
                    }
                    if row is not None and row.resolution is not None
                    else None
                ),
            }
        )

    cited = sum(1 for claim in result.claims if _is_cited(claim))
    claims = len(result.claims)
    payload = result.payload()
    return {
        "id": case["id"],
        "query": case["query"],
        "status": result.status,
        "expected_status": case["expected_status"],
        "status_match": result.status == case["expected_status"],
        "hypotheses": rows,
        "matched": matched,
        "expected_count": len(case["expected"]),
        "claims": claims,
        "cited": cited,
        "citation_integrity": round(cited / claims, 3) if claims else 1.0,
        "payload_tokens": payload["tok"],
        "gaps": result.gaps,
        "warnings": result.warnings,
    }


def run(dataset_path: Path, min_accuracy: float, min_citation_integrity: float) -> dict:
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = [_run_case(case) for case in data["cases"]]

    expected_total = sum(case["expected_count"] for case in cases)
    matched_total = sum(case["matched"] for case in cases)
    claims_total = sum(case["claims"] for case in cases)
    cited_total = sum(case["cited"] for case in cases)
    status_total = sum(1 for case in cases if case["status_match"])

    verdict_accuracy = matched_total / expected_total if expected_total else 0.0
    citation_integrity = cited_total / claims_total if claims_total else 1.0
    status_accuracy = status_total / len(cases) if cases else 0.0
    passed = verdict_accuracy >= min_accuracy and citation_integrity >= min_citation_integrity
    return {
        "dataset": data.get("name", dataset_path.name),
        "version": data.get("version"),
        "caveat": data.get("note", "Curated local evidence; not production acceptance."),
        "cases": cases,
        "summary": {
            "cases": len(cases),
            "hypotheses": expected_total,
            "matched": matched_total,
            "mismatched": expected_total - matched_total,
            "verdict_accuracy": round(verdict_accuracy, 4),
            "min_verdict_accuracy": min_accuracy,
            "status_matches": status_total,
            "status_accuracy": round(status_accuracy, 4),
            "claims": claims_total,
            "cited": cited_total,
            "citation_integrity": round(citation_integrity, 4),
            "min_citation_integrity": min_citation_integrity,
            "passed": passed,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default=str(ROOT / "weblens-lab" / "datasets" / "synthesis_complex_v1.json"),
        help="Path to the labeled synthesis dataset.",
    )
    parser.add_argument("--min-accuracy", type=float, default=0.95)
    parser.add_argument("--min-citation-integrity", type=float, default=1.0)
    args = parser.parse_args(argv)

    if not 0.0 <= args.min_accuracy <= 1.0:
        parser.error("--min-accuracy must be between 0 and 1")
    if not 0.0 <= args.min_citation_integrity <= 1.0:
        parser.error("--min-citation-integrity must be between 0 and 1")

    report = run(Path(args.dataset), args.min_accuracy, args.min_citation_integrity)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
