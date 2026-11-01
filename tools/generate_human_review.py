#!/usr/bin/env python3
"""Generate stratified human review sample (150 items) for blind human evaluation."""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE7_DATASET = ROOT / "reports" / "tavily-comparison" / "data" / "stage7_dataset.jsonl"
EXPANDED_DATASET = ROOT / "benchmarks" / "eval_dataset_expanded.json"
OUT_CSV = ROOT / "evidence" / "human_review.csv"


def main():
    rows = []
    # 1. Load stage7 dataset
    if STAGE7_DATASET.exists():
        for line in STAGE7_DATASET.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                rows.append({
                    "id": item.get("id"),
                    "category": item.get("category", "general"),
                    "query": item.get("query"),
                    "gold": ", ".join(item.get("answer_terms") or []) if item.get("answer_terms") else "(No reliable answer expected)",
                    "split": item.get("split", "dev"),
                })

    # 2. Load expanded dataset
    if EXPANDED_DATASET.exists():
        data = json.loads(EXPANDED_DATASET.read_text(encoding="utf-8"))
        for item in data:
            rows.append({
                "id": f"exp-{item.get('id')}",
                "category": item.get("category", "general"),
                "query": item.get("query"),
                "gold": item.get("ground_truth_answer", ""),
                "split": "expanded",
            })

    # Ensure deterministic sampling
    rng = random.Random(20261101)
    rng.shuffle(rows)

    # Stratified selection to reach exactly 150 items
    categories = {}
    for r in rows:
        cat = r["category"]
        categories.setdefault(cat, []).append(r)

    selected = []
    # First pass: take evenly from all categories
    while len(selected) < 150 and any(categories.values()):
        for cat in list(categories.keys()):
            if categories[cat]:
                selected.append(categories[cat].pop(0))
                if len(selected) == 150:
                    break

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "sample_index",
            "source_id",
            "category",
            "split",
            "query",
            "gold_reference",
            "system_a_designation",
            "system_b_designation",
            "system_a_passage",
            "system_b_passage",
            "human_system_a_supports_answer",  # Blank for human
            "human_system_b_supports_answer",  # Blank for human
            "human_preferred_winner",          # Blank for human (System A / System B / Tie)
            "human_notes",                     # Blank for human
        ])
        for idx, item in enumerate(selected, start=1):
            # Blind A/B assignment: randomly assign S0 (WebLens keyless) and S3 (Tavily direct) to A or B
            flip = rng.random() > 0.5
            sys_a = "S0_weblens_keyless" if flip else "S3_tavily_direct"
            sys_b = "S3_tavily_direct" if flip else "S0_weblens_keyless"

            writer.writerow([
                idx,
                item["id"],
                item["category"],
                item["split"],
                item["query"],
                item["gold"],
                sys_a,
                sys_b,
                "[EVIDENCE_TO_POPULATE_ON_RUN]",
                "[EVIDENCE_TO_POPULATE_ON_RUN]",
                "",  # Human blank
                "",  # Human blank
                "",  # Human blank
                "",  # Human blank
            ])

    print(f"Generated {len(selected)} stratified items in {OUT_CSV}")


if __name__ == "__main__":
    main()

