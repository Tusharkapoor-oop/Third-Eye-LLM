"""Derive the frozen F1-F17 quality registry from the supplied V9B artifacts.

This script never edits the dataset or rewrites baseline measurements.  It
creates per-item verdicts and a resumable checkpoint.  Fields lacking the raw
evidence required by the registry are explicitly UNSUPPORTED/OPEN rather than
being inferred from aggregate numbers.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "benchmarks" / "eval_dataset_expanded.json"
BASELINE_DIR = ROOT / "reports" / "three-system-comparison" / "raw-v9b-2026-11-02"
RAW_BASELINE = BASELINE_DIR / "three_system_results.jsonl"
SUMMARY_BASELINE = BASELINE_DIR / "summary.json"
OUT_DIR = ROOT / "evidence" / "raw" / "quality-loop-20261102"
STATE_PATH = ROOT / "evidence" / "loop-state.json"
GAP_PATH = ROOT / "GAP-LEDGER.md"
LEDGER_PATH = ROOT / "evidence" / "ledger.jsonl"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_value(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    except Exception:
        return "unknown"


def load() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in RAW_BASELINE.read_text(encoding="utf-8").splitlines() if line.strip()]
    summary = json.loads(SUMMARY_BASELINE.read_text(encoding="utf-8"))
    return dataset, rows, summary


def item_rows(rows: list[dict[str, Any]], system: str) -> list[dict[str, Any]]:
    return [
        {
            "id": row["id"],
            "category": row.get("category"),
            "query": row.get("query"),
            "unanswerable": row.get("unanswerable", False),
            **row[system],
        }
        for row in rows
    ]


def derive() -> dict[str, Any]:
    dataset, rows, summary = load()
    if [item["id"] for item in dataset[: len(rows)]] != [row["id"] for row in rows]:
        raise ValueError("baseline rows do not match the first dataset slice; refusing to derive evidence")
    experiment_id = "QL-V9B-20261102-BASELINE"
    local = item_rows(rows, "local_weblens")
    answerable = [row for row in local if not row["unanswerable"]]
    traps = [row for row in local if row["unanswerable"]]
    records: list[dict[str, Any]] = []
    fields: list[dict[str, Any]] = []

    def add_item_field(field: str, items: list[dict[str, Any]], predicate, reason) -> dict[str, Any]:
        passed = 0
        for item in items:
            ok = bool(predicate(item))
            passed += int(ok)
            records.append({
                "experiment_id": experiment_id,
                "field": field,
                "system": "local_weblens",
                "item_id": item["id"],
                "category": item.get("category"),
                "passed": ok,
                "reason": reason(item) if not ok else "target met for this item",
                "source": "reports/three-system-comparison/raw-v9b-2026-11-02/three_system_results.jsonl",
            })
        return {"passed_items": passed, "total_items": len(items)}

    f1 = add_item_field("F1", answerable, lambda item: item["precision_at_5"] > 0, lambda item: f"precision_at_5={item['precision_at_5']} (no relevant top-5 hit)")
    f2 = add_item_field("F2", answerable, lambda item: item["answer_supported"] is True, lambda item: "answer_supported=false; root cause requires source/query trace")
    f4 = add_item_field("F4", traps, lambda item: item["false_confidence"] is False, lambda item: "false_confidence=true")
    f11 = add_item_field("F11", local, lambda item: item["latency_ms"] <= 2400, lambda item: f"latency_ms={item['latency_ms']} exceeds 2400ms hard ceiling")
    f12 = add_item_field("F12", local, lambda item: item["tokens"] <= 600, lambda item: f"tokens={item['tokens']} exceeds 600-token item ceiling")
    f14 = add_item_field("F14", local, lambda item: item["credits_used"] == 0, lambda item: f"credits_used={item['credits_used']}")
    f15 = add_item_field("F15", local, lambda item: item["status"] == "ok", lambda item: f"status={item['status']}")

    def field(name: str, result: dict[str, Any], verdict: str, next_action: str, *, two_run: bool = False, notes: str | None = None) -> None:
        fields.append({
            "field": name,
            "passed_items": result.get("passed_items"),
            "total_items": result.get("total_items"),
            "item_level_100": result.get("total_items") is not None and result.get("total_items", 0) > 0 and result.get("passed_items") == result.get("total_items"),
            "two_independent_runs": two_run,
            "verdict": verdict,
            "next_action": next_action,
            "notes": notes,
        })

    field("F1", f1, "OPEN-REMEDIATION", "Add a single-variable query-rewrite/retrieval change, then rerun the same 100-item held-out slice twice with paired raw results.")
    field("F2", f2, "OPEN-REMEDIATION", "Trace the 17 local misses to query formulation/provider coverage; fix one routing variable and rerun without changing labels.")
    field("F3", {"passed_items": None, "total_items": None}, "UNSUPPORTED", "Capture generated answer text and claim-level citations for every item; the V9B search-only artifact cannot audit hallucinations.", notes="No answer/claim artifact exists in the supplied baseline.")
    field("F4", f4, "FAIL", "Fix abstention/false-confidence behavior for the six flagged unanswerable items and rerun the complete trap set twice.")
    for name, description in (("F5", "20-document extraction battery"), ("F6", "code/table/HTML-noise extraction checks"), ("F7", "PDF/offline page checks"), ("F8", "BM25/hybrid/RRF per-query retrieval evidence"), ("F9", "deep-research hop evidence"), ("F10", "claim URL/passage/timestamp/hash citation log")):
        field(name, {"passed_items": None, "total_items": None}, "UNSUPPORTED", f"Run and preserve the required {description}; no compatible raw artifact is in V9B.", notes="Not measured by the search-only baseline.")
    latency_summary = summary["systems"]["system_1_local_weblens"]["latency"]
    field("F11", {"passed_items": f11["passed_items"], "total_items": f11["total_items"]}, "FAIL", "Remove the item-1 latency overrun while preserving retrieval quality; p50 passes but the 100% hard ceiling does not.", notes=f"p50_ms={latency_summary['p50_ms']}; max item latency={max(item['latency_ms'] for item in local)}")
    field("F12", f12, "OPEN-REMEDIATION", "Repeat a cold and warm run; the current single run meets the item ceiling and mean but lacks the required second independent run.", notes=f"mean_tokens={summary['systems']['system_1_local_weblens']['tokens_and_cost']['mean_tokens']}")
    field("F13", {"passed_items": None, "total_items": None}, "UNSUPPORTED", "Run a dedicated sustained throughput measurement with explicit windows and QPM logs; the sequential baseline is not valid evidence.")
    field("F14", f14, "OPEN-REMEDIATION", "Repeat keyless local calls in a second cold process and preserve the provider credit ledger.")
    field("F15", f15, "OPEN-REMEDIATION", "Repeat the reliability protocol with documented retry policy and a second fresh process.")
    field("F16", {"passed_items": None, "total_items": None}, "OPEN-REMEDIATION", "Expand the bounded security campaign to every frozen red-team vector and benign-FPR corpus; current evidence is only a partial transport campaign.")
    field("F17", {"passed_items": None, "total_items": None}, "OPEN-REMEDIATION", "Run the complete regression suite twice from fresh processes and tie every kept prior fix to an output artifact.", notes="Fresh captures exist, but the proper nested run was 173 passed/1 skipped and the two-run matrix is not yet complete.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "field_verdicts.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    metadata = {
        "experiment_id": experiment_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": str(DATASET.relative_to(ROOT)),
        "dataset_sha256": sha256(DATASET),
        "baseline_summary": str(SUMMARY_BASELINE.relative_to(ROOT)),
        "baseline_raw": str(RAW_BASELINE.relative_to(ROOT)),
        "baseline_rows": len(rows),
        "dataset_rows_available": len(dataset),
        "git_commit": git_value("rev-parse", "HEAD"),
        "git_status": git_value("status", "--short"),
        "tavily_budget_cap": "UNSET; zero credits spent by this loop",
        "regression_evidence": "evidence/raw/quality-loop-20261102/regression_runs.json and nested-weblens-run2-proper.json",
        "fields": fields,
    }
    (OUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    state = {
        "session": "quality-loop-20261102",
        "registry": "F1-F17 frozen from user prompt",
        "updated_at": metadata["created_at"],
        "status": "OPEN-REMEDIATION",
        "dataset": {"path": str(DATASET.relative_to(ROOT)), "sha256": metadata["dataset_sha256"], "records_available": len(dataset), "records_measured": len(rows)},
        "baseline": str(SUMMARY_BASELINE.relative_to(ROOT)),
        "current_field": "F2",
        "next_action": "Obtain a valid authorized Tavily credential and explicit BUDGET_CAP, then run the F2 paired 100-item cold-process benchmark with the MCP-backed local adapter and per-item answer/citation artifacts.",
        "fields": {entry["field"]: entry for entry in fields},
        "evidence": [str((OUT_DIR / "field_verdicts.jsonl").relative_to(ROOT)), str((OUT_DIR / "metadata.json").relative_to(ROOT))],
    }
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    gap_lines = [
        "# GAP-LEDGER — Quality Loop 2026-11-02",
        "",
        "Evidence source: `evidence/raw/quality-loop-20261102/metadata.json`; no aggregate is treated as a 100% item-level pass.",
        "",
        "| F# | Field | WebLens measured | Best comparator in supplied V9B | Gap / blocker | Root cause or evidence gap | Disposition |",
        "|---|---|---:|---:|---|---|---|",
    ]
    comparator = summary["systems"]["system_3_tavily_direct"]
    gap_lines.extend([
        f"| F1 | Search hit in top-5 | {f1['passed_items']}/{f1['total_items']} | not derivable from aggregate | 2 misses | keyless provider coverage/query formulation | OPEN |",
        f"| F2 | Supported answer | {f2['passed_items']}/{f2['total_items']} | {comparator['quality']['answer_supported_count']}/100 | 17 misses | exact source coverage and answer/citation trace absent | REMEDIATING |",
        f"| F3 | Unsupported claims | UNSUPPORTED | UNSUPPORTED | no answer artifact | baseline is search-only | STRUCTURAL |",
        f"| F4 | Trap abstention | {f4['passed_items']}/{f4['total_items']} | {100-comparator['quality']['false_confidence_count']}/100 | 6 local flags | false-confidence policy/provider results | OPEN |",
        "| F5-F10 | Extraction/RAG/research/citations | UNSUPPORTED | UNSUPPORTED | no compatible raw artifacts | required batteries not run | STRUCTURAL |",
        f"| F11 | Latency hard ceiling | {f11['passed_items']}/{f11['total_items']}; p50 {summary['systems']['system_1_local_weblens']['latency']['p50_ms']}ms | Tavily p50 {comparator['latency']['p50_ms']}ms | one local request >2400ms | tail outlier | OPEN |",
        f"| F12 | Tokens | {f12['passed_items']}/{f12['total_items']}; mean {summary['systems']['system_1_local_weblens']['tokens_and_cost']['mean_tokens']} | Tavily mean {comparator['tokens_and_cost']['mean_tokens']} | second run absent | reproducibility gate | REMEDIATING |",
        "| F13 | Throughput | UNSUPPORTED | UNSUPPORTED | no sustained QPM windows | sequential benchmark | STRUCTURAL |",
        f"| F14 | Keyless cost | {f14['passed_items']}/{f14['total_items']} | Tavily {comparator['tokens_and_cost']['total_credits']} credits | second run absent | reproducibility gate | REMEDIATING |",
        f"| F15 | Reliability | {f15['passed_items']}/{f15['total_items']} | Tavily {comparator['quality']['success_rate']} | retry protocol absent | evidence protocol gap | REMEDIATING |",
        "| F16 | Security | partial campaign only | not comparable | auth failure/deployed | frozen vector matrix incomplete | OPEN |",
        "| F17 | Prior-cycle regressions | not fully re-derived twice | not applicable | independent audit absent | reproducibility protocol gap | OPEN |",
    ])
    GAP_PATH.write_text("\n".join(gap_lines) + "\n", encoding="utf-8")

    ledger_entry = {
        "id": experiment_id,
        "class": "REAL",
        "utc": metadata["created_at"],
        "dataset_sha256": metadata["dataset_sha256"],
        "baseline": str(SUMMARY_BASELINE.relative_to(ROOT)),
        "artifacts": [str((OUT_DIR / "field_verdicts.jsonl").relative_to(ROOT)), str((OUT_DIR / "metadata.json").relative_to(ROOT)), "evidence/loop-state.json", "GAP-LEDGER.md"],
        "verdict": "OPEN-REMEDIATION",
        "tavily_credits_spent": 0,
        "note": "F1-F17 frozen registry derived honestly; no dataset mutation and no Tavily spend without an explicit budget cap and valid credential.",
    }
    existing_ids = set()
    if LEDGER_PATH.exists():
        for line in LEDGER_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                existing_ids.add(json.loads(line).get("id"))
            except json.JSONDecodeError:
                continue
    if experiment_id not in existing_ids:
        with LEDGER_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(ledger_entry, sort_keys=True) + "\n")
    return metadata


if __name__ == "__main__":
    result = derive()
    print(json.dumps({"experiment_id": result["experiment_id"], "fields": {x["field"]: x["verdict"] for x in result["fields"]}, "tavily_credits_spent": 0}))
