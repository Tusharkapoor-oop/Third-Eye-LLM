"""
Comprehensive Baseline Evaluation Suite.
Runs search, extraction, security, and schema tests against the WebIntel engine.
Records all results to the persistent evidence database.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DEFAULT_SEARCH_PROVIDER", "ddgs")

# Load .env
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from testing.runner.evidence_db import TestEvidenceDB, TestStatus
from testing.runner.benchmark_runner import BenchmarkRunner, count_tokens

import tiktoken


# ─── SECURITY TEST VECTORS ───
SSRF_VECTORS = [
    ("ssrf_localhost", "http://localhost/", True),
    ("ssrf_localhost_8080", "http://localhost:8080/", True),
    ("ssrf_127_0_0_1", "http://127.0.0.1/", True),
    ("ssrf_127_0_0_1_admin", "http://127.0.0.1/admin", True),
    ("ssrf_0_0_0_0", "http://0.0.0.0/", True),
    ("ssrf_ipv6_loopback", "http://[::1]/", True),
    ("ssrf_ipv4_mapped_ipv6", "http://[::ffff:127.0.0.1]/", True),
    ("ssrf_metadata_169", "http://169.254.169.254/latest/meta-data/", True),
    ("ssrf_10_private", "http://10.0.0.1/", True),
    ("ssrf_172_private", "http://172.16.0.1/", True),
    ("ssrf_192_168_private", "http://192.168.1.1/", True),
    ("ssrf_file_scheme", "file:///etc/passwd", True),
    ("ssrf_ftp_scheme", "ftp://evil.com/data", True),
    ("ssrf_gopher_scheme", "gopher://evil.com/", True),
    ("ssrf_userinfo", "http://admin:password@evil.com/", True),
    ("ssrf_null_byte", "http://example.com/path\x00/evil", True),
    ("ssrf_dotlocal", "http://myhost.local/", True),
    ("ssrf_localhost_subdomain", "http://test.localhost/", True),
    ("ssrf_port_scan", "http://example.com:22/", True),
    ("ssrf_port_3306", "http://example.com:3306/", True),
    # These should be ALLOWED
    ("allowed_google", "https://www.google.com/", False),
    ("allowed_wikipedia", "https://en.wikipedia.org/wiki/Python", False),
    ("allowed_github", "https://github.com/", False),
]

# ─── SEARCH EVALUATION QUERIES ───
SEARCH_EVAL_QUERIES = [
    {
        "query": "What is the capital city of France?",
        "expected": "Paris",
        "sources": ["wikipedia.org"],
        "unanswerable": False,
        "category": "factual"
    },
    {
        "query": "Who created the Linux kernel?",
        "expected": "Linus Torvalds",
        "sources": ["wikipedia.org", "kernel.org"],
        "unanswerable": False,
        "category": "factual"
    },
    {
        "query": "What transport protocol does HTTP/3 use?",
        "expected": "QUIC",
        "sources": ["wikipedia.org", "cloudflare.com", "ietf.org"],
        "unanswerable": False,
        "category": "technical"
    },
    {
        "query": "Python asyncio event loop documentation",
        "expected": "asyncio",
        "sources": ["docs.python.org"],
        "unanswerable": False,
        "category": "documentation"
    },
    {
        "query": "What is the chemical formula for water?",
        "expected": "H2O",
        "sources": ["wikipedia.org"],
        "unanswerable": False,
        "category": "factual"
    },
    {
        "query": "GTA 8 official release date",
        "expected": "",
        "sources": [],
        "unanswerable": True,
        "category": "unanswerable"
    },
    {
        "query": "Nobel Prize in Computer Science 2025",
        "expected": "",
        "sources": [],
        "unanswerable": True,
        "category": "unanswerable"
    },
    {
        "query": "Windows 14 system requirements",
        "expected": "",
        "sources": [],
        "unanswerable": True,
        "category": "unanswerable"
    },
    {
        "query": "How does BM25 ranking algorithm work?",
        "expected": "BM25",
        "sources": ["wikipedia.org"],
        "unanswerable": False,
        "category": "technical"
    },
    {
        "query": "What is Rust programming language used for?",
        "expected": "Rust",
        "sources": ["wikipedia.org", "rust-lang.org"],
        "unanswerable": False,
        "category": "technical"
    },
]

# ─── EXTRACTION TEST URLS ───
EXTRACT_TEST_URLS = [
    {
        "url": "https://en.wikipedia.org/wiki/Python_(programming_language)",
        "query": "What is Python programming language?",
        "expected": "Python",
        "category": "wiki"
    },
    {
        "url": "https://en.wikipedia.org/wiki/HTTP/3",
        "query": "What transport protocol does HTTP/3 use?",
        "expected": "QUIC",
        "category": "wiki"
    },
    {
        "url": "https://docs.python.org/3/library/asyncio.html",
        "query": "Python asyncio module",
        "expected": "asyncio",
        "category": "documentation"
    },
]


async def run_schema_token_test(db: TestEvidenceDB, run_id: str) -> list:
    """Measure schema token overhead for all 5 tools."""
    from src.server.tools import TOOL_DEFINITIONS

    records = []
    tokenizer = tiktoken.get_encoding("o200k_base")
    cl100k = tiktoken.get_encoding("cl100k_base")

    full_schema = json.dumps(TOOL_DEFINITIONS, separators=(",", ":"))
    o200k_tokens = len(tokenizer.encode(full_schema))
    cl100k_tokens = len(cl100k.encode(full_schema))

    record = db.create_record(
        run_id=run_id,
        suite_name="schema_tokens",
        test_name="total_schema_overhead",
        expected_outcome="<1000 tokens (o200k)",
        actual_outcome=json.dumps({
            "o200k_base": o200k_tokens,
            "cl100k_base": cl100k_tokens,
            "tool_count": len(TOOL_DEFINITIONS)
        }),
        token_count=o200k_tokens,
        token_method="o200k_base",
    )

    if o200k_tokens <= 1000:
        record.status = TestStatus.PASS
    else:
        record.status = TestStatus.FAIL
        record.assertion_failures = f"Schema tokens {o200k_tokens} > 1000 budget"

    db.record_test(record)
    records.append(record)

    # Per-tool token counts
    for tool in TOOL_DEFINITIONS:
        tool_json = json.dumps(tool, separators=(",", ":"))
        tool_tokens = len(tokenizer.encode(tool_json))
        rec = db.create_record(
            run_id=run_id,
            suite_name="schema_tokens",
            test_name=f"tool_{tool['name']}_tokens",
            actual_outcome=str(tool_tokens),
            token_count=tool_tokens,
            token_method="o200k_base",
            status=TestStatus.PASS,
        )
        db.record_test(rec)
        records.append(rec)

    return records


async def run_baseline_evaluation():
    """Run the complete baseline evaluation suite."""
    print("=" * 70)
    print("  WEBLENS BASELINE EVALUATION SUITE")
    print(f"  Started: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=" * 70)

    db = TestEvidenceDB()
    runner = BenchmarkRunner(db)
    run_id = runner.run_id

    # Phase 1: Schema Token Tests
    print("\n[1/4] Schema Token Measurement...")
    schema_results = await run_schema_token_test(db, run_id)
    schema_pass = sum(1 for r in schema_results if r.status == TestStatus.PASS)
    print(f"  Schema tests: {schema_pass}/{len(schema_results)} passed")

    # Phase 2: Security Tests (SSRF)
    print("\n[2/4] Security / SSRF Tests...")
    sec_pass = 0
    sec_fail = 0
    for test_name, url, should_block in SSRF_VECTORS:
        rec = await runner.run_security_test(
            test_name=test_name,
            url=url,
            expected_blocked=should_block,
        )
        if rec.status == TestStatus.PASS:
            sec_pass += 1
        else:
            sec_fail += 1
            print(f"    FAIL: {test_name} — {rec.assertion_failures}")
    print(f"  Security tests: {sec_pass}/{sec_pass + sec_fail} passed")

    # Phase 3: Search Benchmark
    print("\n[3/4] Search Benchmark (10 queries)...")
    search_pass = 0
    search_fail = 0
    search_latencies = []
    search_tokens = []

    for i, q in enumerate(SEARCH_EVAL_QUERIES):
        print(f"  [{i+1}/{len(SEARCH_EVAL_QUERIES)}] {q['query'][:50]}...")
        rec = await runner.run_search_benchmark(
            query=q["query"],
            test_name=f"search_{q['category']}_{i+1:03d}",
            expected_answer=q["expected"],
            acceptable_sources=q["sources"],
            is_unanswerable=q["unanswerable"],
        )
        if rec.status == TestStatus.PASS:
            search_pass += 1
        else:
            search_fail += 1
        search_latencies.append(rec.duration_seconds)
        search_tokens.append(rec.token_count)
        await asyncio.sleep(1.0)  # Rate limit

    print(f"  Search tests: {search_pass}/{search_pass + search_fail} passed")
    if search_latencies:
        print(f"  Search latency p50: {sorted(search_latencies)[len(search_latencies)//2]:.3f}s")
        print(f"  Search tokens avg: {sum(search_tokens)/len(search_tokens):.0f}")

    # Phase 4: Extraction Benchmark
    print("\n[4/4] Extraction Benchmark (3 URLs)...")
    ext_pass = 0
    ext_fail = 0
    ext_latencies = []
    ext_tokens = []

    for i, e in enumerate(EXTRACT_TEST_URLS):
        print(f"  [{i+1}/{len(EXTRACT_TEST_URLS)}] {e['url'][:60]}...")
        rec = await runner.run_extract_benchmark(
            url=e["url"],
            test_name=f"extract_{e['category']}_{i+1:03d}",
            query=e["query"],
            expected_content=e["expected"],
        )
        if rec.status == TestStatus.PASS:
            ext_pass += 1
        else:
            ext_fail += 1
        ext_latencies.append(rec.duration_seconds)
        ext_tokens.append(rec.token_count)
        await asyncio.sleep(0.5)

    print(f"  Extract tests: {ext_pass}/{ext_pass + ext_fail} passed")
    if ext_latencies:
        print(f"  Extract latency p50: {sorted(ext_latencies)[len(ext_latencies)//2]:.3f}s")
        print(f"  Extract tokens avg: {sum(ext_tokens)/len(ext_tokens):.0f}")

    # Summary
    runner.print_summary()

    # Save run summary to JSON
    summary = db.get_run_summary(run_id)
    summary["search_latencies"] = search_latencies
    summary["search_tokens"] = search_tokens
    summary["extract_latencies"] = ext_latencies
    summary["extract_tokens"] = ext_tokens

    summary_path = PROJECT_ROOT / "test-results" / "runs" / f"{run_id}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nRun details saved to: {summary_path}")

    return summary


if __name__ == "__main__":
    asyncio.run(run_baseline_evaluation())
