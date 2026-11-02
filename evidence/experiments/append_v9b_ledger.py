import hashlib, json

files = [
    "reports/three-system-comparison/raw-v9b-2026-11-02/three_system_results.jsonl",
    "reports/three-system-comparison/raw-v9b-2026-11-02/summary.json",
    "reports/three-system-comparison/THREE_SYSTEM_100Q_EXTENSION_2026-11-02.md",
]
outs = {p: hashlib.sha256(open(p, "rb").read()).hexdigest() for p in files}
entry = {
    "id": "EXP-V9B-100Q",
    "class": "REAL",
    "kind": "three-system benchmark 100-query extension",
    "dataset": "benchmarks/eval_dataset_expanded.json (first 100)",
    "dataset_sha256": "6130548dacb595da44a0973e66c4e3a44836846baf16a97ef1ca87664f2d065f",
    "started_utc": "2026-11-02T22:03Z",
    "ended_utc": "2026-11-02T22:43Z",
    "git_commit": "475a6ff",
    "systems": {
        "sys1": "local keyless (ddg,mwmbl,wikipedia)",
        "sys2": "https://weblens-16131012091.us-central1.run.app",
        "sys3": "tavily direct (100 credits consumed)",
    },
    "key_results": {
        "sys1": {"p50_ms": 922.7, "prec_at5": 0.688, "support": 0.80, "tokens": 425.8, "credits": 0, "success": 1.0},
        "sys2": {"p50_ms": 1112.1, "prec_at5": 0.646, "support": 0.76, "tokens": 426.9, "credits": 0, "success": 0.99},
        "sys3": {"p50_ms": 2381.6, "prec_at5": 0.756, "support": 0.90, "tokens": 1527.3, "credits": 100, "success": 1.0},
    },
    "caveat": "false-confidence flags (6/6/7) confined to fabricated-entity trap category; scoring heuristic, not validated hallucination",
}
entry["outputs"] = outs
with open("evidence/ledger.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps(entry) + "\n")
print("appended EXP-V9B-100Q")
