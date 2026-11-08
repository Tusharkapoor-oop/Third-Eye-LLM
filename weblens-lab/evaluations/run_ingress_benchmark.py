"""Measure the HTTP ingress stack: API-key auth, tenant binding, and limits.

This is an in-process ASGI benchmark. It measures the middleware that protects
the MCP endpoint, not search/extract work, MCP tool dispatch, or network time.
The output says so explicitly so a local number is never presented as an
end-to-end production result.

Example:
    python weblens-lab/evaluations/run_ingress_benchmark.py \
        --sustained-seconds 60 --burst-requests 10000 --concurrency 100
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
import time
from pathlib import Path

import httpx
from httpx import ASGITransport

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "weblens" / "src"))

from weblens.tenancy import ApiKeyRegistry  # noqa: E402

from weblens.cli import _ApiKeyAuth, _RateLimit, _SecurityHeaders  # noqa: E402


async def _ok_app(scope, receive, send):
    body = b'{"status":"ok"}'
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _summary(latencies_ms: list[float], wall_s: float) -> dict:
    return {
        "requests": len(latencies_ms),
        "wall_s": round(wall_s, 3),
        "throughput_rps": round(len(latencies_ms) / wall_s, 2) if wall_s > 0 else None,
        "throughput_qpm": round(60 * len(latencies_ms) / wall_s, 1) if wall_s > 0 else None,
        "p50_ms": round(_percentile(latencies_ms, 50), 3),
        "p95_ms": round(_percentile(latencies_ms, 95), 3),
        "p99_ms": round(_percentile(latencies_ms, 99), 3),
        "max_ms": round(max(latencies_ms), 3) if latencies_ms else 0.0,
    }


def _build_app(keys: dict[str, str], limit: int, tenant_limits: dict[str, int]):
    registry = ApiKeyRegistry(keys)
    rate = _RateLimit(_ok_app, limit=limit, window_s=60.0, tenant_limits=tenant_limits)
    auth = _ApiKeyAuth(rate, registry)
    return _SecurityHeaders(auth)


async def _one(client: httpx.AsyncClient, key: str) -> tuple[int, float]:
    started = time.perf_counter()
    response = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers={"authorization": f"Bearer {key}", "accept": "application/json"},
    )
    return response.status_code, (time.perf_counter() - started) * 1000.0


async def _burst(app, keys: dict[str, str], requests_n: int, concurrency: int) -> dict:
    latencies: list[float] = []
    statuses: dict[int, int] = {}
    semaphore = asyncio.Semaphore(max(1, concurrency))
    tenant_keys = list(keys.values())

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://bench") as client:

        async def bounded(index: int) -> None:
            async with semaphore:
                status, ms = await _one(client, tenant_keys[index % len(tenant_keys)])
                statuses[status] = statuses.get(status, 0) + 1
                latencies.append(ms)

        started = time.perf_counter()
        await asyncio.gather(*(bounded(i) for i in range(requests_n)))
        wall = time.perf_counter() - started

    return {
        "mode": "burst",
        "tenants": len(keys),
        "concurrency": concurrency,
        "statuses": {str(k): v for k, v in sorted(statuses.items())},
        **_summary(latencies, wall),
    }


async def _sustained(app, key: str, qpm: int, seconds: float) -> dict:
    interval = 60.0 / float(qpm)
    total = max(1, int(round(qpm * seconds / 60.0)))
    latencies: list[float] = []
    statuses: dict[int, int] = {}
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://bench") as client:
        started = time.perf_counter()
        for index in range(total):
            target = started + index * interval
            delay = target - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            status, ms = await _one(client, key)
            statuses[status] = statuses.get(status, 0) + 1
            latencies.append(ms)
        wall = time.perf_counter() - started
    return {
        "mode": "sustained",
        "target_qpm": qpm,
        "planned_seconds": seconds,
        "statuses": {str(k): v for k, v in sorted(statuses.items())},
        **_summary(latencies, wall),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark WebLens HTTP ingress middleware.")
    parser.add_argument("--sustained-seconds", type=float, default=60.0)
    parser.add_argument("--qpm", type=int, default=1000)
    parser.add_argument("--burst-requests", type=int, default=10_000)
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--tenants", type=int, default=10)
    args = parser.parse_args(argv)

    keys = {f"tenant-{i}": f"bench-key-{i:04d}-0123456789" for i in range(max(1, args.tenants))}
    per_tenant = {tenant: args.qpm for tenant in keys}
    app = _build_app(keys, args.qpm, per_tenant)
    one_key = next(iter(keys.values()))

    sustained = asyncio.run(_sustained(app, one_key, args.qpm, args.sustained_seconds))
    burst = asyncio.run(_burst(app, keys, args.burst_requests, args.concurrency))

    out = {
        "scope": "ingress-middleware-only",
        "caveat": (
            "In-process ASGI, synthetic handler. Excludes MCP tool dispatch, "
            "provider/network latency, and real HTTP transport."
        ),
        "environment": {
            "python": platform.python_version(),
            "platform": f"{platform.system()} {platform.release()}",
            "qpm_limit_per_tenant": args.qpm,
            "tenants": len(keys),
        },
        "sustained": sustained,
        "burst": burst,
        "gate": {
            "target_qpm": 1000,
            "target_p95_ms": 2000.0,
            "sustained_qpm_met": (sustained["throughput_qpm"] or 0) >= 1000,
            "sustained_p95_met": sustained["p95_ms"] < 2000.0,
            "note": "A local middleware pass is necessary but not sufficient for the production gate.",
        },
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
