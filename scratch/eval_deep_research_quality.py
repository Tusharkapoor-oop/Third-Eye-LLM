"""Empirical evaluation of Deep Research Quality components:
1. Multi-hop query decomposition (2-4 hops) across query types.
2. Gap analysis mechanics and coverage enhancement.
3. Cross-source evidence synthesis and citation structure.
4. Asynchronous lifecycle and cancellation behavior.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

# Engine 1: Root research_engine.py
from research_engine import DeepResearchEngine as V14DeepResearchEngine, ResearchJobStatus
from query_engine import build_rule_based_plan, plan_query_fast
from schemas import UnifiedResponse, SourceItem, ChunkResult

# Engine 2: src/engine/research/deep_research.py
from src.engine.research.deep_research import (
    DeepResearchEngine as V13DeepResearchEngine,
    generate_sub_queries,
    _first_prose_sentence,
    SourcedFact,
    ResearchReport,
)

# Engine 3: src/weblens/research/engine.py
from src.weblens.research.engine import decompose as weblens_decompose

async def evaluate_query_decomposition():
    test_queries = [
        "Compare uv vs pip dependency resolution and lockfile caching",
        "How to configure Playwright Chromium in headless Docker container",
        "SMR small modular nuclear reactor commercial deployment timeline 2026",
        "PostgreSQL 17 query plan optimizer improvements vs MySQL 8.4",
        "What are the latency tradeoffs of hybrid BM25 and vector retrieval?"
    ]

    print("=== 1. QUERY DECOMPOSITION EVALUATION ===")
    results = {}
    for q in test_queries:
        # 1.1 query_engine / V14 planner
        plan = build_rule_based_plan(q)
        v14_mini_hops = [plan.primary_keyword_query, plan.semantic_expansion_query]
        v14_mini_hops.extend(plan.sub_queries)
        v14_mini_hops = list(dict.fromkeys(v14_mini_hops))[:2]

        v14_pro_hops = [plan.primary_keyword_query, plan.semantic_expansion_query]
        v14_pro_hops.extend(plan.sub_queries)
        v14_pro_hops = list(dict.fromkeys(v14_pro_hops))[:4]

        # 1.2 deep_research.py generate_sub_queries
        v13_sub_queries = generate_sub_queries(q)

        # 1.3 weblens decompose
        weblens_subs = weblens_decompose(q)

        results[q] = {
            "v14_mini_hops": v14_mini_hops,
            "v14_mini_count": len(v14_mini_hops),
            "v14_pro_hops": v14_pro_hops,
            "v14_pro_count": len(v14_pro_hops),
            "v13_sub_queries": v13_sub_queries,
            "v13_count": len(v13_sub_queries),
            "weblens_subs": weblens_subs,
            "weblens_count": len(weblens_subs),
        }
        print(f"\nQuery: {q}")
        print(f"  V14 Mini ({len(v14_mini_hops)} hops): {v14_mini_hops}")
        print(f"  V14 Pro  ({len(v14_pro_hops)} hops): {v14_pro_hops}")
        print(f"  V13 Subs ({len(v13_sub_queries)} hops): {v13_sub_queries}")
        print(f"  WebLens  ({len(weblens_subs)} hops): {weblens_subs}")

    return results

async def evaluate_gap_analysis():
    print("\n=== 2. GAP ANALYSIS EVALUATION ===")
    # Simulate SearchPipeline for V14 DeepResearchEngine
    class MockGapSearchPipeline:
        def __init__(self, initial_sources_count=3):
            self.initial_sources_count = initial_sources_count
            self.search_calls = []

        async def search(self, query: str, search_depth: str = "basic", max_results: int = 3, chunks_per_source: int = 3):
            self.search_calls.append({"query": query, "depth": search_depth})
            if "technical specifications benchmarks comparison" in query:
                # Gap query return
                return UnifiedResponse(
                    query=query,
                    answer="Gap evidence found",
                    results=[
                        SourceItem(
                            url=f"https://benchmark.org/gap-{i}",
                            title=f"Benchmark Specification Source {i}",
                            score=0.95,
                            content=f"Detailed technical benchmark finding {i}",
                            chunks=[ChunkResult(content=f"Benchmark spec {i}", score=0.95)]
                        )
                        for i in range(3)
                    ],
                    source_engine="local_live"
                )
            else:
                return UnifiedResponse(
                    query=query,
                    answer="Standard evidence",
                    results=[
                        SourceItem(
                            url=f"https://docs.org/standard-{hash(query) % 1000}-{i}",
                            title=f"Documentation Standard {i}",
                            score=0.88,
                            content=f"Standard finding {i} for {query}",
                            chunks=[ChunkResult(content=f"Standard chunk {i}", score=0.88)]
                        )
                        for i in range(1)
                    ],
                    source_engine="local_live"
                )

    # Test Pro Mode with sparse results (<6 sources)
    sparse_pipeline = MockGapSearchPipeline(initial_sources_count=3)
    engine_pro = V14DeepResearchEngine(search_pipeline=sparse_pipeline)
    t0 = time.perf_counter()
    resp_pro = await engine_pro.conduct_research("Next-Gen Vector Database Benchmarks", mode="pro")
    elapsed_pro = time.perf_counter() - t0

    print(f"Pro Mode (sparse): total sources={len(resp_pro.sources)}, sub_queries={len(resp_pro.sub_queries)}, time={elapsed_pro:.4f}s")
    print(f"Sub-queries invoked ({len(resp_pro.sub_queries)}):")
    for sq in resp_pro.sub_queries:
        print(f"  - {sq}")

    # Test Mini Mode (no gap analysis phase)
    sparse_pipeline_mini = MockGapSearchPipeline(initial_sources_count=3)
    engine_mini = V14DeepResearchEngine(search_pipeline=sparse_pipeline_mini)
    resp_mini = await engine_mini.conduct_research("Next-Gen Vector Database Benchmarks", mode="mini")
    print(f"Mini Mode: total sources={len(resp_mini.sources)}, sub_queries={len(resp_mini.sub_queries)}")
    for sq in resp_mini.sub_queries:
        print(f"  - {sq}")

    gap_analysis_data = {
        "pro_sources_count": len(resp_pro.sources),
        "pro_sub_queries": resp_pro.sub_queries,
        "pro_search_calls_count": len(sparse_pipeline.search_calls),
        "mini_sources_count": len(resp_mini.sources),
        "mini_sub_queries": resp_mini.sub_queries,
        "mini_search_calls_count": len(sparse_pipeline_mini.search_calls),
    }
    return gap_analysis_data

async def evaluate_synthesis_and_citations():
    print("\n=== 3. SYNTHESIS AND CITATIONS EVALUATION ===")
    # Check synthesis output structure
    mock_pipeline = None
    engine = V14DeepResearchEngine()
    test_sources = [
        SourceItem(
            url="https://docs.astral.sh/uv/concepts/resolution",
            title="UV Dependency Resolution Architecture",
            score=0.96,
            content="uv uses PubGrub algorithm with aggressive hardlink caching to resolve dependencies in milliseconds.",
            chunks=[
                ChunkResult(content="uv uses PubGrub algorithm with aggressive hardlink caching.", score=0.96),
                ChunkResult(content="Resolves dependencies 10-100x faster than standard pip.", score=0.94)
            ]
        ),
        SourceItem(
            url="https://pip.pypa.io/en/stable/topics/dependency-resolution",
            title="Pip Dependency Resolution",
            score=0.91,
            content="pip uses Resolvelib backtracking resolver to find consistent dependency sets across wheel indexes.",
            chunks=[
                ChunkResult(content="pip uses Resolvelib backtracking resolver.", score=0.91)
            ]
        )
    ]

    report = await engine._synthesize_report(
        prompt="Compare uv vs pip dependency resolution",
        sources=test_sources,
        sub_queries=["uv vs pip", "uv resolution", "pip resolvelib"],
        mode="pro"
    )

    print("Synthesis Report Sample:\n" + report)
    has_executive_summary = "## Executive Summary" in report
    has_key_findings = "## Key Findings & Verified Evidence" in report
    has_citations_table = "## Evidence Summary & Citations Table" in report
    has_markdown_links = "[UV Dependency Resolution Architecture](https://docs.astral.sh/uv/concepts/resolution)" in report
    has_blockquotes = "> uv uses PubGrub" in report

    # Test V13 prose sentence extractor
    v13_passage = "# Markdown Heading\n![Img](pic.png)\nuv uses PubGrub algorithm with aggressive hardlink caching to achieve sub-second speeds. Second sentence."
    v13_first_sent = _first_prose_sentence(v13_passage)
    print(f"\nV13 Prose Extraction Test: '{v13_first_sent}'")

    synthesis_data = {
        "has_executive_summary": has_executive_summary,
        "has_key_findings": has_key_findings,
        "has_citations_table": has_citations_table,
        "has_markdown_links": has_markdown_links,
        "has_blockquotes": has_blockquotes,
        "v13_prose_extracted": v13_first_sent,
        "report_length_chars": len(report),
        "report_length_lines": len(report.splitlines()),
    }
    return synthesis_data

async def evaluate_lifecycle_and_cancellation():
    print("\n=== 4. ASYNC LIFECYCLE AND CANCELLATION EVALUATION ===")
    class SlowSearchPipeline:
        async def search(self, query: str, search_depth: str = "basic", max_results: int = 3, chunks_per_source: int = 3):
            await asyncio.sleep(0.5)
            return UnifiedResponse(
                query=query,
                answer="done",
                results=[SourceItem(url=f"https://slow.org/{query}", title="Slow", score=0.9, content="slow", chunks=[])],
                source_engine="mock"
            )

    engine = V14DeepResearchEngine(search_pipeline=SlowSearchPipeline())
    job = engine.start_research_job("Long-running async query", mode="pro")
    print(f"Job launched: id={job.job_id}, status={job.status}, step={job.progress_step}")
    assert job.status in (ResearchJobStatus.CREATED, ResearchJobStatus.RUNNING)

    # Cancel job after brief delay
    await asyncio.sleep(0.05)
    cancelled = engine.cancel_research_job(job.job_id)
    print(f"Cancelled: {cancelled}, status={job.status}, step={job.progress_step}")

    try:
        await job._task
    except asyncio.CancelledError:
        print("asyncio.CancelledError correctly caught and handled.")

    lifecycle_data = {
        "job_id": job.job_id,
        "initial_status": "CREATED/RUNNING",
        "cancelled_status": str(job.status),
        "cancelled_step": job.progress_step,
        "cancelled_result": cancelled,
    }
    return lifecycle_data

async def main():
    decomp = await evaluate_query_decomposition()
    gap = await evaluate_gap_analysis()
    synth = await evaluate_synthesis_and_citations()
    life = await evaluate_lifecycle_and_cancellation()

    output = {
        "decomposition": decomp,
        "gap_analysis": gap,
        "synthesis": synth,
        "lifecycle": life,
    }
    out_path = Path("cache/eval_deep_research_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nEmpirical evaluation results written to {out_path}")

if __name__ == "__main__":
    asyncio.run(main())
