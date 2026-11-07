"""benchmarks/deep_research_efficiency_benchmark.py

Empirical evaluation of Deep Research Engine efficiency:
1. Research execution latency across phases and modes.
2. Token efficiency, context compression, and passage utilization.
3. Source reuse, overlap, and URL deduplication across search hops.
4. Redundant query detection and query plan decomposition analysis.
5. Early stopping condition evaluation and bounded execution guarantees.
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import tiktoken

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_engine import build_rule_based_plan, plan_query_fast
from research_engine import DeepResearchEngine, ResearchJob, ResearchJobStatus
from schemas import ChunkResult, ResearchResponse, SourceItem, UnifiedResponse


# Tokenizers for precise token measurement
enc_o200k = tiktoken.get_encoding("o200k_base")
enc_cl100k = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> dict[str, int]:
    if not text:
        return {"o200k": 0, "cl100k": 0}
    return {
        "o200k": len(enc_o200k.encode(text, disallowed_special=())),
        "cl100k": len(enc_cl100k.encode(text, disallowed_special=())),
    }


class ControlledMockSearchPipeline:
    """Mock search pipeline with deterministic source overlap, latency, and corpus control."""

    def __init__(
        self,
        sources_per_query: int = 3,
        chunks_per_source: int = 3,
        overlap_probability: float = 0.5,
        simulated_latency_s: float = 0.05,
    ):
        self.sources_per_query = sources_per_query
        self.chunks_per_source = chunks_per_source
        self.overlap_probability = overlap_probability
        self.simulated_latency_s = simulated_latency_s
        self.call_history: list[dict[str, Any]] = []

    async def search(
        self,
        query: str,
        search_depth: str = "basic",
        max_results: int = 3,
        chunks_per_source: int = 3,
        include_domains: list[str] | None = None,
    ) -> UnifiedResponse:
        t0 = time.perf_counter()
        if self.simulated_latency_s > 0:
            await asyncio.sleep(self.simulated_latency_s)

        results: list[SourceItem] = []
        # Generate sources. Some URLs are shared across queries based on domain keywords
        for i in range(max_results):
            # Deterministic pseudo-overlap:
            # If i == 0, use a shared common authority URL for this topic
            query_slug = query.lower().replace(" ", "_")[:30]
            if i == 0:
                url = "https://en.wikipedia.org/wiki/Artificial_intelligence_architecture"
                title = "AI Architecture Reference - Wikipedia"
            elif i == 1 and "comparison" in query.lower():
                url = "https://techbenchmarks.org/ai-agent-frameworks-benchmark"
                title = "AI Agent Frameworks Benchmark Review"
            else:
                url = f"https://source-{i}.example.org/docs/{query_slug}"
                title = f"Verified Source {i} for {query[:25]}"

            chunks = [
                ChunkResult(
                    content=(
                        f"Detailed analysis on {query} (Section {c+1}): "
                        f"Empirical evaluations demonstrate that multi-agent systems and tiered retrieval "
                        f"optimize throughput and latency while bounding token expenditure to under 1500 tokens. "
                        f"Corroborated by independent benchmarks on 2026 systems."
                    ),
                    score=0.95 - (i * 0.05) - (c * 0.02),
                )
                for c in range(chunks_per_source)
            ]
            source_content = "\n\n".join(c.content for c in chunks)
            results.append(
                SourceItem(
                    url=url,
                    title=title,
                    score=0.95 - (i * 0.05),
                    content=source_content,
                    chunks=chunks,
                )
            )

        dur = time.perf_counter() - t0
        self.call_history.append({"query": query, "depth": search_depth, "results_count": len(results), "latency_s": dur})
        return UnifiedResponse(
            query=query,
            answer=f"Synthesized preliminary answer for {query}",
            results=results,
            source_engine="local_live",
            response_time=dur,
        )


async def run_latency_and_hop_benchmarks():
    """Benchmark 1: Measure research execution latency, hops, and source counts across query archetypes and modes."""
    test_queries = [
        ("AI Agent Architectures 2026", "general_factual"),
        ("uv vs pip package manager python", "comparison"),
        ("how to fix ConnectionResetError 104 in asyncio aiohttp", "technical_troubleshooting"),
        ("Transformer attention multi-head scaling law compute efficiency", "academic_research"),
        ("   ", "empty_edge_case"),
    ]

    results = []

    for prompt, category in test_queries:
        for mode in ("mini", "pro"):
            mock_pipe = ControlledMockSearchPipeline(simulated_latency_s=0.03)
            engine = DeepResearchEngine(search_pipeline=mock_pipe)

            t0 = time.perf_counter()
            resp = await engine.conduct_research(prompt, mode=mode)
            total_wall_s = round(time.perf_counter() - t0, 4)

            # Analyze query decomposition
            plan = await plan_query_fast(prompt)
            sub_queries_planned = len(resp.sub_queries)

            # Token measurements
            prompt_tokens = count_tokens(prompt)["o200k"]
            answer_tokens = count_tokens(resp.answer)["o200k"]

            total_retrieved_tokens = 0
            cited_chunk_tokens = 0
            for s in resp.sources:
                total_retrieved_tokens += count_tokens(s.content)["o200k"]
                for c in s.chunks[:2]:
                    cited_chunk_tokens += count_tokens(c.content)["o200k"]

            compression_ratio = round(total_retrieved_tokens / max(1, answer_tokens), 2)
            utilization_pct = round((cited_chunk_tokens / max(1, total_retrieved_tokens)) * 100, 1)

            results.append({
                "prompt": prompt.strip() or "[EMPTY]",
                "category": category,
                "mode": mode,
                "sub_queries_count": sub_queries_planned,
                "sub_queries": resp.sub_queries,
                "sources_retrieved_count": len(resp.sources),
                "search_calls_dispatched": len(mock_pipe.call_history),
                "total_wall_latency_s": total_wall_s,
                "engine_response_time_s": resp.response_time,
                "prompt_tokens_o200k": prompt_tokens,
                "retrieved_tokens_o200k": total_retrieved_tokens,
                "answer_tokens_o200k": answer_tokens,
                "compression_ratio": compression_ratio,
                "passage_utilization_pct": utilization_pct,
            })

    return results


async def run_source_reuse_and_deduplication_analysis():
    """Benchmark 2: Measure source reuse, Jaccard overlap, and deduplication across hops."""
    prompts = [
        "uv vs pip package manager python",
        "AI Agent Architectures 2026",
        "Transformer attention multi-head scaling law compute efficiency",
    ]

    reuse_results = []

    for prompt in prompts:
        # Create pipeline where subqueries return 3 items each with some deliberate cross-query collisions
        mock_pipe = ControlledMockSearchPipeline(simulated_latency_s=0.01)
        engine = DeepResearchEngine(search_pipeline=mock_pipe)

        job = engine.start_research_job(prompt, mode="pro")
        await job._task

        calls = mock_pipe.call_history
        total_sources_received = sum(c["results_count"] for c in calls)
        unique_sources_retained = len(job.sources)

        # Calculate duplicate sources pruned
        duplicates_pruned = total_sources_received - unique_sources_retained
        dedup_ratio = round((duplicates_pruned / max(1, total_sources_received)) * 100, 1)

        reuse_results.append({
            "prompt": prompt,
            "sub_queries": job.sub_queries,
            "total_search_hops": len(calls),
            "raw_sources_retrieved": total_sources_received,
            "deduplicated_sources_retained": unique_sources_retained,
            "duplicates_eliminated": duplicates_pruned,
            "dedup_efficiency_pct": dedup_ratio,
        })

    return reuse_results


async def run_early_stopping_and_gap_analysis():
    """Benchmark 3: Evaluate early stopping conditions and bounded execution in research_engine.py."""
    trials = []

    # Scenario A: Pro mode with abundant sources (>= 6 unique sources)
    class AbundantSearchPipeline:
        def __init__(self):
            self.calls = 0

        async def search(self, query: str, search_depth: str = "advanced", max_results: int = 3, chunks_per_source: int = 3):
            self.calls += 1
            # Return 3 unique sources per query call
            return UnifiedResponse(
                query=query,
                answer="",
                results=[
                    SourceItem(url=f"https://source-{self.calls}-{i}.org", title=f"Source {self.calls}-{i}", score=0.9, content="Evidence", chunks=[ChunkResult(content="C", score=0.9)])
                    for i in range(3)
                ],
                source_engine="local_live",
            )

    pipe_abundant = AbundantSearchPipeline()
    eng_abundant = DeepResearchEngine(search_pipeline=pipe_abundant)
    job_abundant = eng_abundant.start_research_job("AI Agent Architectures 2026", mode="pro")
    await job_abundant._task

    # In abundant case, 4 sub-queries * 3 unique sources = 12 sources >= 6.
    # Phase 3 Gap Analysis must be skipped (early stopping).
    trials.append({
        "scenario": "Pro mode with abundant sources (>= 6)",
        "expected_gap_query_triggered": False,
        "actual_gap_query_triggered": any("technical specifications benchmarks comparison" in q for q in job_abundant.sub_queries),
        "total_calls": pipe_abundant.calls,
        "early_stopping_honored": not any("technical specifications benchmarks comparison" in q for q in job_abundant.sub_queries),
        "source_count": len(job_abundant.sources),
        "bounded_source_limit": 8,
    })

    # Scenario B: Pro mode with sparse sources (< 6 unique sources)
    class SparseSearchPipeline:
        def __init__(self):
            self.calls = 0

        async def search(self, query: str, search_depth: str = "advanced", max_results: int = 3, chunks_per_source: int = 3):
            self.calls += 1
            # Returns only 1 source total across all queries
            return UnifiedResponse(
                query=query,
                answer="",
                results=[
                    SourceItem(url="https://single-domain.org/sparse", title="Sparse Source", score=0.88, content="Sparse evidence", chunks=[ChunkResult(content="C", score=0.88)])
                ],
                source_engine="local_live",
            )

    pipe_sparse = SparseSearchPipeline()
    eng_sparse = DeepResearchEngine(search_pipeline=pipe_sparse)
    job_sparse = eng_sparse.start_research_job("AI Agent Architectures 2026", mode="pro")
    await job_sparse._task

    # In sparse case, unique sources < 6, so Phase 3 Gap Query MUST be triggered.
    gap_triggered_sparse = any("technical specifications benchmarks comparison" in q for q in job_sparse.sub_queries)
    trials.append({
        "scenario": "Pro mode with sparse sources (< 6)",
        "expected_gap_query_triggered": True,
        "actual_gap_query_triggered": gap_triggered_sparse,
        "total_calls": pipe_sparse.calls,
        "early_stopping_honored": gap_triggered_sparse, # True because condition correctly detected gap
        "source_count": len(job_sparse.sources),
        "bounded_source_limit": 8,
    })

    # Scenario C: Mini mode never triggers gap analysis regardless of source count
    pipe_mini = SparseSearchPipeline()
    eng_mini = DeepResearchEngine(search_pipeline=pipe_mini)
    job_mini = eng_mini.start_research_job("AI Agent Architectures 2026", mode="mini")
    await job_mini._task

    gap_triggered_mini = any("technical specifications benchmarks comparison" in q for q in job_mini.sub_queries)
    trials.append({
        "scenario": "Mini mode with sparse sources (< 6)",
        "expected_gap_query_triggered": False,
        "actual_gap_query_triggered": gap_triggered_mini,
        "total_calls": pipe_mini.calls,
        "early_stopping_honored": not gap_triggered_mini,
        "source_count": len(job_mini.sources),
        "bounded_source_limit": 5,
    })

    # Scenario D: Job Cancellation early stopping
    pipe_cancel = ControlledMockSearchPipeline(simulated_latency_s=0.2)
    eng_cancel = DeepResearchEngine(search_pipeline=pipe_cancel)
    job_cancel = eng_cancel.start_research_job("Complex Cancellation Test", mode="pro")
    # Cancel immediately
    cancelled = eng_cancel.cancel_research_job(job_cancel.job_id)
    await asyncio.sleep(0.05)
    trials.append({
        "scenario": "Immediate Job Cancellation",
        "cancellation_succeeded": cancelled,
        "job_status": job_cancel.status.value,
        "progress_step": job_cancel.progress_step,
        "bounded_exit_verified": job_cancel.status == ResearchJobStatus.CANCELLED,
    })

    return trials


async def run_redundant_query_analysis():
    """Benchmark 4: Evaluate query decomposition redundancy and lexical overlap."""
    queries = [
        "AI Agent Architectures 2026",
        "uv vs pip package manager python",
        "how to fix ConnectionResetError 104 in asyncio aiohttp",
        "quantum computing error correction surface code",
        "what is the difference between synchronous and asynchronous python",
        "best practices for distributed caching redis",
    ]

    analysis = []
    for q in queries:
        rule_plan = build_rule_based_plan(q)
        primary = rule_plan.primary_keyword_query
        semantic = rule_plan.semantic_expansion_query
        sub_qs = rule_plan.sub_queries

        # Redundancy checks:
        primary_equals_semantic = (primary.lower().strip() == semantic.lower().strip())
        
        # Sub-query set deduplicated by dict.fromkeys as in research_engine.py
        merged = [primary, semantic]
        merged.extend(sub_qs)
        deduped = list(dict.fromkeys(merged))

        # Check word overlap across sub_queries
        word_sets = [set(re_sub.lower().split()) for re_sub in deduped]
        common_words = set.intersection(*word_sets) if word_sets else set()

        analysis.append({
            "raw_query": q,
            "primary": primary,
            "semantic": semantic,
            "primary_equals_semantic": primary_equals_semantic,
            "initial_sub_queries_count": len(merged),
            "deduped_sub_queries_count": len(deduped),
            "mini_hops_count": min(2, len(deduped)),
            "pro_hops_count": min(4, len(deduped)),
            "common_intersecting_tokens": list(common_words),
            "redundancy_flag": primary_equals_semantic,
        })

    return analysis


async def main():
    print("Executing Deep Research Efficiency Benchmarks...")
    t_start = time.perf_counter()

    latencies = await run_latency_and_hop_benchmarks()
    print(f"Latency & Token Benchmarks finished ({len(latencies)} cases).")

    source_reuse = await run_source_reuse_and_deduplication_analysis()
    print(f"Source Reuse Benchmarks finished ({len(source_reuse)} cases).")

    early_stopping = await run_early_stopping_and_gap_analysis()
    print(f"Early Stopping Benchmarks finished ({len(early_stopping)} trials).")

    redundancy = await run_redundant_query_analysis()
    print(f"Redundant Query Analysis finished ({len(redundancy)} queries).")

    total_time = round(time.perf_counter() - t_start, 3)

    benchmark_bundle = {
        "timestamp": time.time(),
        "total_benchmark_duration_s": total_time,
        "latency_and_tokens": latencies,
        "source_reuse": source_reuse,
        "early_stopping": early_stopping,
        "redundant_queries": redundancy,
    }

    out_file = ROOT / "benchmarks" / "deep_research_efficiency_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(benchmark_bundle, f, indent=2)

    print(f"Results written to {out_file} in {total_time}s.")


if __name__ == "__main__":
    asyncio.run(main())
