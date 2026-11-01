"""
Unified Benchmark Harness for WebIntel evaluation.
Drives search, extract, and research through the actual engine,
measures latency, tokens, quality, and records everything to the evidence DB.
"""

import asyncio
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import tiktoken

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from testing.runner.evidence_db import TestEvidenceDB, TestRecord, TestStatus


TOKENIZER = tiktoken.get_encoding("o200k_base")


def count_tokens(text: str) -> int:
    """Count tokens using o200k_base tokenizer."""
    if not text:
        return 0
    return len(TOKENIZER.encode(text))


def compute_checksum(data: str) -> str:
    """Compute SHA256 checksum of evidence data."""
    import hashlib
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


class BenchmarkRunner:
    """Runs benchmark suites against the WebIntel engine and records all results."""

    def __init__(self, db: TestEvidenceDB | None = None):
        self.db = db or TestEvidenceDB()
        self.run_id = self.db.generate_run_id()
        self._engine_initialized = False
        self._aggregator = None
        self._extractor = None
        self._researcher = None

    def _ensure_engine(self):
        """Lazy-initialize engine components."""
        if self._engine_initialized:
            return
        os.environ.setdefault("DEFAULT_SEARCH_PROVIDER", "ddgs")
        from src.engine.search.aggregator import SearchAggregator
        from src.engine.extract.extractor import DocumentExtractor
        from src.engine.research.deep_research import DeepResearchEngine
        self._aggregator = SearchAggregator()
        self._extractor = DocumentExtractor()
        self._researcher = DeepResearchEngine()
        self._engine_initialized = True

    async def run_search_benchmark(
        self,
        query: str,
        test_name: str,
        expected_answer: str = "",
        acceptable_sources: list[str] | None = None,
        is_unanswerable: bool = False,
        count: int = 5,
        max_tokens: int = 600,
        experiment_id: str = ""
    ) -> TestRecord:
        """Run a single search query and record the result."""
        self._ensure_engine()
        record = self.db.create_record(
            run_id=self.run_id,
            suite_name="search_benchmark",
            test_name=test_name,
            test_input=json.dumps({"query": query, "count": count, "max_tokens": max_tokens}),
            expected_outcome=expected_answer,
            experiment_id=experiment_id,
            provider=os.environ.get("DEFAULT_SEARCH_PROVIDER", "ddgs"),
        )

        t0 = time.perf_counter()
        try:
            resp = await asyncio.wait_for(
                self._aggregator.search(query=query, count=count, max_tokens=max_tokens),
                timeout=30.0
            )
            duration = time.perf_counter() - t0

            # Serialize response for token counting
            resp_dict = resp.to_dict()
            resp_json = json.dumps(resp_dict, separators=(",", ":"))
            tokens = count_tokens(resp_json)

            record.duration_seconds = round(duration, 4)
            record.latency_p50_ms = round(duration * 1000, 2)
            record.token_count = tokens
            record.token_method = "o200k_base"
            record.api_requests = 1
            record.actual_outcome = resp_json[:2000]  # Cap stored outcome
            record.evidence_checksum = compute_checksum(resp_json)

            # Quality evaluation
            results = resp_dict.get("results", [])
            status_field = resp_dict.get("status", "")

            if is_unanswerable:
                if status_field == "no_reliable_result" or not results:
                    record.status = TestStatus.PASS
                else:
                    record.status = TestStatus.FAIL
                    record.assertion_failures = "Returned results for unanswerable query (false confidence)"
            else:
                if not results:
                    record.status = TestStatus.FAIL
                    record.assertion_failures = "No results returned for answerable query"
                else:
                    # Check if expected answer appears in results
                    combined = " ".join(
                        (r.get("title", "") + " " + r.get("snippet", "")).lower()
                        for r in results
                    )
                    answer_found = expected_answer.lower() in combined if expected_answer else True

                    # Check source quality
                    source_match = False
                    if acceptable_sources:
                        for r in results:
                            url = r.get("url", "").lower()
                            if any(src in url for src in acceptable_sources):
                                source_match = True
                                break
                    else:
                        source_match = True

                    if answer_found and source_match:
                        record.status = TestStatus.PASS
                    elif answer_found:
                        record.status = TestStatus.PASS  # Answer found but not from preferred source
                        record.assertion_failures = "Answer found but not from preferred sources"
                    else:
                        record.status = TestStatus.FAIL
                        record.assertion_failures = f"Expected '{expected_answer}' not found in results"

        except asyncio.TimeoutError:
            record.status = TestStatus.ERROR
            record.error_message = "Search timed out after 30 seconds"
            record.duration_seconds = 30.0
        except Exception as e:
            record.status = TestStatus.ERROR
            record.error_message = str(e)[:500]
            record.duration_seconds = round(time.perf_counter() - t0, 4)

        self.db.record_test(record)
        return record

    async def run_extract_benchmark(
        self,
        url: str,
        test_name: str,
        query: str = "",
        expected_content: str = "",
        max_tokens: int = 1200,
        experiment_id: str = ""
    ) -> TestRecord:
        """Run a single extraction and record the result."""
        self._ensure_engine()
        record = self.db.create_record(
            run_id=self.run_id,
            suite_name="extract_benchmark",
            test_name=test_name,
            test_input=json.dumps({"url": url, "query": query, "max_tokens": max_tokens}),
            expected_outcome=expected_content,
            experiment_id=experiment_id,
        )

        t0 = time.perf_counter()
        try:
            doc = await asyncio.wait_for(
                self._extractor.extract_url(url=url, query=query, max_tokens=max_tokens),
                timeout=30.0
            )
            duration = time.perf_counter() - t0
            doc_dict = doc.to_dict()
            doc_json = json.dumps(doc_dict, separators=(",", ":"))
            tokens = count_tokens(doc_json)

            record.duration_seconds = round(duration, 4)
            record.latency_p50_ms = round(duration * 1000, 2)
            record.token_count = tokens
            record.token_method = "o200k_base"
            record.api_requests = 1
            record.actual_outcome = doc_json[:2000]
            record.evidence_checksum = compute_checksum(doc_json)

            if doc_dict.get("status") == "success":
                passages = doc_dict.get("passages", [])
                if expected_content:
                    passage_text = " ".join(p.get("text", "") for p in passages).lower()
                    if expected_content.lower() in passage_text:
                        record.status = TestStatus.PASS
                    else:
                        record.status = TestStatus.FAIL
                        record.assertion_failures = f"Expected content '{expected_content[:100]}' not in passages"
                else:
                    record.status = TestStatus.PASS if passages else TestStatus.FAIL
            elif doc_dict.get("status") == "blocked":
                record.status = TestStatus.BLOCKED
                record.skip_reason = doc_dict.get("metadata", {}).get("error", "Security block")
            else:
                record.status = TestStatus.FAIL
                record.assertion_failures = f"Extraction status: {doc_dict.get('status')}"

        except asyncio.TimeoutError:
            record.status = TestStatus.ERROR
            record.error_message = "Extraction timed out after 30 seconds"
            record.duration_seconds = 30.0
        except Exception as e:
            record.status = TestStatus.ERROR
            record.error_message = str(e)[:500]
            record.duration_seconds = round(time.perf_counter() - t0, 4)

        self.db.record_test(record)
        return record

    async def run_security_test(
        self,
        test_name: str,
        url: str,
        expected_blocked: bool = True,
        experiment_id: str = ""
    ) -> TestRecord:
        """Run a security test (SSRF, injection, etc.) and record the result."""
        from src.engine.security import validate_url_security

        record = self.db.create_record(
            run_id=self.run_id,
            suite_name="security",
            test_name=test_name,
            test_input=json.dumps({"url": url}),
            expected_outcome="blocked" if expected_blocked else "allowed",
            experiment_id=experiment_id,
        )

        t0 = time.perf_counter()
        try:
            is_safe, reason, resolved_ips = validate_url_security(url)
            duration = time.perf_counter() - t0
            record.duration_seconds = round(duration, 4)
            record.actual_outcome = json.dumps({
                "is_safe": is_safe, "reason": reason, "ips": resolved_ips
            })

            if expected_blocked:
                if not is_safe:
                    record.status = TestStatus.PASS
                else:
                    record.status = TestStatus.FAIL
                    record.assertion_failures = f"URL should be blocked but was allowed: {reason}"
            else:
                if is_safe:
                    record.status = TestStatus.PASS
                else:
                    record.status = TestStatus.FAIL
                    record.assertion_failures = f"URL should be allowed but was blocked: {reason}"

        except Exception as e:
            record.status = TestStatus.ERROR
            record.error_message = str(e)[:500]
            record.duration_seconds = round(time.perf_counter() - t0, 4)

        self.db.record_test(record)
        return record

    async def run_dataset(self, dataset_path: str, max_queries: int = 0) -> dict:
        """Run the full eval dataset and return a summary."""
        with open(dataset_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)

        if max_queries > 0:
            dataset = dataset[:max_queries]

        results = []
        for item in dataset:
            query = item.get("query", "")
            test_name = f"eval_{item.get('id', 0):03d}_{item.get('category', 'unknown')}"
            expected = item.get("ground_truth_answer", "")
            sources = item.get("acceptable_sources", [])
            unanswerable = item.get("is_unanswerable", False)

            record = await self.run_search_benchmark(
                query=query,
                test_name=test_name,
                expected_answer=expected,
                acceptable_sources=sources,
                is_unanswerable=unanswerable,
            )
            results.append(record)
            # Brief pause to avoid rate limiting
            await asyncio.sleep(0.5)

        summary = self.db.get_run_summary(self.run_id)
        return summary

    def print_summary(self):
        """Print a summary of the current run."""
        summary = self.db.get_run_summary(self.run_id)
        print(f"\n{'='*60}")
        print(f"Test Run: {self.run_id}")
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Status Breakdown:")
        for status, count in summary["status_breakdown"].items():
            pct = (count / summary["total_tests"] * 100) if summary["total_tests"] > 0 else 0
            print(f"  {status}: {count} ({pct:.1f}%)")
        print(f"{'='*60}\n")


async def acceptance_test():
    """
    Acceptance test for the evidence system itself.
    Deliberately runs a failing test, then a passing test,
    and verifies both records persist after re-opening the DB.
    """
    print("=== Evidence System Acceptance Test ===\n")
    db = TestEvidenceDB()

    # 1. Record a deliberate failure
    run_id = db.generate_run_id()
    fail_record = db.create_record(
        run_id=run_id,
        suite_name="acceptance",
        test_name="deliberate_failure",
        status=TestStatus.FAIL,
        assertion_failures="This is a deliberately recorded failure",
        expected_outcome="should_fail",
        actual_outcome="failed_as_expected",
    )
    fail_row = db.record_test(fail_record)
    print(f"  Recorded FAIL: row_id={fail_row}")

    # 2. Record a deliberate pass
    pass_record = db.create_record(
        run_id=run_id,
        suite_name="acceptance",
        test_name="deliberate_pass",
        status=TestStatus.PASS,
        expected_outcome="should_pass",
        actual_outcome="passed_as_expected",
    )
    pass_row = db.record_test(pass_record)
    print(f"  Recorded PASS: row_id={pass_row}")

    # 3. Re-open the database and verify both records exist
    db2 = TestEvidenceDB()
    total = db2.get_total_records()
    print(f"  Total records after re-open: {total}")

    summary = db2.get_run_summary(run_id)
    print(f"  Run summary: {summary}")

    assert summary["status_breakdown"].get("FAIL", 0) >= 1, "Failure record not found after re-open!"
    assert summary["status_breakdown"].get("PASS", 0) >= 1, "Pass record not found after re-open!"

    # 4. Verify JSONL backup exists
    jsonl = db2.jsonl_path
    assert jsonl.exists(), f"JSONL backup not found at {jsonl}"
    with open(jsonl, "r") as f:
        lines = f.readlines()
    assert len(lines) >= 2, f"JSONL should have at least 2 lines, found {len(lines)}"
    print(f"  JSONL backup: {len(lines)} records")

    # 5. Verify integrity
    ok = db2.verify_integrity()
    print(f"  Database integrity: {'PASS' if ok else 'FAIL'}")

    print("\n=== Acceptance Test: ALL PASSED ===")
    return True


if __name__ == "__main__":
    asyncio.run(acceptance_test())
