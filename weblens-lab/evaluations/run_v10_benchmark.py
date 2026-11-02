"""V10 three-system benchmark runner.

Differences from the V9 runner (each fixes a measurement defect found during
repository reconnaissance):

1. System 1 talks to a real local MCP server process, not the in-process service.
2. A response with results is never miscounted as a failure just because one
   upstream provider degraded (``partial`` is reported separately from ``error``).
3. Quality uses graded relevance (domain match > fact match > irrelevant) and
   reports P@1/3/5, MRR, nDCG@5, Hit@5 and domain diversity, not P@5 alone.
4. Tokens are normalised with one tokenizer (cl100k_base) for all systems.
5. Every row carries provenance: dataset version, response hash, HTTP status,
   backend provider, raw engine status and cache state.
6. Runs are resumable and never overwrite earlier rows.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import random
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "weblens" / "src"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "weblens-lab"))

from adapters.deployed_adapter.adapter import DeployedWebLensAdapter
from adapters.local_mcp_adapter.adapter import LocalMCPAdapter
from adapters.provenance import canonical_hash
from adapters.tavily_adapter.adapter import TavilyAdapter
from weblens.tokens import count_tokens
from weblens.urls import registrable_domain

DEFAULT_DATASET = ROOT / "weblens-lab" / "datasets" / "eval_benchmark_suite_v10.json"
DEFAULT_OUT = ROOT / "reports" / "three-system-comparison-v10" / "raw"
SYSTEMS = ("local_weblens", "deployed_weblens", "tavily_direct")


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def grade_result(item: dict[str, Any], result: Any, acceptable: list[str]) -> int:
    url = _norm(getattr(result, "url", "") or "")
    text = _norm((getattr(result, "title", "") or "") + " " + (getattr(result, "content", "") or ""))
    host = registrable_domain(url) if url else ""
    if acceptable and any(acc.lower().lstrip("www.") in (host + url) for acc in acceptable):
        return 2
    keywords = [k.lower() for k in str(item.get("ground_truth_answer", "")).replace(",", " ").split() if len(k) > 2]
    if keywords:
        covered = sum(1 for k in keywords if k in text)
        if covered / len(keywords) >= 0.6:
            return 1
    return 0


def dcgs(grades: list[int], k: int = 5) -> tuple[float, float]:
    def dcg(gs: list[int]) -> float:
        return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(gs[:k]))

    actual = dcg(grades)
    ideal = dcg(sorted(grades, reverse=True))
    return actual, ideal


def bootstrap_ci(values: list[float], *, n_boot: int = 2000, seed: int = 7) -> tuple[float, float] | None:
    if len(values) < 3:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(len(values))] for _ in values]
        means.append(sum(sample) / len(sample))
    means.sort()
    return (round(means[int(0.025 * len(means))], 3), round(means[int(0.975 * len(means)) - 1], 3))


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def normalized_tokens(results: list[Any]) -> int:
    text = "\n".join(
        f"{getattr(r, 'title', '')}\n{getattr(r, 'content', '')}" for r in results
    )
    return count_tokens(text)


def search_metrics(item: dict[str, Any], results: list[Any]) -> dict[str, Any]:
    acceptable = item.get("acceptable_sources") or []
    unanswerable = bool(item.get("is_unanswerable"))
    grades = [grade_result(item, r, acceptable) for r in results]
    k = 5
    top = grades[:k]
    hits = [1 if g > 0 else 0 for g in top]

    precision = {f"p@{n}": (sum(hits[:n]) / n if n else 0.0) for n in (1, 3, 5)}
    first_rel = next((i + 1 for i, g in enumerate(grades) if g > 0), None)
    mrr = 1.0 / first_rel if first_rel else 0.0
    actual, ideal = dcgs(grades, k)
    ndcg = (actual / ideal) if ideal > 0 else 0.0
    domains = [registrable_domain(getattr(r, "url", "") or "") for r in results]
    domains = [d for d in domains if d]
    urls = [getattr(r, "url", "") for r in results]
    dup_rate = 0.0 if not urls else 1.0 - (len(set(urls)) / len(urls))

    return {
        "graded": not unanswerable and bool(acceptable),
        "relevant_count": sum(hits),
        "precision_at_1": round(precision["p@1"], 3),
        "precision_at_3": round(precision["p@3"], 3),
        "precision_at_5": round(precision["p@5"], 3),
        "mrr": round(mrr, 3),
        "ndcg_at_5": round(ndcg, 3),
        "hit_at_5": any(hits),
        "domain_diversity": round(len(set(domains)) / len(domains), 3) if domains else 0.0,
        "duplicate_rate": round(dup_rate, 3),
        "grades": grades,
    }


def summarize(records: list[dict[str, Any]], system: str) -> dict[str, Any]:
    rows = [r["systems"][system] for r in records]
    graded = [
        r["systems"][system]
        for r in records
        if r["systems"][system]["metrics"].get("graded")
    ]
    latencies = [r["latency_ms"] for r in rows if r["status"] != "error" and r["latency_ms"] > 0]
    ok = sum(1 for r in rows if r["status"] == "ok")
    partials = sum(1 for r in rows if r["status"] == "partial")
    empties = sum(1 for r in rows if r["status"] == "empty")
    errors = sum(1 for r in rows if r["status"] == "error")
    successes = ok + partials

    def mean(key: str, subset: list[dict[str, Any]] | None = None) -> float:
        src = subset if subset is not None else rows
        vals = [r["metrics"][key] for r in src if key in r["metrics"]]
        return round(statistics.fmean(vals), 3) if vals else 0.0

    ndcg_values = [r["metrics"]["ndcg_at_5"] for r in graded]
    p5_values = [r["metrics"]["precision_at_5"] for r in graded]
    tokens = [r["tokens"] for r in rows]
    return {
        "n": len(rows),
        "n_graded": len(graded),
        "status_counts": {
            "ok": ok,
            "partial": partials,
            "empty": empties,
            "error": errors,
        },
        "success_rate": round(successes / len(rows), 3) if rows else 0.0,
        "empty_rate": round(empties / len(rows), 3) if rows else 0.0,
        "error_rate": round(errors / len(rows), 3) if rows else 0.0,
        "quality": {
            "precision_at_1": mean("precision_at_1", graded),
            "precision_at_3": mean("precision_at_3", graded),
            "precision_at_5": mean("precision_at_5", graded),
            "mrr": mean("mrr", graded),
            "ndcg_at_5": mean("ndcg_at_5", graded),
            "hit_at_5": round(
                sum(1 for r in graded if r["metrics"]["hit_at_5"]) / len(graded), 3
            )
            if graded
            else 0.0,
            "domain_diversity": mean("domain_diversity"),
            "duplicate_rate": mean("duplicate_rate"),
            "p5_ci95": bootstrap_ci(p5_values),
            "ndcg_ci95": bootstrap_ci(ndcg_values),
        },
        "latency_ms": {
            "p50": round(percentile(latencies, 0.50), 1),
            "p90": round(percentile(latencies, 0.90), 1),
            "p95": round(percentile(latencies, 0.95), 1),
            "p99": round(percentile(latencies, 0.99), 1),
            "mean": round(statistics.fmean(latencies), 1) if latencies else 0.0,
            "min": round(min(latencies), 1) if latencies else 0.0,
            "max": round(max(latencies), 1) if latencies else 0.0,
            "ci95": bootstrap_ci(latencies),
        },
        "tokens": {
            "mean_normalized": round(statistics.fmean(tokens), 1) if tokens else 0.0,
            "mean_provider_reported": round(
                statistics.fmean([r["provider_tokens"] for r in rows]), 1
            )
            if rows
            else 0.0,
            "total_normalized": sum(tokens),
        },
        "credits": {
            "total": round(sum(r["credits"] for r in rows), 2),
            "mean": round(statistics.fmean([r["credits"] for r in rows]), 3) if rows else 0.0,
        },
        "error_samples": [
            {"id": rec["id"], "error": rec["systems"][system]["error"]}
            for rec in records
            if rec["systems"][system]["error"]
        ][:10],
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    dataset_path = Path(args.dataset)
    raw_dataset = dataset_path.read_bytes()
    dataset_sha = hashlib.sha256(raw_dataset).hexdigest()
    items: list[dict[str, Any]] = json.loads(raw_dataset)
    manifest = {}
    manifest_path = dataset_path.with_name("manifest_v10.json")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset_version = manifest.get("version", dataset_path.stem)

    if args.split:
        items = [i for i in items if i.get("split") == args.split]
    if args.limit:
        items = items[: args.limit]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id or f"v10_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6]}"
    raw_file = out_dir / f"run_{run_id}.jsonl"
    completed: set[str] = set()
    if args.resume and raw_file.exists():
        for line in raw_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    completed.add(json.loads(line)["id"])
                except (KeyError, json.JSONDecodeError):
                    continue
        print(f"resume: {len(completed)} rows already present in {raw_file.name}")

    local = LocalMCPAdapter()
    deployed = DeployedWebLensAdapter()
    tavily = TavilyAdapter()
    providers = {
        "local_weblens": local,
        "deployed_weblens": deployed,
        "tavily_direct": tavily,
    }

    print(f"run_id={run_id} dataset={dataset_version} items={len(items)}")
    print("starting local MCP server...")
    await local.start()
    local_meta = local.start_metadata()
    print(f"local MCP ready: {local_meta['endpoint']} tools={len(local_meta['tools'])}")

    deployed_meta: dict[str, Any] = {}
    try:
        await deployed.start()
        deployed_meta = deployed.start_metadata()
        print(f"deployed MCP ready: {deployed.endpoint_url} tools={len(deployed_meta['tools'])}")
    except Exception as exc:
        print(f"WARNING: deployed MCP initialization failed: {type(exc).__name__}: {exc}")

    order = list(range(len(items)))
    if not args.keep_order:
        random.Random(11).shuffle(order)

    records: list[dict[str, Any]] = []
    started_at = datetime.now(timezone.utc)
    try:
        for step, idx in enumerate(order, start=1):
            item = items[idx]
            if item["id"] in completed:
                continue
            query = item["query"]
            per_system: dict[str, Any] = {}
            rotation = step % 3
            names = list(SYSTEMS)
            names = names[rotation:] + names[:rotation]

            for name in names:
                provider = providers[name]
                t0 = time.perf_counter()
                try:
                    res = await provider.search(query, max_results=5)
                    wall_ms = (time.perf_counter() - t0) * 1000.0
                    metrics = search_metrics(item, res.results)
                    per_system[name] = {
                        "status": res.status,
                        "raw_status": res.raw_status,
                        "latency_ms": round(res.latency_ms, 1),
                        "wall_ms": round(wall_ms, 1),
                        "http_status": res.http_status,
                        "response_bytes": res.response_bytes,
                        "response_hash": res.response_hash,
                        "tokens": normalized_tokens(res.results),
                        "provider_tokens": res.tokens_returned,
                        "credits": res.credits_used,
                        "backend_provider": res.backend_provider,
                        "cache_state": res.cache_state,
                        "hit_count": len(res.results),
                        "error": res.error,
                        "metrics": metrics,
                    }
                except Exception as exc:
                    per_system[name] = {
                        "status": "error",
                        "raw_status": "adapter_exception",
                        "latency_ms": 0.0,
                        "wall_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                        "http_status": None,
                        "response_bytes": None,
                        "response_hash": None,
                        "tokens": 0,
                        "provider_tokens": 0,
                        "credits": 0.0,
                        "backend_provider": None,
                        "cache_state": "unknown",
                        "hit_count": 0,
                        "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                        "metrics": {},
                    }
                await asyncio.sleep(args.throttle_s)

            record = {
                "experiment_id": run_id,
                "dataset_version": dataset_version,
                "dataset_sha256": dataset_sha,
                "id": item["id"],
                "category": item.get("category"),
                "difficulty": item.get("difficulty"),
                "split": item.get("split"),
                "unanswerable": bool(item.get("is_unanswerable")),
                "query": query,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "systems": per_system,
            }
            records.append(record)
            with open(raw_file, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

            if step % 10 == 0 or step == len(order):
                print(
                    f"[{step}/{len(order)}] {item['id']} "
                    + " | ".join(
                        f"{n.split('_')[0]}={per_system[n]['status']}/{per_system[n]['latency_ms']}ms"
                        for n in SYSTEMS
                    )
                )
    finally:
        await local.close()
        await deployed.close()
        await tavily.close()

    # Merge rows already on disk (resume) before summarising.
    all_records: list[dict[str, Any]] = []
    if raw_file.exists():
        for line in raw_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                all_records.append(json.loads(line))

    summary = {
        "run_id": run_id,
        "status": "ok",
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": dataset_version,
        "dataset_path": str(dataset_path.relative_to(ROOT)) if dataset_path.is_relative_to(ROOT) else str(dataset_path),
        "dataset_sha256": dataset_sha,
        "total_queries_evaluated": len({r["id"] for r in all_records}),
        "completed_this_run": len(records),
        "request_budget": {name: len(records) for name in SYSTEMS},
        "environment": {
            "host": platform.node(),
            "platform": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "git_commit": _git_commit(),
            "cwd": str(ROOT),
        },
        "providers": {
            "local_weblens": local_meta,
            "deployed_weblens": deployed_meta,
            "tavily_direct": {
                "endpoint": TavilyAdapter.BASE_URL,
                "auth": "Bearer header",
                "search_depth": "basic",
                "credits_model": "1 credit per basic search (provider-reported usage)",
            },
        },
        "systems": {name: summarize(all_records, name) for name in SYSTEMS},
        "paired_differences": paired_differences(all_records),
        "resource_usage": {
            "local_mcp_process": local.resource_usage,
            "deployed_container": "not observable from client (Cloud Run)",
        },
    }
    summary_file = out_dir / f"summary_{run_id}.json"
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    latest = out_dir / "summary_latest.json"
    latest.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nsummary -> {summary_file}")
    return summary


def paired_differences(records: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for a, b in (
        ("local_weblens", "tavily_direct"),
        ("deployed_weblens", "tavily_direct"),
        ("local_weblens", "deployed_weblens"),
    ):
        diffs = [r["systems"][a]["metrics"].get("precision_at_5", 0) - r["systems"][b]["metrics"].get("precision_at_5", 0) for r in records]
        lat = [r["systems"][a]["latency_ms"] - r["systems"][b]["latency_ms"] for r in records if r["systems"][a]["status"] != "error" and r["systems"][b]["status"] != "error"]
        out[f"{a}_minus_{b}"] = {
            "n": len(diffs),
            "precision_at_5_mean_delta": round(statistics.fmean(diffs), 3) if diffs else 0.0,
            "precision_at_5_delta_ci95": bootstrap_ci(diffs),
            "latency_mean_delta_ms": round(statistics.fmean(lat), 1) if lat else 0.0,
        }
    return out


def _git_commit() -> str:
    try:
        import subprocess

        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=5
        ).strip()
    except Exception:
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--split", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--keep-order", action="store_true")
    parser.add_argument("--throttle-s", type=float, default=0.25)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    summary = asyncio.run(run(args))
    print(json.dumps(summary["systems"], indent=2)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
