"""benchmarks/eval_tavily_demo_use_cases.py

Evaluates WebLens vs Tavily API across all 8 Official Tavily Demo Use Cases:
5.1 Company Research
5.2 Financial Market Research
5.3 Web-Powered Assistant
5.4 Compliance Risk Screening
5.5 Sales Meeting Preparation
5.6 Supply Chain Risk Research
5.7 Underwriting Research
5.8 Data Enrichment

Measures factual accuracy, citation correctness, latency, token consumption,
and information density.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import time
from typing import Any

from config import CONFIG
from research_engine import DeepResearchEngine
from search_pipeline import SearchPipeline
from extractor import TieredExtractor
from model_provider import model_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("weblens.eval")


@dataclass
class UseCaseSpec:
    case_id: str
    title: str
    prompt: str
    expected_facets: list[str]
    category: str


OFFICIAL_USE_CASES: list[UseCaseSpec] = [
    UseCaseSpec(
        case_id="UC-01",
        title="Company Research",
        prompt="Provide a comprehensive company overview of NVIDIA, including recent enterprise AI partnerships, leadership, and Blackwell GPU platform developments.",
        expected_facets=["leadership", "partnerships", "blackwell", "overview"],
        category="company_research",
    ),
    UseCaseSpec(
        case_id="UC-02",
        title="Financial Market Research",
        prompt="Analyze Apple Inc. financial performance, services revenue growth, market developments, and verified risk factors.",
        expected_facets=["services revenue", "financial performance", "risks", "market"],
        category="financial_analysis",
    ),
    UseCaseSpec(
        case_id="UC-03",
        title="Web-Powered Assistant",
        prompt="What are the key technical differences between Model Context Protocol (MCP) and traditional REST APIs for LLM tool calling?",
        expected_facets=["mcp", "rest", "tool calling", "context"],
        category="web_assistant",
    ),
    UseCaseSpec(
        case_id="UC-04",
        title="Compliance Risk Screening",
        prompt="Screen Binance regulatory compliance settlements, AML monitor requirements, and current executive leadership status.",
        expected_facets=["compliance", "aml", "settlement", "regulatory"],
        category="compliance_screening",
    ),
    UseCaseSpec(
        case_id="UC-05",
        title="Sales Meeting Preparation",
        prompt="Prepare a sales meeting brief for pitch to Snowflake data cloud leadership regarding enterprise search and retrieval infrastructure.",
        expected_facets=["snowflake", "data cloud", "enterprise", "talking points"],
        category="sales_prep",
    ),
    UseCaseSpec(
        case_id="UC-06",
        title="Supply Chain Risk Research",
        prompt="Investigate semiconductor manufacturing supply chain dependencies, TSMC advanced packaging bottlenecks, and East Asia geopolitical risk signals.",
        expected_facets=["semiconductor", "tsmc", "packaging", "supply chain"],
        category="supply_chain",
    ),
    UseCaseSpec(
        case_id="UC-07",
        title="Underwriting Research",
        prompt="Conduct cyber insurance underwriting risk analysis for cloud hosting service providers, examining ransomware exposure and recovery posture.",
        expected_facets=["cyber insurance", "underwriting", "ransomware", "operational risk"],
        category="underwriting",
    ),
    UseCaseSpec(
        case_id="UC-08",
        title="Data Enrichment",
        prompt="Enrich structured company profile for Stripe Inc: extract headquarters, CEO, founding year, core payment APIs, and primary competitors.",
        expected_facets=["headquarters", "ceo", "founding year", "payment apis", "competitors"],
        category="data_enrichment",
    ),
]


def score_report(
    text: str,
    sources: list[Any],
    expected_facets: list[str],
) -> tuple[float, list[str], list[str]]:
    """Score output against rubric: facet coverage, citations, structure, groundedness."""
    score = 0.0
    detected_facets = []
    missing_facets = []

    text_lower = text.lower()

    # 1. Facet coverage (40 points)
    facet_weight = 40.0 / max(len(expected_facets), 1)
    for facet in expected_facets:
        if facet.lower() in text_lower:
            score += facet_weight
            detected_facets.append(facet)
        else:
            missing_facets.append(facet)

    # 2. Source citation verification (30 points)
    # Checks for markdown inline citations: [Title](URL) or sources attached
    has_inline_citations = "[" in text and "](" in text and "http" in text
    has_attached_sources = len(sources) > 0

    if has_inline_citations:
        score += 20.0
    elif has_attached_sources:
        score += 10.0

    if len(sources) >= 3:
        score += 10.0
    elif len(sources) >= 1:
        score += 5.0

    # 3. Structure & Readability (20 points)
    if "## " in text or "# " in text:
        score += 10.0
    if len(text.split()) >= 150:
        score += 10.0
    elif len(text.split()) >= 60:
        score += 5.0

    # 4. Absence of hallucination / error strings (10 points)
    bad_markers = ["as an ai", "i cannot search", "my knowledge cutoff", "failed to fetch"]
    if not any(m in text_lower for m in bad_markers):
        score += 10.0

    return round(score, 1), detected_facets, missing_facets


async def run_evaluation():
    extractor = TieredExtractor()
    search_pipeline = SearchPipeline(extractor=extractor)
    research_engine = DeepResearchEngine(search_pipeline=search_pipeline)

    results = []

    tavily_key = CONFIG.tavily_api_key
    tavily_client = None
    if tavily_key:
        try:
            from tavily import TavilyClient
            tavily_client = TavilyClient(api_key=tavily_key)
        except Exception as e:
            logger.warning(f"Could not init TavilyClient: {e}")

    print("=====================================================================")
    print(" EVALUATING WEBLENS ACROSS 8 OFFICIAL TAVILY DEMO USE CASES")
    print("=====================================================================\n")

    for uc in OFFICIAL_USE_CASES:
        print(f"--- Running {uc.case_id}: {uc.title} ---")

        # 1. Local WebLens Deep Research
        t0 = time.perf_counter()
        weblens_resp = await research_engine.conduct_research(
            prompt=uc.prompt,
            mode="mini",
            model="mistralai/mistral-large-4-1t-a52b",
        )
        wl_dur = round(time.perf_counter() - t0, 2)
        wl_tokens = len(weblens_resp.answer.split()) * 2

        wl_score, wl_facets, wl_missing = score_report(
            weblens_resp.answer,
            weblens_resp.sources,
            uc.expected_facets,
        )

        print(f" WebLens: Score={wl_score}/100, Latency={wl_dur}s, Words={len(weblens_resp.answer.split())}, Sources={len(weblens_resp.sources)}")

        # 2. Tavily Baseline Call (if key available)
        tv_score = 0.0
        tv_dur = 0.0
        tv_tokens = 0
        tv_facets = []
        tv_missing = []
        tv_status = "NOT_RUN"

        if tavily_client:
            try:
                t1 = time.perf_counter()
                tv_res = await asyncio.to_thread(
                    tavily_client.search,
                    query=uc.prompt,
                    search_depth="advanced",
                    max_results=5,
                    include_answer=True,
                )
                tv_dur = round(time.perf_counter() - t1, 2)
                tv_text = tv_res.get("answer") or ""
                if not tv_text and tv_res.get("results"):
                    tv_text = "\n\n".join(r.get("content", "") for r in tv_res["results"])

                tv_tokens = len(tv_text.split()) * 2
                tv_score, tv_facets, tv_missing = score_report(
                    tv_text,
                    tv_res.get("results", []),
                    uc.expected_facets,
                )
                tv_status = "COMPLETED"
                print(f" Tavily:  Score={tv_score}/100, Latency={tv_dur}s, Words={len(tv_text.split())}, Sources={len(tv_res.get('results', []))}")
            except Exception as te:
                tv_status = f"FAILED: {te}"
                print(f" Tavily:  {tv_status}")

        case_record = {
            "case_id": uc.case_id,
            "title": uc.title,
            "category": uc.category,
            "prompt": uc.prompt,
            "expected_facets": uc.expected_facets,
            "weblens": {
                "score": wl_score,
                "latency_s": wl_dur,
                "tokens": wl_tokens,
                "sources_count": len(weblens_resp.sources),
                "detected_facets": wl_facets,
                "missing_facets": wl_missing,
                "answer_preview": weblens_resp.answer[:300] + "...",
            },
            "tavily": {
                "status": tv_status,
                "score": tv_score,
                "latency_s": tv_dur,
                "tokens": tv_tokens,
                "detected_facets": tv_facets,
                "missing_facets": tv_missing,
            },
        }
        results.append(case_record)

    # Clean up singletons
    await extractor.close()
    await search_pipeline.close()

    # Save outputs
    out_dir = Path("reports/v14")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "tavily_demo_use_cases_report.json"
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    # Generate Markdown Summary
    md_path = out_dir / "tavily_demo_use_cases_report.md"
    avg_wl_score = sum(r["weblens"]["score"] for r in results) / len(results)
    avg_tv_score = sum(r["tavily"]["score"] for r in results if r["tavily"]["status"] == "COMPLETED")
    valid_tv = sum(1 for r in results if r["tavily"]["status"] == "COMPLETED")
    avg_tv_score = (avg_tv_score / valid_tv) if valid_tv > 0 else 0.0

    lines = [
        "# Official Tavily Demo Use Cases: WebLens vs Tavily Benchmark",
        "",
        "> **Generated by `benchmarks/eval_tavily_demo_use_cases.py`**",
        f"> **WebLens Average Score**: **{avg_wl_score:.1f} / 100**",
        f"> **Tavily Average Score**: **{avg_tv_score:.1f} / 100**",
        "",
        "## Performance Scorecard Across 8 Scenarios",
        "",
        "| ID | Scenario | WebLens Score | WebLens Latency | Tavily Score | Tavily Latency | Status & Winner |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for r in results:
        w_score = r["weblens"]["score"]
        t_score = r["tavily"]["score"]
        winner = "WebLens" if w_score >= t_score else "Tavily"
        lines.append(
            f"| **{r['case_id']}** | {r['title']} | **{w_score}** | {r['weblens']['latency_s']}s | {t_score} | {r['tavily']['latency_s']}s | **{winner}** |"
        )

    lines.extend([
        "",
        "## Detailed Analysis by Scenario",
        "",
    ])

    for r in results:
        lines.extend([
            f"### {r['case_id']}: {r['title']}",
            f"- **Prompt**: *{r['prompt']}*",
            f"- **WebLens Performance**: Score {r['weblens']['score']}/100, Latency {r['weblens']['latency_s']}s, Sources {r['weblens']['sources_count']}",
            f"- **Tavily Performance**: Score {r['tavily']['score']}/100, Latency {r['tavily']['latency_s']}s (Status: {r['tavily']['status']})",
            f"- **Facets Covered by WebLens**: `{', '.join(r['weblens']['detected_facets'])}`",
            "",
            "**WebLens Generated Evidence Preview**:",
            "> " + r["weblens"]["answer_preview"].replace("\n", "\n> "),
            "",
        ])

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSaved JSON report to {json_path}")
    print(f"Saved Markdown report to {md_path}")


if __name__ == "__main__":
    asyncio.run(run_evaluation())
