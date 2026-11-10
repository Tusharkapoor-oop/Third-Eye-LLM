"""Paired relevance test: gather-all fuse vs bounded (early-stop) fuse.

The unpaired comparison was confounded by search-index drift (the same code
scored P@5 0.575, 0.500 and 0.485 on three consecutive runs of one split). This
script removes that by interleaving both variants on the *same* query, back to
back, and scoring relevance per item, so drift hits both arms equally.

Decision rule (evidence/prereg.md, quality-first): a latency win counts only if
quality is non-inferior — the paired P@5 difference lower CI bound must be no
worse than -0.02.
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

from weblens.service import WebLens  # noqa: E402

LAB = Path(__file__).resolve().parents[2] / "weblens-lab" / "evaluations"
sys.path.insert(0, str(LAB))

import run_weblens_vs_tavily_v11 as bench  # noqa: E402


async def _one(svc: WebLens, query: str) -> tuple[list[str], float]:
    started = time.perf_counter()
    out = await svc.search(query, max_results=5)
    elapsed = (time.perf_counter() - started) * 1000.0
    urls = [str(r.get("u") or r.get("url") or "") for r in (out.get("res") or [])]
    return urls, elapsed


def _bootstrap_ci(values: list[float], iterations: int = 10000, seed: int = 12345):
    rng = random.Random(seed)
    means = []
    n = len(values)
    for _ in range(iterations):
        means.append(statistics.mean([values[rng.randrange(n)] for _ in range(n)]))
    means.sort()
    return means[int(0.025 * iterations)], means[int(0.975 * iterations)]


async def main() -> int:
    queries = bench.select_queries(40, "development")
    if not queries:
        raise SystemExit("no queries")

    svc = WebLens()
    old_fuse = None

    # Capture the shipped (gather-all) implementation, then build the bounded one.
    import weblens.search.router as R

    shipped = R.SearchRouter._fuse

    async def bounded_fuse(self, q, *, k, freshness, domains, exclude_domains, outcome, accept, providers):
        async def one(p):
            name = getattr(p, "name", "?")
            try:
                raw = await asyncio.wait_for(
                    p.search(q, k=max(k, 8), freshness=freshness, domains=domains, exclude_domains=exclude_domains),
                    timeout=self._provider_timeout(p),
                )
                return name, accept(raw), None
            except Exception as e:  # noqa: BLE001
                return name, [], e

        tasks = {asyncio.create_task(one(p)): getattr(p, "name", "?") for p in providers}
        pending = set(tasks)
        results = []
        seen: set[str] = set()
        try:
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for t in done:
                    res = t.result()
                    results.append(res)
                    for h in res[1]:
                        seen.add(h.url)
                if len(seen) >= k:
                    break
        finally:
            for t in pending:
                t.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        merged = []
        for name, hits, err in results:
            if err is None:
                self._mark_success(name)
                outcome.providers.append(name)
                merged.extend(hits)
            else:
                self._mark_failure(name)
                outcome.failures[name] = "timeout" if isinstance(err, TimeoutError) else type(err).__name__
        return merged

    del old_fuse

    d_p5: list[float] = []
    d_ndcg: list[float] = []
    d_ms: list[float] = []
    detail = []

    for rep in range(2):
        order = list(queries)
        random.Random(100 + rep).shuffle(order)
        for item in order:
            q = str(item["query"])
            labels = [str(x) for x in (item.get("acceptable_sources") or [])]

            R.SearchRouter._fuse = shipped
            urls_a, ms_a = await _one(svc, q)
            R.SearchRouter._fuse = bounded_fuse
            urls_b, ms_b = await _one(svc, q)

            p5_a = bench.precision_at_k(urls_a, labels, 5)
            p5_b = bench.precision_at_k(urls_b, labels, 5)
            nd_a = bench.ndcg_at_k(urls_a, labels, 5)
            nd_b = bench.ndcg_at_k(urls_b, labels, 5)

            d_p5.append(p5_b - p5_a)
            d_ndcg.append(nd_b - nd_a)
            d_ms.append(ms_b - ms_a)
            detail.append(
                {"q": q, "p5_shipped": p5_a, "p5_bounded": p5_b, "ms_shipped": ms_a, "ms_bounded": ms_b}
            )

    R.SearchRouter._fuse = shipped
    await svc.close()

    lo_p5, hi_p5 = _bootstrap_ci(d_p5)
    lo_nd, hi_nd = _bootstrap_ci(d_ndcg)
    lo_ms, hi_ms = _bootstrap_ci(d_ms)

    summary = {
        "n_pairs": len(d_p5),
        "p5_diff_mean": round(statistics.mean(d_p5), 4),
        "p5_diff_ci95": [round(lo_p5, 4), round(hi_p5, 4)],
        "ndcg_diff_mean": round(statistics.mean(d_ndcg), 4),
        "ndcg_diff_ci95": [round(lo_nd, 4), round(hi_nd, 4)],
        "ms_diff_mean": round(statistics.mean(d_ms), 1),
        "ms_diff_ci95": [round(lo_ms, 1), round(hi_ms, 1)],
        "quality_guard": "HELD" if lo_p5 >= -0.02 else "VIOLATED",
    }
    out = Path("../evidence/raw")
    out.mkdir(parents=True, exist_ok=True)
    (out / "cycle1_paired_fuse_quality.json").write_text(
        json.dumps({"summary": summary, "detail": detail}, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
