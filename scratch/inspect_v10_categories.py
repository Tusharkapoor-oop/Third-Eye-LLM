from __future__ import annotations

import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
items = json.loads((root / "weblens-lab/datasets/eval_benchmark_suite_v10.json").read_text(encoding="utf-8"))
cats = {
    "contradictory_sources",
    "ambiguous_questions",
    "adversarial_injection",
    "programming_developer_docs",
    "insufficient_evidence",
}
for cat in sorted(cats):
    print(f"\n=== {cat} ===")
    for item in items:
        if item.get("category") != cat:
            continue
        print(
            json.dumps(
                {
                    "id": item.get("id"),
                    "query": item.get("query"),
                    "split": item.get("split"),
                    "unanswerable": item.get("is_unanswerable"),
                    "answer": item.get("ground_truth_answer"),
                    "acceptable": item.get("acceptable_sources"),
                },
                ensure_ascii=False,
            )
        )
