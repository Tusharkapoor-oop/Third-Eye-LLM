"""Analyse a V10 three-system run without re-querying any provider.

Reads the JSONL records emitted by ``run_v10_benchmark.py`` and produces:

* per-category quality/latency/token tables,
* paired win/tie/loss counts and latency deltas,
* the queries with the largest local-vs-Tavily quality gap,
* a machine-readable analysis JSON plus a Markdown fragment.

Usage:
    python weblens-lab/evaluations/analyze_v10.py --run <run.jsonl> --out <dir>
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

SYSTEMS = ("local_weblens", "deployed_weblens", "tavily_direct")


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def mean(values: list[float]) -> float:
    return round(statistics.fmean(values), 3) if values else 0.0


def bootstrap_ci(values: list[float], n_boot: int = 2000, seed: int = 7) -> list[float] | None:
    if len(values) < 3:
        return None
    import random

    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(len(values))] for _ in values]
        means.append(sum(sample) / len(sample))
    means.sort()
    return [round(means[int(0.025 * len(means))], 3), round(means[int(0.975 * len(means)) - 1], 3)]


def system_rows(records: list[dict[str, Any]], system: str) -> list[dict[str, Any]]:
    return [r["systems"][system] for r in records]


def summarize(records: list[dict[str, Any]], system: str) -> dict[str, Any]:
    rows = system_rows(records, system)
    graded = [r for r in rows if r["metrics"].get("graded")]
    latencies = [r["latency_ms"] for r in rows if r["status"] != "error" and r["latency_ms"] > 0]
    ok = sum(1 for r in rows if r["status"] in ("ok", "partial"))
    return {
        "n": len(rows),
        "n_graded": len(graded),
        "success_rate": round(ok / len(rows), 3) if rows else 0.0,
        "p50_ms": round(percentile(latencies, 0.50), 1),
        "p95_ms": round(percentile(latencies, 0.95), 1),
        "mean_ms": round(statistics.fmean(latencies), 1) if latencies else 0.0,
        "p5": mean([r["metrics"]["precision_at_5"] for r in graded]),
        "p1": mean([r["metrics"]["precision_at_1"] for r in graded]),
        "mrr": mean([r["metrics"]["mrr"] for r in graded]),
        "ndcg5": mean([r["metrics"]["ndcg_at_5"] for r in graded]),
        "hit5": mean([1.0 if r["metrics"]["hit_at_5"] else 0.0 for r in graded]),
        "tokens": round(statistics.fmean([r["tokens"] for r in rows]), 1) if rows else 0.0,
        "credits": round(sum(r["credits"] for r in rows), 2),
        "p5_ci95": bootstrap_ci([r["metrics"]["precision_at_5"] for r in graded]),
        "ndcg5_ci95": bootstrap_ci([r["metrics"]["ndcg_at_5"] for r in graded]),
    }


def paired(records: list[dict[str, Any]], a: str, b: str, metric: str) -> dict[str, Any]:
    diffs = []
    wins = ties = losses = 0
    for rec in records:
        ra, rb = rec["systems"][a]["metrics"], rec["systems"][b]["metrics"]
        if not ra.get("graded") or not rb.get("graded"):
            continue
        diff = ra[metric] - rb[metric]
        diffs.append(diff)
        if diff > 0.01:
            wins += 1
        elif diff < -0.01:
            losses += 1
        else:
            ties += 1
    return {
        "n_pairs": len(diffs),
        "mean_delta": round(statistics.fmean(diffs), 3) if diffs else 0.0,
        "ci95": bootstrap_ci(diffs),
        "wins": wins,
        "ties": ties,
        "losses": losses,
    }


def category_table(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        by_cat[rec["category"]].append(rec)
    rows = []
    for category, recs in sorted(by_cat.items()):
        row: dict[str, Any] = {"category": category, "n": len(recs)}
        for system in SYSTEMS:
            s = summarize(recs, system)
            row[f"{system}_p5"] = s["p5"]
            row[f"{system}_ndcg5"] = s["ndcg5"]
            row[f"{system}_p50_ms"] = s["p50_ms"]
            row[f"{system}_tokens"] = s["tokens"]
        rows.append(row)
    return rows


def biggest_gaps(records: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    rows = []
    for rec in records:
        local = rec["systems"]["local_weblens"]["metrics"]
        tav = rec["systems"]["tavily_direct"]["metrics"]
        if not local.get("graded") or not tav.get("graded"):
            continue
        gap = tav["precision_at_5"] - local["precision_at_5"]
        rows.append(
            {
                "id": rec["id"],
                "category": rec["category"],
                "query": rec["query"][:160],
                "local_p5": local["precision_at_5"],
                "tavily_p5": tav["precision_at_5"],
                "gap": round(gap, 3),
                "local_grades": local["grades"],
                "tavily_grades": tav["grades"],
                "local_status": rec["systems"]["local_weblens"]["status"],
            }
        )
    rows.sort(key=lambda r: (-r["gap"], r["id"]))
    return rows[:limit]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    records = [json.loads(line) for line in args.run.read_text(encoding="utf-8").splitlines() if line.strip()]
    args.out.mkdir(parents=True, exist_ok=True)

    analysis = {
        "run_file": str(args.run),
        "records": len(records),
        "dataset_versions": sorted({r.get("dataset_version") for r in records}),
        "systems": {s: summarize(records, s) for s in SYSTEMS},
        "paired": {
            "local_minus_tavily_p5": paired(records, "local_weblens", "tavily_direct", "precision_at_5"),
            "local_minus_tavily_ndcg5": paired(records, "local_weblens", "tavily_direct", "ndcg_at_5"),
            "deployed_minus_local_p5": paired(records, "deployed_weblens", "local_weblens", "precision_at_5"),
            "local_minus_deployed_p5": paired(records, "local_weblens", "deployed_weblens", "precision_at_5"),
        },
        "categories": category_table(records),
        "largest_local_vs_tavily_gaps": biggest_gaps(records),
    }
    (args.out / "analysis.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")

    lines = [
        "# V10 Analysis",
        "",
        f"- Records: {len(records)}",
        f"- Dataset: {', '.join(str(v) for v in analysis['dataset_versions'])}",
        "",
        "## Overall",
        "",
        "| Metric | Local | Deployed | Tavily |",
        "|---|---|---|---|",
    ]
    keys = [
        ("n_graded", "Graded queries"),
        ("success_rate", "Success rate"),
        ("p50_ms", "p50 ms"),
        ("p95_ms", "p95 ms"),
        ("p5", "P@5"),
        ("p1", "P@1"),
        ("mrr", "MRR"),
        ("ndcg5", "nDCG@5"),
        ("hit5", "Hit@5"),
        ("tokens", "Tokens"),
        ("credits", "Credits"),
    ]
    for key, label in keys:
        vals = [analysis["systems"][s][key] for s in SYSTEMS]
        lines.append(f"| {label} | {vals[0]} | {vals[1]} | {vals[2]} |")

    lines += ["", "## Per-category P@5", "", "| Category | n | Local | Deployed | Tavily |", "|---|---|---|---|---|"]
    for row in analysis["categories"]:
        lines.append(
            f"| {row['category']} | {row['n']} | {row['local_weblens_p5']} | "
            f"{row['deployed_weblens_p5']} | {row['tavily_direct_p5']} |"
        )

    lines += [
        "",
        "## Paired comparisons",
        "",
        "| Comparison | Pairs | Mean delta | 95% CI | W/T/L |",
        "|---|---|---|---|---|",
    ]
    for name, data in analysis["paired"].items():
        lines.append(
            f"| {name} | {data['n_pairs']} | {data['mean_delta']} | {data['ci95']} | "
            f"{data['wins']}/{data['ties']}/{data['losses']} |"
        )

    lines += ["", "## Largest local-vs-Tavily P@5 gaps", ""]
    for gap in analysis["largest_local_vs_tavily_gaps"]:
        lines.append(
            f"- `{gap['id']}` ({gap['category']}): local {gap['local_p5']} vs Tavily {gap['tavily_p5']} "
            f"| local grades {gap['local_grades']} vs {gap['tavily_grades']} | {gap['query']}"
        )

    (args.out / "analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({s: analysis["systems"][s] for s in SYSTEMS}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
