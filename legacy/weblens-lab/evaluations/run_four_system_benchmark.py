"""Four-System Competitive Benchmark Runner:
System 1: Local WebLens MCP
System 2: Deployed WebLens MCP (Google Cloud Run)
System 3: Tavily Direct API
System 4: Google Gemini API (Native Grounded Search)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "weblens" / "src"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "weblens-lab"))

from adapters.deployed_adapter.adapter import DeployedWebLensAdapter
from adapters.gemini_adapter.adapter import GeminiAdapter
from adapters.tavily_adapter.adapter import TavilyAdapter
from adapters.weblens_adapter.adapter import WebLensAdapter
from weblens.config import Settings
from weblens.urls import registrable_domain


def evaluate_precision(results: list[Any], item: dict[str, Any]) -> tuple[float, bool]:
    if not results:
        return 0.0, False

    acceptable = [dom.lower() for dom in item.get("acceptable_sources", [])]
    gt_answer = str(item.get("ground_truth_answer", "")).lower()

    relevant_count = 0
    answer_supported = False

    for r in results[:5]:
        content = getattr(r, "content", "") or ""
        title = getattr(r, "title", "") or ""
        text = (content + " " + title).lower()
        url = (getattr(r, "url", "") or "").lower()
        dom = registrable_domain(url).lower() if url else ""

        is_acceptable = any(acc in dom or acc in url for acc in acceptable) if acceptable else False
        has_content = bool(gt_answer and any(tok in text for tok in gt_answer.split() if len(tok) > 3))

        if is_acceptable or has_content:
            relevant_count += 1
            if has_content:
                answer_supported = True

    precision = round(relevant_count / min(len(results), 5), 3) if results else 0.0
    return precision, answer_supported


async def run_four_system_benchmark(
    dataset_path: Path,
    output_dir: Path,
    *,
    sample_size: int = 15,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_file = output_dir / "four_system_results.jsonl"

    with open(dataset_path, "r", encoding="utf-8") as f:
        all_items: list[dict[str, Any]] = json.load(f)

    eval_items = all_items[:sample_size]

    settings = Settings()
    settings.search_providers = "ddg,mwmbl,wikipedia"
    settings.tavily_api_key = None

    sys1_local = WebLensAdapter(settings=settings, independent=True)
    sys2_deployed = DeployedWebLensAdapter()
    sys3_tavily = TavilyAdapter()
    sys4_gemini = GeminiAdapter()

    records: list[dict[str, Any]] = []
    print(f"Starting Four-System Benchmark on {len(eval_items)} queries...")
    print(f" - System 1: Local WebLens MCP")
    print(f" - System 2: Deployed WebLens MCP ({sys2_deployed.endpoint_url})")
    print(f" - System 3: Tavily Direct API")
    print(f" - System 4: Google Gemini API (Available: {sys4_gemini.is_available})")

    try:
        for idx, item in enumerate(eval_items):
            qid = item["id"]
            query = item["query"]
            category = item.get("category", "general")
            unanswerable = item.get("is_unanswerable", False)

            # Four-way rotation to prevent network ordering bias
            all_systems = [
                ("sys1_local", sys1_local),
                ("sys2_deployed", sys2_deployed),
                ("sys3_tavily", sys3_tavily),
                ("sys4_gemini", sys4_gemini),
            ]
            shift = idx % 4
            rotated_systems = all_systems[shift:] + all_systems[:shift]

            results_by_sys: dict[str, Any] = {}

            for sys_name, provider in rotated_systems:
                try:
                    res = await provider.search(query, max_results=5)
                    prec, supp = evaluate_precision(res.results, item)
                    false_conf = unanswerable and (prec > 0.4)
                    results_by_sys[sys_name] = {
                        "status": res.status,
                        "latency_ms": round(res.latency_ms, 1),
                        "precision_at_5": prec,
                        "answer_supported": supp,
                        "false_confidence": false_conf,
                        "tokens": res.tokens_returned,
                        "credits_used": res.credits_used,
                        "error": res.error,
                        "hit_count": len(res.results),
                    }
                except Exception as e:
                    results_by_sys[sys_name] = {
                        "status": "error",
                        "latency_ms": 0.0,
                        "precision_at_5": 0.0,
                        "answer_supported": False,
                        "false_confidence": False,
                        "tokens": 0,
                        "credits_used": 0.0,
                        "error": str(e),
                        "hit_count": 0,
                    }
                await asyncio.sleep(0.3)

            record = {
                "id": qid,
                "category": category,
                "query": query,
                "unanswerable": unanswerable,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "local_weblens": results_by_sys["sys1_local"],
                "deployed_weblens": results_by_sys["sys2_deployed"],
                "tavily_direct": results_by_sys["sys3_tavily"],
                "gemini_api": results_by_sys["sys4_gemini"],
            }
            records.append(record)

            with open(raw_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")

            print(f"[{idx+1}/{len(eval_items)}] {qid}: "
                  f"Local={results_by_sys['sys1_local']['latency_ms']}ms | "
                  f"Deployed={results_by_sys['sys2_deployed']['latency_ms']}ms | "
                  f"Tavily={results_by_sys['sys3_tavily']['latency_ms']}ms | "
                  f"Gemini Status={results_by_sys['sys4_gemini']['status']}")

    finally:
        await sys1_local.close()
        await sys2_deployed.close()

    n = len(records)
    if n == 0:
        return {"status": "error", "msg": "No records produced"}

    def calc_stats(sys_key: str) -> dict[str, Any]:
        lats = sorted([r[sys_key]["latency_ms"] for r in records if r[sys_key]["latency_ms"] > 0])
        p50 = lats[len(lats) // 2] if lats else 0.0
        p90 = lats[int(len(lats) * 0.9)] if lats else 0.0
        mean_lat = round(sum(lats) / len(lats), 1) if lats else 0.0

        precisions = [r[sys_key]["precision_at_5"] for r in records]
        mean_prec = round(sum(precisions) / n, 3)

        supp_count = sum(1 for r in records if r[sys_key]["answer_supported"])
        supp_rate = round(supp_count / n, 3)
        success_count = sum(1 for r in records if r[sys_key]["status"] == "ok")

        mean_tokens = round(sum(r[sys_key]["tokens"] for r in records) / n, 1)
        total_credits = sum(r[sys_key]["credits_used"] for r in records)

        return {
            "status": "active" if lats else "blocked_or_unavailable",
            "latency": {
                "p50_ms": p50,
                "p90_ms": p90,
                "mean_ms": mean_lat,
            },
            "quality": {
                "mean_precision_at_5": mean_prec,
                "answer_supported_rate": supp_rate,
                "success_rate": round(success_count / n, 3),
            },
            "tokens_and_cost": {
                "mean_tokens": mean_tokens,
                "total_credits": total_credits,
                "cost_usd": round(total_credits * 0.005, 4),
            },
        }

    summary = {
        "status": "ok",
        "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_queries_evaluated": n,
        "systems": {
            "system_1_local_weblens": calc_stats("local_weblens"),
            "system_2_deployed_weblens": calc_stats("deployed_weblens"),
            "system_3_tavily_direct": calc_stats("tavily_direct"),
            "system_4_google_gemini": calc_stats("gemini_api"),
        },
    }

    summary_file = output_dir / "four_system_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    dpath = ROOT / "weblens-lab" / "datasets" / "eval_benchmark_suite.json"
    out = ROOT / "reports" / "four-system-comparison" / "raw"
    res = asyncio.run(run_four_system_benchmark(dpath, out, sample_size=15))
    print("\n=== Four-System Benchmark Summary ===")
    print(json.dumps(res, indent=2))

