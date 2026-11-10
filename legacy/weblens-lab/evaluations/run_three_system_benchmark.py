"""Three-System Competitive Benchmark Runner: Local WebLens vs Deployed WebLens vs Tavily Direct.

Evaluates:
- System 1: Local WebLens MCP (independent keyless)
- System 2: Deployed WebLens MCP (Google Cloud Run)
- System 3: Tavily Direct API (official key-backed REST API)

Measures:
- Latency (p50, p90, p95, mean)
- Precision@5 (density of authoritative sources)
- Answer support (factual claim grounding)
- False confidence (hallucination on unanswerable queries)
- Token efficiency (tokens per response)
- Cost (credits and estimated USD)
- Success rate (uptime and reliability)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
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
from adapters.tavily_adapter.adapter import TavilyAdapter
from adapters.weblens_adapter.adapter import WebLensAdapter
from weblens.config import Settings
from weblens.urls import registrable_domain


# PREREG-V10-001 (2026-11-02): corrected evaluation scorer.
# - Short/symbolic ground-truth tokens (<=3 chars) match with non-alphanumeric
#   boundaries (e.g. "405", "H2O", "Au", "@>"); long tokens remain substring matches.
# - "NOT MEASURED -" ground truths are dynamic facts: token verification is skipped
#   and support is granted iff a top-5 result comes from acceptable_sources.
# Applied identically to all systems. See evidence/prereg-v10-001-scoring-fix.md.
_DYNAMIC_GT_PREFIX = "not measured"
_BOUNDARY_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _ground_truth_matches(text_lower: str, gt_tokens: list[str]) -> bool:
    if not gt_tokens:
        return False
    for tok in gt_tokens:
        if len(tok) > 3:
            if tok in text_lower:
                return True
        else:
            pattern = _BOUNDARY_RE_CACHE.get(tok)
            if pattern is None:
                pattern = re.compile(r"(?<![a-z0-9])" + re.escape(tok) + r"(?![a-z0-9])")
                _BOUNDARY_RE_CACHE[tok] = pattern
            if pattern.search(text_lower):
                return True
    return False


def evaluate_precision(results: list[Any], item: dict[str, Any]) -> tuple[float, bool]:
    if not results:
        return 0.0, False

    acceptable = [dom.lower() for dom in item.get("acceptable_sources", [])]
    gt_raw = str(item.get("ground_truth_answer", ""))
    is_dynamic = gt_raw.strip().lower().startswith(_DYNAMIC_GT_PREFIX)
    gt_answer = "" if is_dynamic else gt_raw.lower()
    gt_tokens = gt_answer.split() if gt_answer else []

    relevant_count = 0
    answer_supported = False

    for r in results[:5]:
        content = getattr(r, "content", "") or ""
        title = getattr(r, "title", "") or ""
        text = (content + " " + title).lower()
        url = (getattr(r, "url", "") or "").lower()
        dom = registrable_domain(url).lower() if url else ""

        is_acceptable = any(acc in dom or acc in url for acc in acceptable) if acceptable else False
        if is_dynamic:
            has_content = is_acceptable
        else:
            has_content = _ground_truth_matches(text, gt_tokens)

        if is_acceptable or has_content:
            relevant_count += 1
            if has_content:
                answer_supported = True

    precision = round(relevant_count / min(len(results), 5), 3) if results else 0.0
    return precision, answer_supported


async def run_three_system_benchmark(
    dataset_path: Path,
    output_dir: Path,
    *,
    sample_size: int | None = None,
    include_tavily: bool = True,
    include_deployed: bool = True,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_file = output_dir / "three_system_results.jsonl"

    with open(dataset_path, "r", encoding="utf-8") as f:
        all_items: list[dict[str, Any]] = json.load(f)

    if sample_size and sample_size < len(all_items):
        eval_items = all_items[:sample_size]
    else:
        eval_items = all_items

    settings = Settings()
    # CYCLE-1 (v10, 2026-11-02): single-variable change — add keyless Bing (best-effort
    # HTML adapter, no API key) as FIRST provider of the independent chain.
    # Baseline chain for reference: "ddg,mwmbl,wikipedia"
    settings.search_providers = "bing,ddg,mwmbl,wikipedia"
    settings.tavily_api_key = None

    sys1_local = WebLensAdapter(settings=settings, independent=True)
    sys2_deployed = DeployedWebLensAdapter() if include_deployed else None
    sys3_tavily = TavilyAdapter() if include_tavily else None

    records: list[dict[str, Any]] = []
    print(f"Starting Three-System Benchmark on {len(eval_items)} queries...")
    print(f"System 1: Local WebLens MCP")
    print(f"System 2: Deployed WebLens MCP ({sys2_deployed.endpoint_url})")
    print(f"System 3: Tavily Direct API")

    try:
        for idx, item in enumerate(eval_items):
            qid = item["id"]
            query = item["query"]
            category = item.get("category", "general")
            unanswerable = item.get("is_unanswerable", False)

            # Rotate execution order to avoid network bias
            perm = idx % 3
            if perm == 0:
                systems_order = [("sys1_local", sys1_local), ("sys2_deployed", sys2_deployed), ("sys3_tavily", sys3_tavily)]
            elif perm == 1:
                systems_order = [("sys2_deployed", sys2_deployed), ("sys3_tavily", sys3_tavily), ("sys1_local", sys1_local)]
            else:
                systems_order = [("sys3_tavily", sys3_tavily), ("sys1_local", sys1_local), ("sys2_deployed", sys2_deployed)]
            if sys3_tavily is None:
                systems_order = [(n, p) for n, p in systems_order if p is not None]
            if sys2_deployed is None:
                systems_order = [("sys1_local", sys1_local)]

            results_by_sys: dict[str, Any] = {}

            for sys_name, provider in systems_order:
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
                await asyncio.sleep(0.3)  # politeness throttle

            record = {
                "id": qid,
                "category": category,
                "query": query,
                "unanswerable": unanswerable,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "local_weblens": results_by_sys["sys1_local"],
                "deployed_weblens": results_by_sys.get("sys2_deployed"),
                "tavily_direct": results_by_sys.get("sys3_tavily"),
            }
            records.append(record)

            with open(raw_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")

            print(f"[{idx+1}/{len(eval_items)}] {qid} ({category}): "
                  f"L={results_by_sys['sys1_local']['latency_ms']}ms | "
                  f"D={results_by_sys['sys2_deployed']['latency_ms']}ms | "
                  f"T={results_by_sys['sys3_tavily']['latency_ms']}ms")

    finally:
        await sys1_local.close()
        if sys2_deployed is not None:
            await sys2_deployed.close()

    # Aggregate Metrics
    n = len(records)
    if n == 0:
        return {"status": "error", "msg": "No records produced"}

    def calc_stats(sys_key: str) -> dict[str, Any]:
        rows = [r[sys_key] for r in records if isinstance(r.get(sys_key), dict)]
        if not rows:
            return {"status": "not_measured", "latency": {}, "quality": {}, "tokens_and_cost": {}}
        n_rows = len(rows)
        lats = sorted([row["latency_ms"] for row in rows if row["latency_ms"] > 0])
        p50 = lats[len(lats) // 2] if lats else 0.0
        p90 = lats[int(len(lats) * 0.9)] if lats else 0.0
        p95 = lats[int(len(lats) * 0.95)] if lats else 0.0
        mean_lat = round(sum(lats) / len(lats), 1) if lats else 0.0

        precisions = [row["precision_at_5"] for row in rows]
        mean_prec = round(sum(precisions) / n_rows, 3)

        supp_count = sum(1 for row in rows if row["answer_supported"])
        supp_rate = round(supp_count / n_rows, 3)

        false_conf_count = sum(1 for row in rows if row["false_confidence"])
        success_count = sum(1 for row in rows if row["status"] == "ok")

        mean_tokens = round(sum(row["tokens"] for row in rows) / n_rows, 1)
        total_credits = sum(row["credits_used"] for row in rows)

        return {
            "latency": {
                "p50_ms": p50,
                "p90_ms": p90,
                "p95_ms": p95,
                "mean_ms": mean_lat,
            },
            "quality": {
                "mean_precision_at_5": mean_prec,
                "answer_supported_rate": supp_rate,
                "answer_supported_count": supp_count,
                "false_confidence_count": false_conf_count,
                "success_rate": round(success_count / n_rows, 3),
            },
            "tokens_and_cost": {
                "mean_tokens": mean_tokens,
                "total_credits": total_credits,
                "estimated_cost_usd": round(total_credits * 0.005, 4),
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
        },
    }

    summary_file = output_dir / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    dpath = ROOT / "weblens-lab" / "datasets" / "eval_benchmark_suite.json"
    out = ROOT / "reports" / "three-system-comparison" / "raw"
    summary = asyncio.run(run_three_system_benchmark(dpath, out, sample_size=15))
    print("\n=== Three-System Benchmark Summary ===")
    print(json.dumps(summary, indent=2))

