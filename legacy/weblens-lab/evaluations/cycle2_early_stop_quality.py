"""Paired quality test for the shipped quality-guarded fuse early stop.

Compares, interleaved on identical queries:
  A = fuse_soft_timeout_s=0     (wait for every provider; previous behaviour)
  B = product default           (soft deadline + depth/domain guard)

The guard differs from the rejected candidate in cycle 1: it only stops early
when the accepted pool already holds k + fuse_early_min_extra distinct URLs
across at least fuse_early_min_domains registrable domains. This measures
whether that guard is sufficient.
"""

from __future__ import annotations

import asyncio
import json
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")

LAB = Path(__file__).resolve().parents[2] / "weblens-lab" / "evaluations"
sys.path.insert(0, str(LAB))

import run_weblens_vs_tavily_v11 as bench  # noqa: E402

from weblens.config import Settings  # noqa: E402
from weblens.service import WebLens  # noqa: E402


async def _one(svc: WebLens, query: str) -> tuple[list[str], float, bool]:
    started = time.perf_counter()
    out = await svc.search(query, max_results=5)
    elapsed = (time.perf_counter() - started) * 1000.0
    urls = [str(r.get("u") or r.get("url") or "") for r in (out.get("res") or [])]
    early = any(str(w).startswith("early_stop:") for w in (out.get("warn") or []))
    return urls, elapsed, early


def _ci(values: list[float], iterations: int = 10000, seed: int = 12345):
    rng = random.Random(seed)
    n = len(values)
    means = sorted(
        statistics.mean([values[rng.randrange(n)] for _ in range(n)]) for _ in range(iterations)
    )
    return means[int(0.025 * iterations)], means[int(0.975 * iterations)]


async def main() -> int:
    queries = bench.select_queries(40, "development")
    if not queries:
        raise SystemExit("no queries")

    base = dict(
        cache_enabled=False,
        allow_browser=False,
        tavily_api_key=None,
        use_official_source_hints=False,
        search_providers="mwmbl,wikipedia,bing,yahoo",
        supplement_providers="",
    )
    svc_a = WebLens(Settings(**base, fuse_soft_timeout_s=0.0))
    svc_b = WebLens(Settings(**base))  # product default soft deadline

    dp5: list[float] = []
    dnd: list[float] = []
    dms: list[float] = []
    early_count = 0

    for rep in range(2):
        order = list(queries)
        random.Random(200 + rep).shuffle(order)
        for item in order:
            q = str(item["query"])
            labels = [str(x) for x in (item.get("acceptable_sources") or [])]

            urls_a, ms_a, _ = await _one(svc_a, q)
            urls_b, ms_b, early = await _one(svc_b, q)
            early_count += int(early)

            dp5.append(bench.precision_at_k(urls_b, labels, 5) - bench.precision_at_k(urls_a, labels, 5))
            dnd.append(bench.ndcg_at_k(urls_b, labels, 5) - bench.ndcg_at_k(urls_a, labels, 5))
            dms.append(ms_b - ms_a)

    await svc_a.close()
    await svc_b.close()

    lo_p5, hi_p5 = _ci(dp5)
    lo_nd, hi_nd = _ci(dnd)
    lo_ms, hi_ms = _ci(dms)

    summary = {
        "n_pairs": len(dp5),
        "early_stop_fired": early_count,
        "p5_diff_mean": round(statistics.mean(dp5), 4),
        "p5_diff_ci95": [round(lo_p5, 4), round(hi_p5, 4)],
        "ndcg_diff_mean": round(statistics.mean(dnd), 4),
        "ndcg_diff_ci95": [round(lo_nd, 4), round(hi_nd, 4)],
        "ms_diff_mean": round(statistics.mean(dms), 1),
        "ms_diff_ci95": [round(lo_ms, 1), round(hi_ms, 1)],
        "quality_guard": "HELD" if lo_p5 >= -0.02 else "VIOLATED",
    }
    out = Path("../evidence/raw")
    out.mkdir(parents=True, exist_ok=True)
    (out / "cycle2_early_stop_quality.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
