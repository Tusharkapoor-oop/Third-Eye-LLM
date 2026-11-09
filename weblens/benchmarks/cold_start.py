# ruff: noqa: ASYNC240, T201
"""Cold-start and cache-hit measurements.

This separates costs that a single search-latency number hides:

* process + import cost (fresh interpreter)
* service/socket setup
* first tokenizer load (tiktoken BPE file)
* MCP schema construction
* a single network search (search results are not cached)
* network extract vs. HTTP-cache hit

Run from the repository root:

    uv run python -m benchmarks.cold_start

The numbers are machine-specific. The JSON file records the environment and
every raw sample so the table can be recomputed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import shutil
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weblens.config import Settings
from weblens.service import WebLens
from weblens.tokens import TOKENIZER_NAME

ROOT = Path(__file__).resolve().parents[1]


def _subprocess_ms(code: str, runs: int) -> list[float]:
    samples: list[float] = []
    for _ in range(runs):
        proc = subprocess.run(  # noqa: S603 - fixed interpreter and literal code
            [sys.executable, "-c", code],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        samples.append(float(proc.stdout.strip().splitlines()[-1]))
    return samples


INIT_CODE = """
import asyncio, time

async def main():
    t = time.perf_counter()
    from weblens.service import WebLens
    from weblens.mcp_server import build_server
    service = WebLens()
    server = build_server(service)
    await server.list_tools()
    elapsed = (time.perf_counter() - t) * 1000
    print(elapsed)
    await service.close()

asyncio.run(main())
"""

IMPORT_CODE = """
import time
t = time.perf_counter()
import weblens.service  # noqa: F401
print((time.perf_counter() - t) * 1000)
"""

TOKEN_CODE = """
import time
from weblens.tokens import count_tokens
t = time.perf_counter()
count_tokens("hello world")
print((time.perf_counter() - t) * 1000)
"""


def _ms(values: list[float]) -> dict[str, float]:
    return {
        "median": round(statistics.median(values), 1),
        "min": round(min(values), 1),
        "max": round(max(values), 1),
        "samples": [round(v, 1) for v in values],
    }


async def warm_cache_measurements(cache_dir: Path) -> dict[str, Any]:
    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)
    settings = Settings(
        cache_dir=cache_dir,
        cache_enabled=True,
        allow_browser=False,
        search_providers="wikipedia",
    )
    settings.ensure_dirs()
    service = WebLens(settings)
    out: dict[str, Any] = {}
    try:
        query = "Python (programming language)"
        t = time.perf_counter()
        first = await service.search(query, max_results=3)
        out["search_network_ms"] = round((time.perf_counter() - t) * 1000, 1)
        out["search_network_status"] = first.get("status")
        out["search_network_providers"] = first.get("prov")
        out["search_network_failures"] = first.get("fail")
        out["search_network_warnings"] = first.get("warn")

        # Search envelopes are not cached, but provider HTTP responses are
        # cached by SafeFetcher. The first repeat is cold; later repeats read
        # the provider response through the HTTP cache.
        repeat: list[float] = []
        for _ in range(3):
            t = time.perf_counter()
            again = await service.search(query, max_results=3)
            repeat.append((time.perf_counter() - t) * 1000)
        out["repeat_search_ms"] = _ms(repeat)
        out["repeat_search_status"] = again.get("status")

        url = "https://example.com/"
        t = time.perf_counter()
        first_extract = await service.extract(url, max_tokens=500)
        out["extract_network_ms"] = round((time.perf_counter() - t) * 1000, 1)
        out["extract_network_status"] = first_extract.get("status")

        warm_extract: list[float] = []
        for _ in range(3):
            t = time.perf_counter()
            again_extract = await service.extract(url, max_tokens=500)
            warm_extract.append((time.perf_counter() - t) * 1000)
        out["extract_cache_ms"] = _ms(warm_extract)
        out["extract_cache_status"] = again_extract.get("status")
    finally:
        await service.close()
    return out


async def main_async(args: argparse.Namespace) -> int:
    import_samples = _subprocess_ms(IMPORT_CODE, args.runs)
    init_samples = _subprocess_ms(INIT_CODE, args.runs)
    token_samples = _subprocess_ms(TOKEN_CODE, args.runs)

    cache = await warm_cache_measurements(Path(args.cache_dir))
    result = {
        "measured_at": datetime.now(UTC).isoformat(),
        "tokenizer": TOKENIZER_NAME,
        "environment": {
            "python": platform.python_version(),
            "platform": f"{platform.system()} {platform.release()}",
            "processor": platform.processor(),
        },
        "method": {
            "process_runs": args.runs,
            "cache_dir": args.cache_dir,
            "notes": (
                "Fresh interpreter per sample; OS file cache is warm. The network search "
                "uses Wikipedia only for a stable single-provider sample. Search envelopes "
                "are not cached; repeated searches still use the HTTP response cache."
            ),
        },
        "import_module_ms": _ms(import_samples),
        "service_and_mcp_ready_ms": _ms(init_samples),
        "first_token_count_ms": _ms(token_samples),
        "cache": cache,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "# WebLens cold start and cache",
        "",
        f"- measured: {result['measured_at']}",
        f"- Python: {result['environment']['python']} on {result['environment']['platform']}",
        f"- samples per subprocess metric: {args.runs}",
        "",
        "| metric | median | min | max |",
        "| --- | --- | --- | --- |",
    ]
    for label, key in (
        ("import `weblens.service`", "import_module_ms"),
        ("service + MCP server ready", "service_and_mcp_ready_ms"),
        ("first `count_tokens` (tiktoken load)", "first_token_count_ms"),
    ):
        m = result[key]
        lines.append(f"| {label} | {m['median']} ms | {m['min']} ms | {m['max']} ms |")
    c = result["cache"]
    lines += [
        f"| search, network (Wikipedia, single sample) | {c['search_network_ms']} ms | | |",
        f"| search, repeated (HTTP cache path, 3 samples) | {c['repeat_search_ms']['median']} ms | "
        f"{c['repeat_search_ms']['min']} ms | {c['repeat_search_ms']['max']} ms |",
        f"| extract, network (single sample) | {c['extract_network_ms']} ms | | |",
        f"| extract, HTTP cache + reparse | {c['extract_cache_ms']['median']} ms | "
        f"{c['extract_cache_ms']['min']} ms | {c['extract_cache_ms']['max']} ms |",
        "",
        f"Search status: `{c['search_network_status']}`; extract status: "
        f"`{c['extract_network_status']}`; extract cache status: "
        f"`{c['extract_cache_status']}`.",
        f"Search provider failures: `{json.dumps(c.get('search_network_failures') or {})}`; "
        f"warnings: `{json.dumps(c.get('search_network_warnings') or [])}`.",
        "Network samples are indicative, not a latency percentile. See `benchmarks/results/` for the p50/p95 run.",
    ]
    markdown = "\n".join(lines) + "\n"
    out.with_suffix(".md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"wrote {out} and {out.with_suffix('.md')}", file=sys.stderr)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--cache-dir", default="benchmarks/.cold-cache")
    p.add_argument("--out", default="benchmarks/results/cold_start.json")
    return asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
