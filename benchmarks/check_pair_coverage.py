"""Diagnostic: which paired-subset query IDs are covered by which provider, across all run files."""
import glob
import json
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

subset = json.load(open("benchmarks/tavily_paired_subset.json", encoding="utf-8"))
ids = sorted(x["id"] for x in subset)

rows = []
for p in sorted(glob.glob("reports/benchmark_runs/run_*.jsonl")):
    file_rows = [json.loads(line) for line in open(p, encoding="utf-8")]
    rows.extend(file_rows)

per_provider = defaultdict(set)
for r in rows:
    if r["provider"] in ("tavily", "ddgs") and r["status"] != "unavailable":
        per_provider[r["provider"]].add(r["query_id"])

for prov in ("tavily", "ddgs"):
    cov = sorted(per_provider[prov])
    missing = sorted(set(ids) - set(cov))
    print(f"{prov}: covered={len(cov)} missing={len(missing)}")
    if missing:
        print(f"  missing ids: {missing}")
