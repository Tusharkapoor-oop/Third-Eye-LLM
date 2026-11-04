"""Run the eight official Tavily demo use cases through real WebLens and Tavily.

WebLens is exercised through its real local MCP server, using `deep_research`
for the six research-shaped cases and the app tools where the case maps to one
(company research, market research, sheets enrichment, meeting prep). Tavily is
exercised through its real `/search` endpoint as a retrieval baseline: the demo
use cases are Tavily *search* demos, but Tavily returns snippets, not a
synthesized report, so comparing facet coverage is intentionally conservative
for Tavily and is labelled as retrieval-only.

No results are merged. Every record carries its own provider, latency, tokens,
credits, status, evidence URLs, and facet checks.

Run:
    python weblens-lab/evaluations/run_tavily_use_cases_v10.py
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import tiktoken

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "weblens-lab"))

from adapters.local_mcp_adapter.adapter import LocalMCPAdapter  # noqa: E402
from adapters.tavily_adapter.adapter import TavilyAdapter  # noqa: E402

OUT = ROOT / "reports" / "tavily-use-cases-v10"

USE_CASES: list[dict[str, Any]] = [
    {
        "id": "UC-01",
        "title": "Company Research",
        "tool": "company_research",
        "args": {"company": "NVIDIA"},
        "prompt": "Provide a comprehensive company overview of NVIDIA, including recent enterprise AI partnerships, leadership, and Blackwell GPU platform developments.",
        "facets": ["leadership", "partnership", "blackwell", "overview"],
    },
    {
        "id": "UC-02",
        "title": "Financial Market Research",
        "tool": "market_research",
        "args": {"asset": "AAPL", "question": "Apple Inc financial performance, services revenue growth, market developments, and verified risk factors"},
        "prompt": "Analyze Apple Inc. financial performance, services revenue growth, market developments, and verified risk factors.",
        "facets": ["services revenue", "financial", "risk", "market"],
    },
    {
        "id": "UC-03",
        "title": "Web-Powered Assistant",
        "tool": "deep_research",
        "args": {"query": "key technical differences between Model Context Protocol and traditional REST APIs for LLM tool calling", "max_tokens": 1800},
        "prompt": "What are the key technical differences between Model Context Protocol (MCP) and traditional REST APIs for LLM tool calling?",
        "facets": ["mcp", "rest", "tool calling", "context"],
    },
    {
        "id": "UC-04",
        "title": "Compliance Risk Screening",
        "tool": "deep_research",
        "args": {"query": "Binance regulatory compliance settlements AML monitor requirements executive leadership status", "max_tokens": 1800},
        "prompt": "Screen Binance regulatory compliance settlements, AML monitor requirements, and current executive leadership status.",
        "facets": ["compliance", "aml", "settlement", "regulatory"],
    },
    {
        "id": "UC-05",
        "title": "Sales Meeting Preparation",
        "tool": "meeting_prep",
        "args": {"meeting_title": "Snowflake enterprise search and retrieval infrastructure pitch", "attendees": ["Snowflake data cloud leadership"], "company_or_org": "Snowflake"},
        "prompt": "Prepare a sales meeting brief for pitch to Snowflake data cloud leadership regarding enterprise search and retrieval infrastructure.",
        "facets": ["snowflake", "data cloud", "enterprise", "talking points"],
    },
    {
        "id": "UC-06",
        "title": "Supply Chain Risk Research",
        "tool": "deep_research",
        "args": {"query": "semiconductor manufacturing supply chain dependencies TSMC advanced packaging bottlenecks East Asia geopolitical risk", "max_tokens": 1800},
        "prompt": "Investigate semiconductor manufacturing supply chain dependencies, TSMC advanced packaging bottlenecks, and East Asia geopolitical risk signals.",
        "facets": ["semiconductor", "tsmc", "packaging", "supply chain"],
    },
    {
        "id": "UC-07",
        "title": "Underwriting Research",
        "tool": "deep_research",
        "args": {"query": "cyber insurance underwriting risk analysis cloud hosting ransomware exposure recovery posture", "max_tokens": 1800},
        "prompt": "Conduct cyber insurance underwriting risk analysis for cloud hosting service providers, examining ransomware exposure and recovery posture.",
        "facets": ["cyber insurance", "underwriting", "ransomware", "operational risk"],
    },
    {
        "id": "UC-08",
        "title": "Data Enrichment",
        "tool": "sheets_enrich",
        "args": {
            "rows": [{"company": "Stripe Inc"}],
            "column_prompts": {
                "headquarters": "Stripe Inc headquarters",
                "ceo": "Stripe Inc CEO",
                "founding_year": "Stripe Inc founding year",
                "payment_apis": "Stripe payment APIs",
                "competitors": "Stripe primary competitors",
            },
        },
        "prompt": "Enrich structured company profile for Stripe Inc: extract headquarters, CEO, founding year, core payment APIs, and primary competitors.",
        "facets": ["headquarters", "ceo", "founding", "payment", "competitor"],
    },
]

_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_ENCODING = tiktoken.get_encoding("cl100k_base")
_SKIP_KEYS = {
    "query",
    "q",
    "subqueries",
    "sub_queries",
    "searched",
    "methodology",
    "status",
    "msg",
    "err",
    "sha",
    "at",
    "u",
    "url",
    "fetched_at",
    "session_id",
    "message_id",
    "role",
    "prov",
    "tok",
    "ms",
    "n",
    "gaps",
    "asset",
    "company",
    "company_or_org",
    "meeting_title",
    "attendees",
    "rows",
    "column_prompts",
    "question",
    "instructions",
    "prompt",
}


def evidence_text(value: Any, key: str = "") -> str:
    """Collect only evidence-bearing strings; never echo the query back."""
    if key.lower() in _SKIP_KEYS:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(evidence_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(evidence_text(item, k) for k, item in value.items())
    return ""


def token_count(text: str) -> int:
    return len(_ENCODING.encode(text)) if text else 0


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def facet_checks(text: str, facets: list[str]) -> dict[str, bool]:
    blob = normalize(text)
    return {facet: facet.lower() in blob for facet in facets}


def urls_in(value: Any) -> list[str]:
    return sorted(set(_URL_RE.findall(json.dumps(value, default=str))))


async def run_case(case: dict[str, Any], local: LocalMCPAdapter, tavily: TavilyAdapter) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": case["id"],
        "title": case["title"],
        "prompt": case["prompt"],
        "facets": case["facets"],
        "systems": {},
    }

    # WebLens through the real MCP tool.
    started = time.perf_counter()
    try:
        payload, meta, elapsed_ms = await local._call(case["tool"], case["args"])
        wall_ms = (time.perf_counter() - started) * 1000.0
        evidence = evidence_text(payload)
        checks = facet_checks(evidence, case["facets"])
        record["systems"]["local_weblens"] = {
            "tool": case["tool"],
            "status": payload.get("status", "ok"),
            "http_status": meta.http_status,
            "latency_ms": round(elapsed_ms, 1),
            "wall_ms": round(wall_ms, 1),
            "tokens": token_count(evidence),
            "facet_checks": checks,
            "facet_coverage": round(sum(checks.values()) / len(checks), 3),
            "evidence_urls": urls_in(payload)[:10],
            "error": payload.get("msg") if payload.get("status") == "error" else None,
        }
    except Exception as exc:
        record["systems"]["local_weblens"] = {
            "tool": case["tool"],
            "status": "error",
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 1),
            "facet_checks": {f: False for f in case["facets"]},
            "facet_coverage": 0.0,
            "evidence_urls": [],
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
        }

    # Tavily direct retrieval baseline.
    started = time.perf_counter()
    try:
        res = await tavily.search(case["prompt"], max_results=5)
        evidence = " ".join(f"{r.title} {r.content}" for r in res.results)
        checks = facet_checks(evidence, case["facets"])
        record["systems"]["tavily_direct"] = {
            "tool": "search",
            "status": res.status,
            "http_status": res.http_status,
            "latency_ms": round(res.latency_ms, 1),
            "wall_ms": round((time.perf_counter() - started) * 1000.0, 1),
            "tokens": token_count(evidence),
            "credits": res.credits_used,
            "facet_checks": checks,
            "facet_coverage": round(sum(checks.values()) / len(checks), 3),
            "evidence_urls": sorted({r.url for r in res.results if r.url})[:10],
            "error": res.error,
        }
    except Exception as exc:
        record["systems"]["tavily_direct"] = {
            "tool": "search",
            "status": "error",
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 1),
            "facet_checks": {f: False for f in case["facets"]},
            "facet_coverage": 0.0,
            "evidence_urls": [],
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
        }

    return record


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"n_cases": len(records), "systems": {}}
    for name in ("local_weblens", "tavily_direct"):
        rows = [r["systems"][name] for r in records]
        out["systems"][name] = {
            "cases": len(rows),
            "ok_cases": sum(1 for r in rows if r.get("status") in ("ok", "partial", "found", "no_reliable_result")),
            "error_cases": sum(1 for r in rows if r.get("status") == "error"),
            "mean_facet_coverage": round(sum(r.get("facet_coverage", 0.0) for r in rows) / len(rows), 3),
            "mean_latency_ms": round(sum(r.get("latency_ms", 0.0) for r in rows) / len(rows), 1),
            "mean_tokens": round(
                sum((r.get("tokens") or 0) for r in rows) / len(rows), 1
            ),
            "cases_with_evidence_urls": sum(1 for r in rows if r.get("evidence_urls")),
        }
    out["per_case"] = [
        {
            "id": r["id"],
            "title": r["title"],
            "local_coverage": r["systems"]["local_weblens"]["facet_coverage"],
            "tavily_coverage": r["systems"]["tavily_direct"]["facet_coverage"],
            "local_tool": r["systems"]["local_weblens"]["tool"],
        }
        for r in records
    ]
    return out


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    local = LocalMCPAdapter()
    tavily = TavilyAdapter()
    print("starting local MCP...")
    await local.start()
    print(f"local tools={len(local.tools)}")
    records: list[dict[str, Any]] = []
    try:
        for case in USE_CASES:
            print(f"[{case['id']}] {case['title']} -> {case['tool']}", flush=True)
            rec = await run_case(case, local, tavily)
            records.append(rec)
            lw = rec["systems"]["local_weblens"]
            tv = rec["systems"]["tavily_direct"]
            print(
                f"  local={lw['status']} {lw['latency_ms']}ms cov={lw['facet_coverage']} | "
                f"tavily={tv['status']} {tv['latency_ms']}ms cov={tv['facet_coverage']}",
                flush=True,
            )
    finally:
        await local.close()
        await tavily.close()

    summary = summarize(records)
    payload = {
        "experiment": "tavily_official_demo_use_cases_v10",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": {
            "local": "real local WebLens MCP server, app/deep_research tool per case",
            "tavily": "direct /search, 5 results; retrieval snippets only, no synthesis",
            "scoring": "case-insensitive facet keyword coverage over the returned payload",
            "caveat": "Tavily /search is not its synthesized assistant; treat its coverage as a lower-bound retrieval baseline.",
        },
        "summary": summary,
        "records": records,
    }
    (OUT / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
