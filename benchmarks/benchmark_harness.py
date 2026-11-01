"""
WebIntel Benchmark Harness — Phase 2/3.

A reproducible, provider-agnostic benchmarking system for the WebIntel engine
and competitor search/extraction providers.

Supports:
- Repeatable test cases with identical queries across providers
- Configurable repetitions, warm-up requests
- Cold-start and warm-cache experiments
- Sequential and concurrent execution
- Fixed timeouts, controlled retry policies
- Raw response preservation with secret redaction
- Structured JSONL results + CSV summaries
- Machine-readable failure reasons
- Reproducible random seeds
- Run metadata and version information

Usage:
    python -m benchmarks.benchmark_harness --config harness_config.json
    python -m benchmarks.benchmark_harness --quick  # smoke test with 5 queries
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import re
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure src/ is importable when run as a module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _load_project_env(path: Path | None = None) -> None:
    """Load .env key=value pairs into os.environ without shadowing explicit values.

    Config is read from process env at import time of src.engine.config, so this
    must run before those imports. Keys in .env never override already-set vars
    (real environment wins)."""
    env_path = path or Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_project_env()

import tiktoken  # type: ignore

from src.engine.config import CONFIG
from src.engine.search.aggregator import SearchAggregator
from src.engine.search.tavily_provider import TavilySearchProvider
from src.engine.extract.extractor import DocumentExtractor
from src.engine.search.base import SearchResult
from src.server.token_counter import measure_tool_schema_tokens

# --- Secret redaction -------------------------------------------------------

SECRET_PATTERNS = [
    re.compile(r"tvly-[A-Za-z0-9_\-]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]+"),
    re.compile(r"Authorization:\s*.+"),
]


def redact_secrets(text: str) -> str:
    """Redact API keys and secrets from text for safe logging."""
    result = text
    for pat in SECRET_PATTERNS:
        result = pat.sub("[REDACTED]", result)
    return result


# --- Data models ------------------------------------------------------------


@dataclass
class QueryCase:
    id: int
    query: str
    category: str
    ground_truth_answer: str
    acceptable_sources: list[str] = field(default_factory=list)
    is_unanswerable: bool = False
    has_conflict: bool = False
    requires_live: bool = True
    difficulty: str = "medium"


@dataclass
class ProviderResult:
    provider: str
    query_id: int
    query: str
    status: str
    latency_sec: float
    result_count: int
    tokens_returned: int
    results: list[dict] = field(default_factory=list)
    error: str | None = None
    cache_hit: bool = False
    raw_response: str | None = None  # secret-redacted


@dataclass
class ExtractionResult:
    provider: str
    query_id: int
    url: str
    status: str
    latency_sec: float
    tokens_used: int
    passages_count: int
    error: str | None = None


@dataclass
class RunMetadata:
    run_id: str
    timestamp: str
    python_version: str
    platform: str
    commit: str | None
    config: dict[str, Any]
    dataset_version: str
    total_queries: int
    providers_tested: list[str]


# --- Token measurement ------------------------------------------------------


def count_tokens(text: str, model: str = "o200k_base") -> int:
    """Count tokens using the specified tokenizer encoding."""
    try:
        enc = tiktoken.get_encoding(model)
        return len(enc.encode(text))
    except Exception:
        # Fallback: rough estimate ~4 chars per token
        return max(1, len(text) // 4)


# --- Benchmark Harness ------------------------------------------------------


class BenchmarkHarness:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.run_id = str(uuid.uuid4())[:8]
        self.results_dir = Path(config.get("results_dir", "reports/benchmark_runs"))
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.results_dir / f"run_{self.run_id}.jsonl"
        self.csv_path = self.results_dir / f"run_{self.run_id}.csv"

        self.tokenizer = tiktoken.get_encoding("o200k_base")
        self.aggregator = SearchAggregator()
        self.extractor = DocumentExtractor()
        self.tavily = TavilySearchProvider()

        self._results: list[dict] = []
        self._cache: dict[str, Any] = {}  # simple in-memory cache for warm tests

    # -- dataset loading -----------------------------------------------------

    def load_dataset(self, path: str) -> list[QueryCase]:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        cases = []
        for item in raw:
            cases.append(
                QueryCase(
                    id=item["id"],
                    query=item["query"],
                    category=item.get("category", "uncategorized"),
                    ground_truth_answer=item.get("ground_truth_answer", ""),
                    acceptable_sources=item.get("acceptable_sources", []),
                    is_unanswerable=item.get("is_unanswerable", False),
                    has_conflict=item.get("has_conflict", False),
                    difficulty=item.get("difficulty", "medium"),
                )
            )
        return cases

    # -- provider execution --------------------------------------------------

    async def run_search_provider(
        self,
        provider_name: str,
        query_case: QueryCase,
        count: int = 5,
        max_tokens: int | None = None,
    ) -> ProviderResult:
        """Run a single search query against a provider."""
        max_tokens = max_tokens or CONFIG.default_search_tokens
        start = time.perf_counter()
        error = None
        results: list[SearchResult] = []
        status = "error"
        cache_hit = False

        # Check cache for warm-cache experiments
        cache_key = f"{provider_name}:{query_case.query.lower().strip()}:{count}"
        if self.config.get("warm_cache") and cache_key in self._cache:
            cached = self._cache[cache_key]
            latency = time.perf_counter() - start
            return ProviderResult(
                provider=provider_name,
                query_id=query_case.id,
                query=query_case.query,
                status=cached["status"],
                latency_sec=round(latency, 4),
                result_count=len(cached["results"]),
                tokens_returned=cached["tokens_returned"],
                results=cached["results"],
                cache_hit=True,
                raw_response=redact_secrets(json.dumps(cached["raw_response"])),
            )

        try:
            if provider_name == "tavily":
                if not self.tavily.is_available():
                    status = "unavailable"
                    error = "Tavily API key not configured"
                else:
                    results = await self.tavily.search(
                        query_case.query,
                        count=count,
                        time_filter=None,
                        domains=None,
                    )
                    status = "success" if results else "no_reliable_result"
            elif provider_name in self.aggregator.providers:
                provider = self.aggregator.providers[provider_name]
                results = await asyncio.wait_for(
                    provider.search(
                        query_case.query,
                        count=count,
                        time_filter=None,
                        domains=None,
                    ),
                    timeout=CONFIG.connect_timeout + 2.0,
                )
                status = "success" if results else "no_reliable_result"
            else:
                status = "unknown_provider"
                error = f"Provider {provider_name} not found"
        except asyncio.TimeoutError:
            status = "timeout"
            error = f"Search timed out after {CONFIG.connect_timeout + 2.0}s"
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = f"{type(exc).__name__}: {exc}"

        latency = round(time.perf_counter() - start, 4)
        tokens_returned = sum(
            count_tokens(f"{r.title} {r.snippet}") for r in results
        )

        result_dicts = [
            {"title": r.title, "url": r.url, "snippet": r.snippet, "provider": r.provider}
            for r in results
        ]

        # Cache for warm experiments
        if self.config.get("warm_cache") and status == "success":
            self._cache[cache_key] = {
                "status": status,
                "results": result_dicts,
                "tokens_returned": tokens_returned,
                "raw_response": result_dicts,
            }

        return ProviderResult(
            provider=provider_name,
            query_id=query_case.id,
            query=query_case.query,
            status=status,
            latency_sec=latency,
            result_count=len(results),
            tokens_returned=tokens_returned,
            results=result_dicts,
            error=error,
            cache_hit=cache_hit,
            raw_response=redact_secrets(json.dumps(result_dicts)),
        )

    async def run_extraction(
        self,
        query_case: QueryCase,
        url: str,
        query: str | None = None,
    ) -> ExtractionResult:
        """Run a single URL extraction."""
        start = time.perf_counter()
        error = None
        status = "error"

        try:
            doc = await asyncio.wait_for(
                self.extractor.extract_url(
                    url=url,
                    query=query or query_case.query,
                    mode="passages",
                    max_tokens=CONFIG.default_extract_tokens,
                ),
                timeout=CONFIG.read_timeout + 2.0,
            )
            status = doc.status
        except asyncio.TimeoutError:
            status = "timeout"
            error = f"Extraction timed out after {CONFIG.read_timeout + 2.0}s"
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = f"{type(exc).__name__}: {exc}"

        latency = round(time.perf_counter() - start, 4)

        # Re-fetch doc to get tokens if we have it
        tokens_used = 0
        passages_count = 0
        try:
            doc = await self.extractor.extract_url(
                url=url,
                query=query or query_case.query,
                mode="passages",
                max_tokens=CONFIG.default_extract_tokens,
            )
            tokens_used = doc.tokens_used
            passages_count = len(doc.passages)
        except Exception:
            pass

        return ExtractionResult(
            provider="engine",
            query_id=query_case.id,
            url=url,
            status=status,
            latency_sec=latency,
            tokens_used=tokens_used,
            passages_count=passages_count,
            error=error,
        )

    # -- run orchestration ---------------------------------------------------

    async def run_provider_comparison(
        self,
        cases: list[QueryCase],
        providers: list[str],
        repetitions: int = 1,
        warm_up: bool = False,
        concurrent: bool = False,
    ) -> list[dict]:
        """Run search provider comparison across all cases and providers."""
        all_results: list[dict] = []

        if warm_up:
            print("[Warm-up] Running warm-up queries...")
            for case in cases[:3]:
                for prov in providers:
                    await self.run_search_provider(prov, case, count=3)
            print("[Warm-up] Complete.\n")

        delay = self.config.get("delay", 1.0)

        for rep in range(repetitions):
            print(f"[Repetition {rep + 1}/{repetitions}]")
            for i, case in enumerate(cases):
                if i > 0 and delay > 0:
                    await asyncio.sleep(delay)
                if concurrent:
                    tasks = [
                        self.run_search_provider(prov, case) for prov in providers
                    ]
                    provider_results = await asyncio.gather(*tasks)
                else:
                    provider_results = []
                    for prov in providers:
                        provider_results.append(
                            await self.run_search_provider(prov, case)
                        )

                for pr in provider_results:
                    result_record = {
                        "run_id": self.run_id,
                        "repetition": rep + 1,
                        "provider": pr.provider,
                        "query_id": pr.query_id,
                        "query": pr.query,
                        "category": case.category,
                        "difficulty": case.difficulty,
                        "is_unanswerable": case.is_unanswerable,
                        "status": pr.status,
                        "latency_sec": pr.latency_sec,
                        "result_count": pr.result_count,
                        "tokens_returned": pr.tokens_returned,
                        "cache_hit": pr.cache_hit,
                        "error": pr.error,
                        "raw_response": pr.raw_response,
                    }
                    all_results.append(result_record)
                    self._results.append(result_record)

                    # Write JSONL incrementally
                    with open(self.jsonl_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(result_record, ensure_ascii=False) + "\n")

        return all_results

    async def run_end_to_end(
        self,
        cases: list[QueryCase],
        provider: str = "ddgs",
        repetitions: int = 1,
    ) -> list[dict]:
        """Run full search + extract workflow for end-to-end latency."""
        all_results: list[dict] = []

        for rep in range(repetitions):
            print(f"[E2E Repetition {rep + 1}/{repetitions}]")
            for case in cases:
                # Search
                search_res = await self.run_search_provider(provider, case)

                e2e_record = {
                    "run_id": self.run_id,
                    "repetition": rep + 1,
                    "provider": provider,
                    "query_id": case.id,
                    "query": case.query,
                    "category": case.category,
                    "search_status": search_res.status,
                    "search_latency_sec": search_res.latency_sec,
                    "search_result_count": search_res.result_count,
                    "search_tokens": search_res.tokens_returned,
                }

                # Extract top result if search succeeded
                if search_res.status == "success" and search_res.results:
                    top_url = search_res.results[0]["url"]
                    ext_res = await self.run_extraction(case, top_url)
                    e2e_record.update(
                        {
                            "extract_url": top_url,
                            "extract_status": ext_res.status,
                            "extract_latency_sec": ext_res.latency_sec,
                            "extract_tokens": ext_res.tokens_used,
                            "extract_passages": ext_res.passages_count,
                            "extract_error": ext_res.error,
                            "e2e_latency_sec": round(
                                search_res.latency_sec + ext_res.latency_sec, 4
                            ),
                        }
                    )
                else:
                    e2e_record.update(
                        {
                            "extract_url": None,
                            "extract_status": "skipped",
                            "extract_latency_sec": 0.0,
                            "extract_tokens": 0,
                            "extract_passages": 0,
                            "extract_error": "No search results to extract",
                            "e2e_latency_sec": search_res.latency_sec,
                        }
                    )

                all_results.append(e2e_record)
                self._results.append(e2e_record)

                with open(self.jsonl_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(e2e_record, ensure_ascii=False) + "\n")

        return all_results

    # -- reporting -----------------------------------------------------------

    def write_csv_summary(self, results: list[dict]) -> None:
        """Write a CSV summary of results."""
        if not results:
            return
        fieldnames = list(results[0].keys())
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in results:
                writer.writerow(row)

    def write_manifest(self, cases: list[QueryCase], providers: list[str]) -> None:
        """Write run metadata manifest."""
        import platform as _platform

        commit = None
        try:
            import subprocess

            commit = (
                subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent.parent)
                .decode()
                .strip()
            )
        except Exception:
            pass

        schema = measure_tool_schema_tokens()

        metadata = RunMetadata(
            run_id=self.run_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            python_version=sys.version,
            platform=_platform.platform(),
            commit=commit,
            config=self.config,
            dataset_version="eval_dataset.json",
            total_queries=len(cases),
            providers_tested=providers,
        )

        manifest = asdict(metadata)
        manifest["schema_tokens_o200k"] = schema["total_o200k"]
        manifest["schema_tokens_cl100k"] = schema["total_cl100k"]

        manifest_path = self.results_dir / f"manifest_{self.run_id}.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return manifest_path

    def compute_summary_stats(self, results: list[dict]) -> dict[str, Any]:
        """Compute summary statistics from results."""
        if not results:
            return {}

        latencies = [r["latency_sec"] for r in results if r.get("latency_sec") is not None]
        tokens = [r["tokens_returned"] for r in results if r.get("tokens_returned") is not None]
        successes = [r for r in results if r.get("status") == "success"]
        failures = [r for r in results if r.get("status") in ("error", "timeout", "unavailable")]

        def pct(values: list[float], p: float) -> float:
            if not values:
                return 0.0
            s = sorted(values)
            k = (len(s) - 1) * (p / 100.0)
            f = int(k)
            c = min(f + 1, len(s) - 1)
            if f == c:
                return s[f]
            return s[f] + (s[c] - s[f]) * (k - f)

        return {
            "total_runs": len(results),
            "success_count": len(successes),
            "failure_count": len(failures),
            "success_rate_pct": round(len(successes) / len(results) * 100, 2),
            "latency": {
                "min": round(min(latencies), 4) if latencies else 0,
                "median": round(pct(latencies, 50), 4) if latencies else 0,
                "mean": round(sum(latencies) / len(latencies), 4) if latencies else 0,
                "p90": round(pct(latencies, 90), 4) if latencies else 0,
                "p95": round(pct(latencies, 95), 4) if latencies else 0,
                "p99": round(pct(latencies, 99), 4) if latencies else 0,
                "max": round(max(latencies), 4) if latencies else 0,
            },
            "tokens": {
                "min": min(tokens) if tokens else 0,
                "median": round(pct(tokens, 50), 1) if tokens else 0,
                "mean": round(sum(tokens) / len(tokens), 1) if tokens else 0,
                "p95": round(pct(tokens, 95), 1) if tokens else 0,
                "max": max(tokens) if tokens else 0,
            },
        }


# --- CLI -------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="WebIntel Benchmark Harness")
    parser.add_argument("--dataset", default="benchmarks/eval_dataset.json", help="Path to eval dataset JSON")
    parser.add_argument("--providers", nargs="+", default=["ddgs", "bing", "tavily"], help="Providers to test")
    parser.add_argument("--repetitions", type=int, default=1, help="Number of repetitions")
    parser.add_argument("--warm-up", action="store_true", help="Run warm-up queries before benchmarking")
    parser.add_argument("--warm-cache", action="store_true", help="Enable warm-cache experiments")
    parser.add_argument("--concurrent", action="store_true", help="Run providers concurrently per query")
    parser.add_argument("--quick", action="store_true", help="Quick smoke test with first 5 queries")
    parser.add_argument("--results-dir", default="reports/benchmark_runs", help="Directory for output files")
    parser.add_argument("--e2e", action="store_true", help="Run end-to-end search + extract workflow")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay in seconds between queries (rate limiting)")
    args = parser.parse_args()

    config = {
        "results_dir": args.results_dir,
        "warm_cache": args.warm_cache,
        "concurrent": args.concurrent,
        "repetitions": args.repetitions,
        "warm_up": args.warm_up,
        "delay": args.delay,
    }

    harness = BenchmarkHarness(config)
    cases = harness.load_dataset(args.dataset)

    if args.quick:
        cases = cases[:5]
        print(f"[Quick mode] Testing {len(cases)} queries")

    providers = [p for p in args.providers if p in ("ddgs", "bing", "tavily")]
    if not providers:
        providers = ["ddgs"]

    print(f"Benchmark run ID: {harness.run_id}")
    print(f"Providers: {providers}")
    print(f"Queries: {len(cases)}")
    print(f"Repetitions: {args.repetitions}")
    print(f"Warm cache: {args.warm_cache}")
    print(f"Concurrent: {args.concurrent}")
    print(f"Tavily available: {harness.tavily.is_available()}")
    print()

    if args.e2e:
        results = asyncio.run(harness.run_end_to_end(cases, provider=providers[0], repetitions=args.repetitions))
    else:
        results = asyncio.run(
            harness.run_provider_comparison(
                cases, providers,
                repetitions=args.repetitions,
                warm_up=args.warm_up,
                concurrent=args.concurrent,
            )
        )

    harness.write_csv_summary(results)
    manifest_path = harness.write_manifest(cases, providers)

    stats = harness.compute_summary_stats(results)
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Run ID: {harness.run_id}")
    print(f"Total runs: {stats.get('total_runs', 0)}")
    print(f"Success rate: {stats.get('success_rate_pct', 0)}%")
    print(f"Latency p50/p95/p99: {stats.get('latency', {}).get('median', 0)}s / {stats.get('latency', {}).get('p95', 0)}s / {stats.get('latency', {}).get('p99', 0)}s")
    print(f"Tokens median/mean/p95: {stats.get('tokens', {}).get('median', 0)} / {stats.get('tokens', {}).get('mean', 0)} / {stats.get('tokens', {}).get('p95', 0)}")
    print(f"\nJSONL results: {harness.jsonl_path}")
    print(f"CSV summary: {harness.csv_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
