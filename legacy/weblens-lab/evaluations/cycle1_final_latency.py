"""Cycle-1 final latency measurement for the pre-registered search gates.

Gates (evidence/prereg.md, fixed before any data was observed):
  p50 <= 1500 ms, p95 <= 5000 ms.

Runs the real WebLens search path against the live keyless provider chain.
Writes machine-readable output so the report generator can consume it; nothing
here is typed by hand.
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

from weblens.config import Settings  # noqa: E402
from weblens.service import WebLens  # noqa: E402

QUERIES = [
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
    "how does dns resolution work",
    "what is a memory leak",
    "jwt vs session cookies",
    "css grid vs flexbox",
    "python dataclass frozen",
    "docker multi stage build",
    "http2 vs http3",
    "sql window function over partition",
    "golang context cancellation",
    "terraform state locking",
    "opentelemetry trace propagation",
    "message queue dead letter",
    "cuda out of memory fix",
    "pytest fixture scope",
    "regex catastrophic backtracking",
    "cap theorem explained",
    "oauth2 authorization code flow",
    "kafka consumer group rebalance",
    "vector database hnsw index",
    "prompt injection mitigation",
    "bm25 vs tf idf",
    "rate limiting token bucket",
    "graphql n plus one problem",
    "linux file descriptor limit",
    "windows wsl2 networking",
    "browser cache control immutable",
    "webassembly performance",
    "microservices saga pattern",
]


async def main() -> int:
    # Pin the provider chain explicitly. A bare WebLens() inherits `.env`, and
    # with auto_include_tavily=True a present TAVILY_API_KEY silently prepends the
    # hosted provider -- which would quietly turn a "keyless" measurement into a
    # Tavily-backed one. This harness measures the keyless arm, so it must say so.
    settings = Settings(
        tavily_api_key=None,
        auto_include_tavily=False,
        search_providers="mwmbl,wikipedia,bing,yahoo",
        supplement_providers="",
    )
    svc = WebLens(settings)
    chain = svc.router.provider_names
    if "tavily" in chain:
        raise SystemExit(f"refusing to measure: keyless arm has Tavily in the chain ({chain})")
    order = list(QUERIES)
    random.Random(20261109).shuffle(order)

    latencies: list[float] = []
    token_counts: list[int] = []
    result_counts: list[int] = []
    statuses: dict[str, int] = {}

    for q in order:
        started = time.perf_counter()
        out = await svc.search(q, max_results=8)
        latencies.append((time.perf_counter() - started) * 1000.0)
        token_counts.append(int(out.get("tok") or 0))
        result_counts.append(int(out.get("n") or 0))
        status = str(out.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1

    ordered = sorted(latencies)

    def pct(p: float) -> float:
        idx = min(len(ordered) - 1, int(round(p * (len(ordered) - 1))))
        return ordered[idx]

    p50, p95 = pct(0.50), pct(0.95)
    summary = {
        "n": len(latencies),
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "mean_ms": round(statistics.mean(latencies), 1),
        "min_ms": round(ordered[0], 1),
        "max_ms": round(ordered[-1], 1),
        "mean_tokens": round(statistics.mean(token_counts), 1),
        "mean_results": round(statistics.mean(result_counts), 2),
        "provider_chain": chain,
        "zero_result_queries": sum(1 for n in result_counts if n == 0),
        "statuses": statuses,
        "gate_p50_1500ms": "PASS" if p50 <= 1500 else "FAIL",
        "gate_p95_5000ms": "PASS" if p95 <= 5000 else "FAIL",
    }

    out_dir = Path("../evidence/raw")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cycle1_final_latency.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0 if (p50 <= 1500 and p95 <= 5000) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
