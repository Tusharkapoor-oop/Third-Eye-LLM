"""Independent Stage 7 analysis from frozen labels and raw JSONL evidence."""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from benchmarks.stage7_common import (
    DATASET_PATH,
    MANIFEST_PATH,
    RAW_DIR,
    REPORT_DIR,
    is_relevant,
    load_dataset,
    mean,
    paired_delta_ci,
    percentile,
    read_jsonl,
    support,
    write_json,
)

PROVIDERS = ("direct_tavily", "weblens_keyless", "weblens_tavily")
RESEARCH_PROVIDERS = ("weblens_keyless", "weblens_tavily")
OK_STATUS = {"ok", "partial", "possibly_outdated", "no_reliable_result"}


def latest(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("query_id") or row.get("url") or ""), str(row.get("provider") or row.get("mode") or ""))
        old = out.get(key)
        if old is None or str(row.get("at", "")) >= str(old.get("at", "")):
            out[key] = row
    return list(out.values())


def host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def search_eval(rec: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    results = rec.get("results") or []
    flags = [is_relevant(str(x.get("u") or ""), row) for x in results]
    urls = [str(x.get("u") or "") for x in results]

    def p(k: int) -> float:
        return round(sum(flags[:k]) / k, 4)

    first = next((i + 1 for i, flag in enumerate(flags[:10]) if flag), None)
    text = "\n".join(str(x.get("t") or "") + "\n" + str(x.get("s") or "") for x in results)
    return {
        "returned": len(results),
        "relevant": sum(flags),
        "precision_at_1": p(1),
        "precision_at_3": p(3),
        "precision_at_5": p(5),
        "precision_at_10": p(10),
        "hit_at_5": 1.0 if any(flags[:5]) else 0.0,
        "hit_at_10": 1.0 if any(flags[:10]) else 0.0,
        "mrr_at_10": round(1 / first, 4) if first else 0.0,
        "ndcg_at_5": round(sum(1 / math.log2(i + 2) for i, f in enumerate(flags[:5]) if f), 4),
        "ndcg_at_10": round(sum(1 / math.log2(i + 2) for i, f in enumerate(flags[:10]) if f), 4),
        "duplicate_rate": round(1 - len(set(urls)) / len(urls), 4) if urls else 0.0,
        "url_validity": round(sum(1 for u in urls if host(u) and u.startswith(("http://", "https://"))) / len(urls), 4)
        if urls
        else 0.0,
        "unique_domains": len({host(u) for u in urls if host(u)}),
        "support": rec.get("support_compact") if rec.get("support_compact") is not None else support(row, text),
        "support_full": rec.get("support_full"),
        "latency_ms": float(rec.get("latency_ms") or 0.0),
        "payload_tokens": int((rec.get("tokens") or {}).get("payload") or 0),
        "raw_tokens": int((rec.get("tokens") or {}).get("raw_provider") or 0),
        "status": rec.get("status"),
    }


def research_eval(rec: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    findings = rec.get("findings") or []
    text = "\n".join(str(x.get("c") or "") for x in findings)
    return {
        "status": rec.get("status"),
        "latency_ms": float(rec.get("latency_ms") or 0.0),
        "payload_tokens": int((rec.get("tokens") or {}).get("payload") or 0),
        "finding_tokens": int((rec.get("tokens") or {}).get("finding_text") or 0),
        "findings": len(findings),
        "support": rec.get("support") if rec.get("support") is not None else support(row, text),
        "status_match": bool(rec.get("status_match")),
        "abstained": bool(rec.get("abstained")),
        "false_confidence": bool(rec.get("false_confidence")),
        "conflict": bool(rec.get("conflict_flagged")),
        "citation_errors": len(rec.get("citation_errors") or []),
    }


def summ(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": mean(values),
        "p50": percentile(values, 50),
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
    }


def paired(
    left: dict[str, dict[str, Any]],
    right: dict[str, dict[str, Any]],
    rows: dict[str, dict[str, Any]],
    fn,
    metric: str,
    *,
    answerable_only: bool = True,
) -> dict[str, Any]:
    lvals: list[float] = []
    rvals: list[float] = []
    for qid, row in rows.items():
        if answerable_only and not row["answerable"]:
            continue
        lrec, rrec = left.get(qid), right.get(qid)
        if not lrec or not rrec or lrec.get("status") == "error" or rrec.get("status") == "error":
            continue
        lm, rm = fn(lrec, row), fn(rrec, row)
        lv, rv = lm.get(metric), rm.get(metric)
        if lv is None or rv is None:
            continue
        lvals.append(float(lv))
        rvals.append(float(rv))
    d = paired_delta_ci(lvals, rvals)
    return {
        "n": d["n"],
        "left_mean": d.get("mean_left"),
        "right_mean": d.get("mean_right"),
        "delta": d.get("mean"),
        "lo": d.get("lo"),
        "hi": d.get("hi"),
    }


def verdict(d: dict[str, Any], practical: float, higher_better: bool = True) -> str:
    if not d or not d.get("n"):
        return "INCONCLUSIVE (no paired observations)"
    lo, hi, point = d["lo"], d["hi"], d["delta"]
    left_better = point > 0 if higher_better else point < 0
    if lo > 0 or hi < 0:
        if abs(point) < practical:
            return "TIE / below practical threshold (95% CI excludes zero)"
        return "LEFT better (practical)" if left_better else "RIGHT better (practical)"
    return "TIE / INCONCLUSIVE (95% CI includes zero)"


def provider_block(
    records: list[dict[str, Any]], rows: dict[str, dict[str, Any]], fn, *, answerable_only: bool = True
) -> dict[str, Any]:
    valid = [r for r in records if r.get("query_id") in rows]
    answerable = [(r, rows[r["query_id"]]) for r in valid if rows[r["query_id"]]["answerable"]]
    metrics = [fn(r, row) for r, row in answerable] if answerable_only else [fn(r, rows[r["query_id"]]) for r in valid]
    supports = [m["support"] for m in metrics if m.get("support") is not None]
    return {
        "records": len(valid),
        "answerable_records": len(answerable),
        "status_counts": dict(Counter(str(r.get("status")) for r in valid)),
        "precision_at_1": mean([m["precision_at_1"] for m in metrics]) if answerable_only else None,
        "precision_at_3": mean([m["precision_at_3"] for m in metrics]) if answerable_only else None,
        "precision_at_5": mean([m["precision_at_5"] for m in metrics]) if answerable_only else None,
        "precision_at_10": mean([m["precision_at_10"] for m in metrics]) if answerable_only else None,
        "hit_at_5": mean([m["hit_at_5"] for m in metrics]) if answerable_only else None,
        "hit_at_10": mean([m["hit_at_10"] for m in metrics]) if answerable_only else None,
        "mrr_at_10": mean([m["mrr_at_10"] for m in metrics]) if answerable_only else None,
        "ndcg_at_5": mean([m["ndcg_at_5"] for m in metrics]) if answerable_only else None,
        "ndcg_at_10": mean([m["ndcg_at_10"] for m in metrics]) if answerable_only else None,
        "duplicate_rate": mean([m["duplicate_rate"] for m in metrics]) if answerable_only else None,
        "url_validity": mean([m["url_validity"] for m in metrics]) if answerable_only else None,
        "support": mean([1.0 if s else 0.0 for s in supports]) if supports else None,
        "support_n": len(supports),
        "latency_ms": summ([m["latency_ms"] for m in metrics]),
        "payload_tokens": summ([m["payload_tokens"] for m in metrics]),
        "raw_tokens": summ([m["raw_tokens"] for m in metrics]),
    }


def research_block(records: list[dict[str, Any]], rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    valid = [r for r in records if r.get("query_id") in rows]
    answerable = [(r, rows[r["query_id"]]) for r in valid if rows[r["query_id"]]["answerable"]]
    unans = [(r, rows[r["query_id"]]) for r in valid if rows[r["query_id"]]["expect_abstention"]]
    conflicts = [(r, rows[r["query_id"]]) for r in valid if rows[r["query_id"]]["expect_conflict"]]
    metrics = [research_eval(r, row) for r, row in answerable]
    unans_m = [research_eval(r, row) for r, row in unans]
    conf_m = [research_eval(r, row) for r, row in conflicts]
    numeric = [(r, row) for r, row in conflicts if row.get("provenance") == "weblens_benchmarks_queries_v1"]
    conceptual = [(r, row) for r, row in conflicts if row.get("provenance") == "root_eval_dataset_v1"]
    supports = [m["support"] for m in metrics if m.get("support") is not None]
    return {
        "records": len(valid),
        "answerable_records": len(metrics),
        "unanswerable_records": len(unans_m),
        "conflict_records": len(conf_m),
        "status_counts": dict(Counter(str(r.get("status")) for r in valid)),
        "support": mean([1.0 if s else 0.0 for s in supports]) if supports else None,
        "support_n": len(supports),
        "status_match": mean([1.0 if m["status_match"] else 0.0 for m in metrics]) if metrics else None,
        "no_result_accuracy": mean([1.0 if m["abstained"] else 0.0 for m in unans_m]) if unans_m else None,
        "false_confidence_rate": mean([1.0 if m["false_confidence"] else 0.0 for m in unans_m]) if unans_m else None,
        "conflict_recall_numeric": mean([1.0 if research_eval(r, row)["conflict"] else 0.0 for r, row in numeric])
        if numeric
        else None,
        "conflict_recall_conceptual": mean([1.0 if research_eval(r, row)["conflict"] else 0.0 for r, row in conceptual])
        if conceptual
        else None,
        "conflict_recall_all": mean([1.0 if m["conflict"] else 0.0 for m in conf_m]) if conf_m else None,
        "citation_error_rate": mean([1.0 if m["citation_errors"] else 0.0 for m in metrics]) if metrics else None,
        "citation_errors_total": sum(m["citation_errors"] for m in metrics),
        "latency_ms": summ([float(r.get("latency_ms") or 0) for r in valid]),
        "payload_tokens": summ([int((r.get("tokens") or {}).get("payload") or 0) for r in valid]),
        "finding_tokens": summ([int((r.get("tokens") or {}).get("finding_text") or 0) for r in valid]),
    }


def main() -> int:
    dataset = load_dataset()
    rows = {r["id"]: r for r in dataset}
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    search = {s: latest(read_jsonl(RAW_DIR / f"search_{s}.jsonl")) for s in ("dev", "test")}
    research = {s: latest(read_jsonl(RAW_DIR / f"research_{s}.jsonl")) for s in ("dev", "test")}
    all_search = latest(search["dev"] + search["test"])
    all_research = latest(research["dev"] + research["test"])

    s_idx: dict[str, dict[str, dict[str, Any]]] = {p: {} for p in PROVIDERS}
    r_idx: dict[str, dict[str, dict[str, Any]]] = {p: {} for p in RESEARCH_PROVIDERS}
    for rec in all_search:
        if rec.get("provider") in s_idx:
            s_idx[rec["provider"]][rec["query_id"]] = rec
    for rec in all_research:
        if rec.get("provider") in r_idx:
            r_idx[rec["provider"]][rec["query_id"]] = rec

    quality: dict[str, Any] = {}
    for split in ("dev", "test", "combined"):
        split_rows = dataset if split == "combined" else [r for r in dataset if r["split"] == split]
        split_ids = {r["id"] for r in split_rows}
        s_rows = all_search if split == "combined" else search[split]
        r_rows = all_research if split == "combined" else research[split]
        quality[split] = {
            "rows": len(split_rows),
            "search": {
                p: provider_block(
                    [r for r in s_rows if r.get("provider") == p and r.get("query_id") in split_ids], rows, search_eval
                )
                for p in PROVIDERS
                if any(r.get("provider") == p and r.get("query_id") in split_ids for r in s_rows)
            },
            "research": {
                p: research_block(
                    [r for r in r_rows if r.get("provider") == p and r.get("query_id") in split_ids], rows
                )
                for p in RESEARCH_PROVIDERS
                if any(r.get("provider") == p and r.get("query_id") in split_ids for r in r_rows)
            },
        }

    comps: dict[str, Any] = {}
    comps["direct_vs_keyless_precision_at_5"] = paired(
        s_idx["direct_tavily"], s_idx["weblens_keyless"], rows, search_eval, "precision_at_5"
    )
    comps["direct_vs_keyless_support"] = paired(
        s_idx["direct_tavily"], s_idx["weblens_keyless"], rows, search_eval, "support"
    )
    comps["direct_vs_keyless_latency_ms"] = paired(
        s_idx["direct_tavily"], s_idx["weblens_keyless"], rows, search_eval, "latency_ms"
    )
    comps["direct_vs_keyless_payload_tokens"] = paired(
        s_idx["direct_tavily"], s_idx["weblens_keyless"], rows, search_eval, "payload_tokens"
    )
    comps["direct_vs_weblens_tavily_precision_at_5"] = paired(
        s_idx["direct_tavily"], s_idx["weblens_tavily"], rows, search_eval, "precision_at_5"
    )
    comps["direct_vs_weblens_tavily_support"] = paired(
        s_idx["direct_tavily"], s_idx["weblens_tavily"], rows, search_eval, "support"
    )
    comps["direct_vs_weblens_tavily_latency_ms"] = paired(
        s_idx["direct_tavily"], s_idx["weblens_tavily"], rows, search_eval, "latency_ms"
    )
    comps["keyless_vs_weblens_tavily_research_support"] = paired(
        r_idx["weblens_keyless"], r_idx["weblens_tavily"], rows, research_eval, "support"
    )
    comps["keyless_vs_weblens_tavily_research_latency_ms"] = paired(
        r_idx["weblens_keyless"], r_idx["weblens_tavily"], rows, research_eval, "latency_ms"
    )

    categories: dict[str, Any] = {}
    for category in sorted({r["category"] for r in dataset}):
        cat_ids = {r["id"] for r in dataset if r["category"] == category}
        cat_rows = [r for r in dataset if r["id"] in cat_ids]
        entry: dict[str, Any] = {"rows": len(cat_rows), "search": {}, "research": {}}
        for p in PROVIDERS:
            recs = [r for r in all_search if r.get("provider") == p and r.get("query_id") in cat_ids]
            if recs:
                entry["search"][p] = provider_block(recs, rows, search_eval)
        for p in RESEARCH_PROVIDERS:
            recs = [r for r in all_research if r.get("provider") == p and r.get("query_id") in cat_ids]
            if recs:
                entry["research"][p] = research_block(recs, rows)
        categories[category] = entry

    extraction_rows = read_jsonl(RAW_DIR / "extraction.jsonl")
    extraction: dict[str, Any] = {"records": len(extraction_rows), "variants": {}}
    for key in ("tavily", "weblens_full", "weblens_query"):
        vals = [r[key] for r in extraction_rows if key in r]
        extraction["variants"][key] = {
            "n": len(vals),
            "status_counts": dict(Counter(str(v.get("status")) for v in vals)),
            "support": mean([1.0 if v.get("support") else 0.0 for v in vals if v.get("support") is not None])
            if any(v.get("support") is not None for v in vals)
            else None,
            "support_n": sum(1 for v in vals if v.get("support") is not None),
            "latency_ms": summ([float(v.get("latency_ms") or 0) for v in vals]),
            "text_tokens": summ([float(v.get("text_tokens") or 0) for v in vals]),
            "chars": summ([float(v.get("chars") or 0) for v in vals]),
        }
    pairs = [
        r
        for r in extraction_rows
        if r.get("tavily", {}).get("support") is not None and r.get("weblens_full", {}).get("support") is not None
    ]
    extraction["paired"] = {
        "n": len(pairs),
        "tavily_support": mean([1.0 if r["tavily"]["support"] else 0.0 for r in pairs]) if pairs else None,
        "weblens_support": mean([1.0 if r["weblens_full"]["support"] else 0.0 for r in pairs]) if pairs else None,
        "tavily_latency_ms": summ([float(r["tavily"]["latency_ms"]) for r in pairs]),
        "weblens_latency_ms": summ([float(r["weblens_full"]["latency_ms"]) for r in pairs]),
        "tavily_text_tokens": summ([float(r["tavily"]["text_tokens"]) for r in pairs]),
        "weblens_text_tokens": summ([float(r["weblens_full"]["text_tokens"]) for r in pairs]),
    }

    browser: dict[str, Any] = {}
    for rec in read_jsonl(RAW_DIR / "browser_fixture.jsonl"):
        key = f"{rec.get('fixture')}:{rec.get('mode')}"
        browser[key] = {
            "status": rec.get("status"),
            "latency_ms": rec.get("latency_ms"),
            "tokens": rec.get("tokens"),
            "proxy_requests": rec.get("proxy_requests"),
            "warnings": rec.get("warnings"),
            "injection": rec.get("injection"),
            "passage_injection": rec.get("passage_injection"),
            "text_prefix": str(rec.get("text") or "")[:160],
        }

    load: dict[str, Any] = {}
    for rec in read_jsonl(RAW_DIR / "load.jsonl"):
        load[f"{rec.get('provider')}:c{rec.get('concurrency')}"] = {
            "queries": rec.get("queries"),
            "wall_ms": rec.get("wall_ms"),
            "latency": rec.get("latency"),
            "statuses": rec.get("statuses"),
        }

    crawl: dict[str, Any] = {}
    for rec in read_jsonl(RAW_DIR / "crawl_map.jsonl"):
        crawl[f"{rec.get('provider')}:{rec.get('op')}"] = {
            "status": rec.get("status"),
            "http_status": rec.get("http_status"),
            "latency_ms": rec.get("latency_ms"),
            "retries": rec.get("retries"),
            "results": len((rec.get("raw") or {}).get("results") or []) if isinstance(rec.get("raw"), dict) else None,
        }

    verdicts = {
        "P1_precision_at_5_direct_vs_keyless": verdict(comps["direct_vs_keyless_precision_at_5"], 0.05),
        "P2_support_direct_vs_keyless": verdict(comps["direct_vs_keyless_support"], 0.05),
        "P3_research_support_keyless_vs_weblens_tavily": verdict(
            comps["keyless_vs_weblens_tavily_research_support"], 0.05
        ),
        "P4_search_latency_direct_vs_keyless": verdict(comps["direct_vs_keyless_latency_ms"], 0.0, False),
        "P5_payload_tokens_direct_vs_keyless": verdict(comps["direct_vs_keyless_payload_tokens"], 0.0, False),
    }

    analysis = {
        "campaign_id": "stage7-20261028-a4a64151",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": {
            "path": str(DATASET_PATH.relative_to(REPORT_DIR.parents[1])).replace("\\", "/"),
            "sha256": manifest["dataset_sha256"],
            "rows": manifest["rows"],
            "splits": manifest["splits"],
            "categories": manifest["categories"],
        },
        "quality": quality,
        "paired": comps,
        "verdicts": verdicts,
        "categories": categories,
        "extraction": extraction,
        "browser": browser,
        "load": load,
        "crawl": crawl,
        "evidence": {
            "search_records": len(all_search),
            "research_records": len(all_research),
            "extraction_records": len(extraction_rows),
            "browser_records": len(browser),
            "load_records": len(load),
            "crawl_records": len(crawl),
            "pre_fix_extraction_records": len(read_jsonl(RAW_DIR / "extraction_pre_fix.jsonl")),
        },
    }

    write_json(REPORT_DIR / "data" / "analysis.json", analysis)
    write_json(
        REPORT_DIR / "QUALITY-RESULTS.json",
        {
            "campaign_id": analysis["campaign_id"],
            "dataset": analysis["dataset"],
            "quality": analysis["quality"],
            "paired": analysis["paired"],
            "verdicts": analysis["verdicts"],
            "categories": analysis["categories"],
            "caveats": [
                "Precision uses strict labelled-domain membership, not human relevance.",
                "Recall@5/10 is not estimable: no exhaustive relevant-URL set exists. Domain hit rate is not recall.",
                "nDCG is binary with ideal DCG=1; it is rank-sensitive but not graded relevance.",
                "WebLens-Tavily is an optimization layer over Tavily, not an independent search engine.",
                "The 10,000-row synthetic corpus was excluded because its labels are placeholders.",
            ],
        },
    )
    write_json(
        REPORT_DIR / "PERFORMANCE-RESULTS.json",
        {
            "campaign_id": analysis["campaign_id"],
            "search": {s: {p: v["latency_ms"] for p, v in d["search"].items()} for s, d in quality.items()},
            "research": {s: {p: v["latency_ms"] for p, v in d["research"].items()} for s, d in quality.items()},
            "extraction": extraction,
            "browser": browser,
            "load": load,
            "crawl": crawl,
            "resource_note": (
                "Process memory was null on Windows because the ctypes process-memory probe failed; "
                "browser child-process RSS was not captured. Latency observations are wall-clock "
                "client-side measurements."
            ),
        },
    )
    write_json(
        REPORT_DIR / "COST-AND-TOKEN-RESULTS.json",
        {
            "campaign_id": analysis["campaign_id"],
            "budget": {
                "max_campaign_credits": 420,
                "hard_stop_remaining": 200,
                "account_usage_before": 170,
                "account_limit": 1000,
                "plan": "Researcher",
            },
            "search_tokens": {s: {p: v["payload_tokens"] for p, v in d["search"].items()} for s, d in quality.items()},
            "research_tokens": {
                s: {p: v["payload_tokens"] for p, v in d["research"].items()} for s, d in quality.items()
            },
            "caveat": (
                "cl100k_base counts of delivered JSON. No model inference occurred; these are not "
                "billed model tokens. The usage endpoint returned HTTP 429 at least once; "
                "call-count accounting is preserved in raw meta files."
            ),
        },
    )
    print(json.dumps({"ok": True, "verdicts": verdicts, "evidence": analysis["evidence"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
