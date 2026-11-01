"""Final merged tavily-vs-ddgs paired-stats computation across all completed run files."""
import glob
import json
import re
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

subset = json.load(open("benchmarks/tavily_paired_subset.json", encoding="utf-8"))
labels = {x["id"]: x for x in subset}

rows = []
for p in sorted(glob.glob("reports/benchmark_runs/run_*.jsonl")):
    rows.extend(json.loads(line) for line in open(p, encoding="utf-8"))

rows = [r for r in rows if r["provider"] in ("tavily", "ddgs")]
rows = [r for r in rows if r["status"] != "unavailable"]

for r in rows:
    if "results" not in r and r.get("raw_response"):
        try:
            r["results"] = json.loads(r["raw_response"])
        except Exception:
            r["results"] = []

per_q = defaultdict(dict)
for r in rows:
    per_q[r["provider"]][r["query_id"]] = r


def answer_in_results(gt, results):
    text = " ".join((r.get("title", "") + " " + r.get("snippet", "")) for r in results).lower()
    gt_norm = gt.lower().replace("metre", "meter").replace("metres", "meters")
    if gt_norm in text:
        return True
    digits = "".join(c for c in gt if c.isdigit())
    if len(digits) >= 4 and digits in "".join(c for c in text if c.isdigit()):
        return True
    toks = [t for t in re.sub(r"[,.\-]", " ", gt_norm).split() if len(t) > 2]
    hits = sum(1 for t in toks if t in text)
    return bool(toks) and hits >= max(1, int(len(toks) * 0.5))


def pct(values, p):
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)


stats = {}
for prov in ("tavily", "ddgs"):
    qv = per_q[prov]
    res_lats = [r["latency_sec"] for r in qv.values() if r["status"] == "success"]
    toks = [r["tokens_returned"] for r in qv.values() if r.get("tokens_returned") is not None]
    supp = denom = 0
    for qid, r in sorted(qv.items()):
        lab = labels.get(qid)
        if not lab or lab.get("is_unanswerable"):
            continue
        denom += 1
        if r["status"] == "success" and answer_in_results(lab["ground_truth_answer"], r.get("results") or []):
            supp += 1
    st = Counter(r["status"] for r in qv.values())
    paired_common = sorted(set(qv) & set(per_q["tavily"] if prov == "ddgs" else per_q["ddgs"]))
    lat_pairs = [(qv[q]["latency_sec"], per_q["tavily" if prov == "ddgs" else "ddgs"][q]["latency_sec"]) for q in paired_common]
    wins = sum(1 for a, b in lat_pairs if a < b) 
    stats[prov] = {
        "n_queries": len(qv),
        "statuses": dict(st),
        "success_latency_p50_s": round(pct(res_lats, 50), 3),
        "success_latency_p95_s": round(pct(res_lats, 95), 3),
        "tokens_median": round(pct(toks, 50), 1),
        "tokens_mean": round(sum(toks) / max(len(toks), 1), 1),
        "tokens_p95": round(pct(toks, 95), 1),
        "result_count_mean": round(sum(r["result_count"] for r in qv.values()) / max(len(qv), 1), 2),
        "answer_support": f"{supp}/{denom}",
        "paired_with_other_n": len(paired_common),
        "latency_wins_head_to_head": f"{wins}/{len(lat_pairs)}",
    }

out = {
    "measured_at": "2026-10-24T05:35:00Z",
    "rows_valid_total": len(rows),
    "method_note": (
        "Merged across all provider-comparison run files; 39 'unavailable' rows from two key-env-bug "
        "attempts excluded; later successful rows supersede earlier per (provider, query). Scorer: "
        "ground-truth containment in title+snippet text (exact / >=4-digit / >=50% token match). "
        "Heuristic scorer - describe capability, not ground truth."
    ),
    "per_provider": stats,
}
json.dump(out, open("reports/benchmark_runs/paired_provider_stats.json", "w", encoding="utf-8"), indent=2)
print(json.dumps(out, indent=2))
