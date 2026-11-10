"""Paired Interleaved Evaluation Runner: WebLens Independent vs Tavily API.

Executes a stratified pilot evaluation comparing WebLens (independent keyless)
against Tavily API across quality, latency, token efficiency, reliability, and cost.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure weblens and weblens-lab are importable
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "weblens" / "src"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "weblens-lab"))
sys.path.insert(0, str(ROOT))

from weblens.config import Settings
from weblens.urls import registrable_domain
from adapters.tavily_adapter.adapter import TavilyAdapter
from adapters.weblens_adapter.adapter import WebLensAdapter


def load_stratified_pilot(dataset_path: Path, count_per_stratum: int = 1) -> list[dict[str, Any]]:
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    by_category: dict[str, list[dict[str, Any]]] = {}
    for item in data:
        cat = item.get("category", "general")
        by_category.setdefault(cat, []).append(item)

    pilot: list[dict[str, Any]] = []
    for cat in sorted(by_category.keys()):
        pilot.extend(by_category[cat][:count_per_stratum])

    return pilot


def evaluate_search_precision(results: list[Any], item: dict[str, Any]) -> tuple[float, bool]:
    if not results:
        return 0.0, False

    acceptable = [dom.lower() for dom in item.get("acceptable_sources", [])]
    gt_answer = str(item.get("ground_truth_answer", "")).lower()

    relevant_count = 0
    answer_supported = False

    for r in results[:5]:
        text = (getattr(r, "content", "") + " " + getattr(r, "title", "")).lower()
        url = getattr(r, "url", "").lower()
        dom = registrable_domain(url).lower() if url else ""

        is_acceptable_src = any(acc in dom or acc in url for acc in acceptable)
        has_answer_content = bool(gt_answer and gt_answer in text)

        if is_acceptable_src or has_answer_content:
            relevant_count += 1
            if has_answer_content:
                answer_supported = True

    precision = round(relevant_count / min(len(results), 5), 3)
    return precision, answer_supported


async def run_evaluation(pilot_queries: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_file = output_dir / "paired_pilot.jsonl"

    settings = Settings()
    # Explicitly enforce independent WebLens
    settings.search_providers = "ddg,mwmbl,wikipedia"
    settings.tavily_api_key = None

    weblens = WebLensAdapter(settings=settings, independent=True)
    tavily = TavilyAdapter()

    records: list[dict[str, Any]] = []

    print(f"Starting paired evaluation on {len(pilot_queries)} stratified queries...")

    for i, item in enumerate(pilot_queries):
        qid = item["id"]
        query = item["query"]
        cat = item.get("category", "unknown")
        unanswerable = item.get("is_unanswerable", False)

        # Interleave execution order to minimize network timing bias
        order = ["weblens", "tavily"] if i % 2 == 0 else ["tavily", "weblens"]

        weblens_res = None
        tavily_res = None

        for system in order:
            if system == "weblens":
                weblens_res = await weblens.search(query, max_results=5)
                await asyncio.sleep(0.5)  # Politeness interval
            else:
                tavily_res = await tavily.search(query, max_results=5)
                await asyncio.sleep(0.5)

        assert weblens_res is not None and tavily_res is not None

        wl_prec, wl_supp = evaluate_search_precision(weblens_res.results, item)
        tv_prec, tv_supp = evaluate_search_precision(tavily_res.results, item)

        # False confidence: unanswerable query but claiming high confidence or precision
        wl_false_conf = unanswerable and (wl_prec > 0.4)
        tv_false_conf = unanswerable and (tv_prec > 0.4)

        rec = {
            "case_id": qid,
            "category": cat,
            "query": query,
            "ground_truth": item.get("ground_truth_answer"),
            "is_unanswerable": unanswerable,
            "order": order,
            "weblens": {
                "status": weblens_res.status,
                "latency_ms": round(weblens_res.latency_ms, 2),
                "tokens": weblens_res.tokens_returned,
                "precision_at_5": wl_prec,
                "answer_supported": wl_supp,
                "false_confidence": wl_false_conf,
                "credits_used": weblens_res.credits_used,
                "result_count": len(weblens_res.results),
                "first_url": weblens_res.results[0].url if weblens_res.results else None,
            },
            "tavily": {
                "status": tavily_res.status,
                "latency_ms": round(tavily_res.latency_ms, 2),
                "tokens": tavily_res.tokens_returned,
                "precision_at_5": tv_prec,
                "answer_supported": tv_supp,
                "false_confidence": tv_false_conf,
                "credits_used": tavily_res.credits_used,
                "result_count": len(tavily_res.results),
                "first_url": tavily_res.results[0].url if tavily_res.results else None,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        records.append(rec)
        print(
            f"[{i+1}/{len(pilot_queries)}] {cat[:18]:<18} | "
            f"WL: {weblens_res.latency_ms:6.1f}ms (P@5={wl_prec:0.2f}) | "
            f"TV: {tavily_res.latency_ms:6.1f}ms (P@5={tv_prec:0.2f})"
        )

    await weblens.close()

    # Write raw output
    with open(raw_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    # Aggregate metrics
    wl_lats = sorted(r["weblens"]["latency_ms"] for r in records)
    tv_lats = sorted(r["tavily"]["latency_ms"] for r in records)

    def pctl(arr: list[float], p: float) -> float:
        idx = int(round(p * (len(arr) - 1)))
        return arr[idx]

    n = len(records)
    summary = {
        "n_queries": n,
        "sample_time": datetime.now(timezone.utc).isoformat(),
        "latency_ms": {
            "weblens": {
                "p50": pctl(wl_lats, 0.50),
                "p90": pctl(wl_lats, 0.90),
                "p95": pctl(wl_lats, 0.95),
                "mean": round(sum(wl_lats) / n, 2),
                "min": wl_lats[0],
                "max": wl_lats[-1],
            },
            "tavily": {
                "p50": pctl(tv_lats, 0.50),
                "p90": pctl(tv_lats, 0.90),
                "p95": pctl(tv_lats, 0.95),
                "mean": round(sum(tv_lats) / n, 2),
                "min": tv_lats[0],
                "max": tv_lats[-1],
            },
        },
        "quality": {
            "weblens": {
                "mean_precision_at_5": round(sum(r["weblens"]["precision_at_5"] for r in records) / n, 3),
                "answer_supported_rate": round(sum(1 for r in records if r["weblens"]["answer_supported"]) / n, 3),
                "false_confidence_count": sum(1 for r in records if r["weblens"]["false_confidence"]),
                "success_rate": round(sum(1 for r in records if r["weblens"]["status"] == "ok") / n, 3),
            },
            "tavily": {
                "mean_precision_at_5": round(sum(r["tavily"]["precision_at_5"] for r in records) / n, 3),
                "answer_supported_rate": round(sum(1 for r in records if r["tavily"]["answer_supported"]) / n, 3),
                "false_confidence_count": sum(1 for r in records if r["tavily"]["false_confidence"]),
                "success_rate": round(sum(1 for r in records if r["tavily"]["status"] == "ok") / n, 3),
            },
        },
        "tokens_and_cost": {
            "weblens": {
                "mean_tokens": round(sum(r["weblens"]["tokens"] for r in records) / n, 1),
                "total_credits": sum(r["weblens"]["credits_used"] for r in records),
                "cost_usd": 0.0,
            },
            "tavily": {
                "mean_tokens": round(sum(r["tavily"]["tokens"] for r in records) / n, 1),
                "total_credits": sum(r["tavily"]["credits_used"] for r in records),
                "cost_usd": round(sum(r["tavily"]["credits_used"] for r in records) * 0.005, 3),  # based on standard $5/1000 credits
            },
        },
    }

    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    dataset_file = ROOT / "benchmarks" / "eval_dataset_expanded.json"
    pilot = load_stratified_pilot(dataset_file, count_per_stratum=1)
    # Ensure at least 18 strata are represented
    print(f"Loaded {len(pilot)} stratified test cases.")
    out = ROOT / "reports" / "tavily-weblens-comparison" / "raw"
    res = asyncio.run(run_evaluation(pilot, out))
    print("\n=== Paired Evaluation Summary ===")
    print(json.dumps(res, indent=2))
