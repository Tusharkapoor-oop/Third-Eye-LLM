#!/usr/bin/env python3
"""tools/calibrate_noise_floor.py

WebLens v8/v9 Part D2: A/A calibration measuring the machine-specific noise floor
for p50 and p95 latencies under randomized interleaved execution.
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from reranker import StructureAwareChunker, TwoStageReranker


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


if __name__ == "__main__":
    res = run_aa_calibration()
    print("A/A Noise Floor Calibration Result:")
    print(json.dumps(res, indent=2))
