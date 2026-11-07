import json
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "scratch/eval_current_mwmbl-wikipedia-hints.jsonl")
rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
split = sys.argv[2] if len(sys.argv) > 2 else ""
graded = [
    r
    for r in rows
    if (not split or r["item"].get("split") == split)
    and not r["item"].get("is_unanswerable")
    and r["item"].get("acceptable_sources")
]
graded.sort(key=lambda r: r["score"]["p5"])
for r in graded:
    item = r["item"]
    print(
        f"{r['score']['p5']:.2f} {item['id']:32} {item['query'][:85]} "
        f"grades={r['score']['grades']} ANS {item['ground_truth_answer']!r} "
        f"ACC {item['acceptable_sources']}"
    )
