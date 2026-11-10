#!/usr/bin/env python3
"""tools/calibrate_noise_floor.py

WebLens v8/v9 Part D2: A/A calibration measuring the machine-specific noise floor
for p50 and p95 latencies under randomized interleaved execution.

Two paths can be calibrated, because a noise floor is only meaningful for the
path the claim is about:

  --path chunk   (default) local chunker + BM25 scoring; sub-millisecond, so its
                 noise floor says nothing about a network-backed search claim.
  --path search  the real WebLens search path against live providers. Use this
                 one to bound any search-latency delta; it is network-bound and
                 its noise floor is tens to hundreds of milliseconds.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from reranker import StructureAwareChunker, TwoStageReranker

SEARCH_QUERIES = [
    "python asyncio tutorial",
    "kubernetes ingress tls",
    "sqlite fts5 bm25",
    "react server components",
    "postgres vacuum full",
    "rust ownership borrow checker",
    "pandas groupby agg",
    "docker compose healthcheck",
    "numpy broadcasting rules",
    "git rebase vs merge",
    "typescript generics constraints",
    "redis persistence aof rdb",
]


def generate_benchmark_document() -> str:
    sections = []
    for i in range(15):
        para = f"## Section {i}: Architecture and Performance Details\n\n"
        para += f"Paragraph {i}.1 provides essential system context for information retrieval. " * 5 + "\n\n"
        para += f"```python\ndef handler_{i}(x: int) -> int:\n    return x * {i} + 42\n```\n\n"
        para += "| Metric | Target | Actual |\n| :--- | :--- | :--- |\n| Latency | <10ms | 4.2ms |\n| Tokens | <500 | 382 |\n\n"
        sections.append(para)
    return "\n".join(sections)


def run_aa_calibration(n_trials: int = 40) -> dict:
    doc = generate_benchmark_document()
    chunker = StructureAwareChunker(target_chars=500)
    reranker = TwoStageReranker()
    query = "latency target performance details"

    # Pre-warm
    chunks = chunker.chunk_document(doc)
    _ = reranker._score_bm25_fast(query, chunks)

    # Interleaved trials
    trials = [("A1", i) for i in range(n_trials)] + [("A2", i) for i in range(n_trials)]
    random.seed(42)
    random.shuffle(trials)

    latencies_a1 = []
    latencies_a2 = []

    for arm, _idx in trials:
        t0 = time.perf_counter()
        ch = chunker.chunk_document(doc)
        _ = reranker._score_bm25_fast(query, ch)
        dur_ms = (time.perf_counter() - t0) * 1000.0

        if arm == "A1":
            latencies_a1.append(dur_ms)
        else:
            latencies_a2.append(dur_ms)

    a1_p50 = float(np.percentile(latencies_a1, 50))
    a1_p95 = float(np.percentile(latencies_a1, 95))
    a2_p50 = float(np.percentile(latencies_a2, 50))
    a2_p95 = float(np.percentile(latencies_a2, 95))

    p50_noise = abs(a1_p50 - a2_p50)
    p95_noise = abs(a1_p95 - a2_p95)

    result = {
        "n_trials_per_arm": n_trials,
        "a1_p50_ms": round(a1_p50, 3),
        "a1_p95_ms": round(a1_p95, 3),
        "a2_p50_ms": round(a2_p50, 3),
        "a2_p95_ms": round(a2_p95, 3),
        "p50_noise_floor_ms": round(p50_noise, 3),
        "p95_noise_floor_ms": round(p95_noise, 3),
        "relative_p50_noise_pct": round((p50_noise / max(a1_p50, 0.001)) * 100.0, 2),
        "relative_p95_noise_pct": round((p95_noise / max(a1_p95, 0.001)) * 100.0, 2),
        "calibrated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    out_path = Path("evidence/loop/NOISE_FLOOR.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    return result


def run_search_aa_calibration(repeats: int = 3) -> dict:
    """A/A on the real search path: the same code measured against itself.

    Each query is run twice back to back. Because both arms are the *same*
    implementation, any difference between them is noise: provider jitter,
    connection setup and search-index drift during the run.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "weblens" / "src"))
    from weblens.service import WebLens  # noqa: PLC0415 - optional heavy import

    async def _measure() -> list[float]:
        svc = WebLens()
        diffs: list[float] = []
        try:
            for rep in range(repeats):
                order = list(SEARCH_QUERIES)
                random.Random(rep).shuffle(order)
                for query in order:
                    started = time.perf_counter()
                    await svc.search(query, max_results=8)
                    arm_a = (time.perf_counter() - started) * 1000.0
                    started = time.perf_counter()
                    await svc.search(query, max_results=8)
                    arm_b = (time.perf_counter() - started) * 1000.0
                    diffs.append(arm_b - arm_a)
        finally:
            await svc.close()
        return diffs

    diffs = asyncio.run(_measure())
    ordered = sorted(diffs)
    n = len(ordered)
    mean_diff = statistics.mean(diffs)
    sd = statistics.pstdev(diffs)
    median_diff = statistics.median(diffs)
    p95_diff = ordered[min(n - 1, int(0.95 * (n - 1)))]
    result = {
        "path": "search",
        "n_pairs": n,
        "mean_paired_diff_ms": round(mean_diff, 1),
        "sd_ms": round(sd, 1),
        "median_paired_diff_ms": round(median_diff, 1),
        "p95_paired_diff_ms": round(p95_diff, 1),
        "p50_noise_floor_ms": round(abs(median_diff), 1),
        "calibrated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    out_path = Path("evidence/loop/NOISE_FLOOR_SEARCH.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="A/A noise floor calibration")
    ap.add_argument(
        "--path",
        choices=("chunk", "search"),
        default="chunk",
        help="chunk = local chunker/BM25 (default); search = live WebLens search path",
    )
    ns = ap.parse_args()
    if ns.path == "search":
        print("A/A Noise Floor Calibration Result (search path):")
        print(json.dumps(run_search_aa_calibration(), indent=2))
    else:
        print("A/A Noise Floor Calibration Result (chunker path):")
        print(json.dumps(run_aa_calibration(), indent=2))
