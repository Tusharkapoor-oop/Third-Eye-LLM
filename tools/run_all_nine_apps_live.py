"""Execute and *verify* all nine WebLens product applications against live web data.

This replaces the earlier version, which reported PASS for workflows that had
provably done no work (Crawl2RAG checked empty stats, the tutorial ran a single
step, the persistent chat never tested persistence, and Sheets never checked
that any cell was actually enriched). Each application below now has explicit,
falsifiable assertions; a workflow that cannot meet them is reported PARTIAL or
FAIL rather than PASS.

Run:
    python tools/run_all_nine_apps_live.py
    python tools/run_all_nine_apps_live.py --only crawl2rag,sheets
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "weblens" / "src"))
sys.path.insert(0, str(ROOT / "src"))

from weblens.apps.chat import ResearchChatSession
from weblens.apps.company import CompanyResearcher
from weblens.apps.crawl2rag import Crawl2RAG
from weblens.apps.deep_research import DeepResearchAgent
from weblens.apps.market import MarketResearcher
from weblens.apps.meeting import MeetingPrepAgent
from weblens.apps.research_chat import PersistentResearchChat
from weblens.apps.sheets import SheetsEnricher
from weblens.apps.tutorial_101 import run_tutorial
from weblens.service import WebLens

CRAWL_URL = "https://docs.python.org/3/library/asyncio-task.html"


def _elapsed(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def _all_have(items: list[dict[str, Any]], key: str) -> bool:
    return bool(items) and all(bool(i.get(key)) for i in items)


def _formula_safe(records: list[dict[str, Any]]) -> bool:
    dangerous = ("=", "+", "-", "@")
    for row in records:
        for value in row.values():
            if isinstance(value, str) and value.startswith(dangerous):
                return False
    return True


async def app_deep_research(service: WebLens) -> dict[str, Any]:
    t0 = time.perf_counter()
    agent = DeepResearchAgent(service)
    res = await agent.execute_research(
        "What are the core technical differences between asyncio and threading in Python?",
        max_tokens=1500,
    )
    findings = res.get("key_findings", [])
    subqueries = res.get("methodology", {}).get("subqueries_searched", [])
    passed = bool(findings) and bool(subqueries) and _all_have(findings, "url")
    assertions = {
        "findings_present": bool(findings),
        "subqueries_present": bool(subqueries),
        "every_finding_has_url": _all_have(findings, "url"),
        "every_finding_has_span": all(isinstance(f.get("span"), list) for f in findings),
    }
    return {
        "status": "PASS" if passed else ("PARTIAL" if findings else "FAIL"),
        "report_status": res.get("status"),
        "findings_count": len(findings),
        "distinct_domains": res.get("diversity_metrics", {}).get("distinct_domains_count", 0),
        "subqueries": len(subqueries),
        "assertions": assertions,
        "sample": findings[:2],
        "latency_ms": _elapsed(t0),
    }


async def app_company(service: WebLens) -> dict[str, Any]:
    t0 = time.perf_counter()
    agent = CompanyResearcher(service)
    res = await agent.research_company("Python Software Foundation")
    profile = res.get("profile", {}) or {}
    populated = {k: len(v or []) for k, v in profile.items()}
    passed = (
        res.get("status") == "found"
        and bool(res.get("detected_domain"))
        and populated.get("overview", 0) > 0
        and populated.get("leadership", 0) > 0
    )
    return {
        "status": "PASS" if passed else ("PARTIAL" if res.get("status") == "found" else "FAIL"),
        "report_status": res.get("status"),
        "detected_domain": res.get("detected_domain"),
        "populated_fields": populated,
        "assertions": {
            "status_found": res.get("status") == "found",
            "domain_detected": bool(res.get("detected_domain")),
            "overview_has_citations": populated.get("overview", 0) > 0,
            "leadership_has_citations": populated.get("leadership", 0) > 0,
        },
        "latency_ms": _elapsed(t0),
    }


async def app_chat(service: WebLens) -> dict[str, Any]:
    t0 = time.perf_counter()
    session = ResearchChatSession(service)
    turn1 = await session.send_message("Python asyncio event loop architecture")
    turn2 = await session.send_message("What about its performance implications?")
    citations = turn1.get("citations", [])
    passed = (
        turn1.get("status") == "ok"
        and bool(citations)
        and bool(turn1.get("answer"))
        and turn2.get("turn_history_count") == 2
        and turn1.get("query_used", "") in turn2.get("query_used", "")
    )
    return {
        "status": "PASS" if passed else ("PARTIAL" if citations else "FAIL"),
        "report_status": turn1.get("status"),
        "citations_returned": len(citations),
        "turn1_query_used": turn1.get("query_used"),
        "turn2_query_used": turn2.get("query_used"),
        "assertions": {
            "turn1_has_citations": bool(citations),
            "turn1_has_answer": bool(turn1.get("answer")),
            "history_advanced_to_two": turn2.get("turn_history_count") == 2,
            "followup_resolved_with_prior_topic": turn1.get("query_used", "")
            in turn2.get("query_used", ""),
        },
        "latency_ms": _elapsed(t0),
    }


async def app_crawl2rag(service: WebLens, work_dir: Path) -> dict[str, Any]:
    t0 = time.perf_counter()
    kb = Crawl2RAG(service, db_path=work_dir / "crawl2rag.db")
    ingest = await kb.ingest(CRAWL_URL, max_pages=2, max_depth=1)
    stats = kb.stats()
    query = await kb.query("asyncio task group event loop", top_k=3)
    passages = query.get("passages", [])
    passed = (
        ingest.get("pages_indexed", 0) > 0
        and stats.get("documents", 0) > 0
        and stats.get("passages", 0) > 0
        and query.get("n", 0) > 0
        and _all_have(passages, "url")
        and all(isinstance(p.get("span"), list) and len(p["span"]) == 2 for p in passages)
    )
    return {
        "status": "PASS" if passed else ("PARTIAL" if stats.get("documents", 0) > 0 else "FAIL"),
        "database_path": str(kb.db_path),
        "ingest": {
            "pages_crawled": ingest.get("pages_crawled", 0),
            "pages_indexed": ingest.get("pages_indexed", 0),
            "passages_indexed": ingest.get("passages_indexed", 0),
            "failures": ingest.get("failures", []),
        },
        "stats": stats,
        "query_hits": query.get("n", 0),
        "assertions": {
            "ingest_indexed_pages": ingest.get("pages_indexed", 0) > 0,
            "documents_nonzero": stats.get("documents", 0) > 0,
            "passages_nonzero": stats.get("passages", 0) > 0,
            "query_returned_passages": query.get("n", 0) > 0,
            "passages_have_spans": all(
                isinstance(p.get("span"), list) and len(p["span"]) == 2 for p in passages
            ),
        },
        "sample_passage": passages[0] if passages else None,
        "latency_ms": _elapsed(t0),
    }


async def app_market(service: WebLens) -> dict[str, Any]:
    t0 = time.perf_counter()
    agent = MarketResearcher(service)
    res = await agent.analyze_portfolio(["Apple Inc.", "Microsoft Corporation"])
    metrics = [
        m
        for report in (res.get("assets", {}) or {}).values()
        for m in (report.get("verified_metrics", []) or [])
    ]
    sourced = all(bool(m.get("source_url")) for m in metrics) if metrics else False
    passed = (
        res.get("total_disclosures_analyzed", 0) > 0
        and len(metrics) > 0
        and sourced
        and bool(res.get("disclaimer"))
    )
    return {
        "status": "PASS" if passed else ("PARTIAL" if res.get("total_disclosures_analyzed", 0) > 0 else "FAIL"),
        "portfolio_size": res.get("portfolio_size", 0),
        "disclosures_analyzed": res.get("total_disclosures_analyzed", 0),
        "verified_metrics": len(metrics),
        "assertions": {
            "disclosures_present": res.get("total_disclosures_analyzed", 0) > 0,
            "verified_metrics_present": len(metrics) > 0,
            "all_metrics_sourced": sourced,
            "disclaimer_present": bool(res.get("disclaimer")),
        },
        "sample_metrics": metrics[:2],
        "latency_ms": _elapsed(t0),
    }


async def app_sheets(service: WebLens) -> dict[str, Any]:
    t0 = time.perf_counter()
    enricher = SheetsEnricher(service)
    rows = [
        {"Company": "Apple", "Note": "=cmd|' /C calc'!A0"},
        {"Company": "Microsoft", "Note": "who is CEO"},
    ]
    res = await enricher.enrich_records(rows, {"CEO": "who is the CEO of {Company}?"})
    records = res.get("records", [])
    verified = [
        r for r in records if r.get("CEO_status") == "verified" and bool(r.get("CEO"))
    ]
    safe = _formula_safe(records)
    sourced = all(bool(r.get("CEO_source")) for r in verified) if verified else False
    passed = (
        res.get("total_rows") == 2
        and safe
        and bool(verified)
        and sourced
    )
    return {
        "status": "PASS" if passed else ("PARTIAL" if res.get("total_rows") == 2 and safe else "FAIL"),
        "rows_enriched": res.get("total_rows", 0),
        "verified_ceo_cells": len(verified),
        "assertions": {
            "all_rows_returned": res.get("total_rows") == 2,
            "formula_values_defanged": safe,
            "at_least_one_verified": bool(verified),
            "verified_values_have_sources": sourced,
        },
        "sample_rows": records,
        "latency_ms": _elapsed(t0),
    }


async def app_meeting(service: WebLens) -> dict[str, Any]:
    t0 = time.perf_counter()
    agent = MeetingPrepAgent(service)
    brief = await agent.prepare_from_calendar_event(
        {
            "summary": "Technical Architecture Review",
            "attendees": [{"displayName": "Guido van Rossum", "email": "guido@python.org"}],
            "organization": "Python Software Foundation",
        }
    )
    profiles = brief.get("attendee_profiles", [])
    sourced = [p for p in profiles if p.get("sources")]
    nonempty = [p for p in profiles if p.get("public_professional_background")]
    passed = (
        brief.get("attendees_researched") == 1
        and bool(sourced)
        and bool(nonempty)
        and bool(brief.get("company_context"))
        and bool(brief.get("privacy_notice"))
    )
    return {
        "status": "PASS" if passed else ("PARTIAL" if brief.get("attendees_researched") else "FAIL"),
        "attendees_researched": brief.get("attendees_researched", 0),
        "attendees_with_sources": len(sourced),
        "company_context_items": len(brief.get("company_context", [])),
        "assertions": {
            "one_attendee_researched": brief.get("attendees_researched") == 1,
            "attendee_has_profile_text": bool(nonempty),
            "attendee_has_sources": bool(sourced),
            "company_context_present": bool(brief.get("company_context")),
            "privacy_notice_present": bool(brief.get("privacy_notice")),
        },
        "latency_ms": _elapsed(t0),
    }


async def app_tutorial(service: WebLens) -> dict[str, Any]:
    t0 = time.perf_counter()
    res = await run_tutorial(service, step="all")
    steps = res.get("steps", {})
    failed = [k for k, v in steps.items() if v.get("status") != "passed"]
    passed = res.get("status") == "ok" and len(steps) == 9 and not failed
    return {
        "status": "PASS" if passed else ("PARTIAL" if steps else "FAIL"),
        "report_status": res.get("status"),
        "steps_executed": len(steps),
        "passed_steps": res.get("passed_steps", 0),
        "failed_steps": failed,
        "assertions": {
            "all_nine_steps_ran": len(steps) == 9,
            "all_steps_passed": not failed,
        },
        "step_statuses": {k: v.get("status") for k, v in steps.items()},
        "latency_ms": _elapsed(t0),
    }


async def app_persistent_chat(service: WebLens, work_dir: Path) -> dict[str, Any]:
    t0 = time.perf_counter()
    db_path = work_dir / "research_sessions.db"
    sid = f"nine-app-{int(time.time())}"
    chat = PersistentResearchChat(service, db_path=db_path, session_id=sid)
    chat.set_topic("Python Concurrency Models")
    turn = await chat.send_query(
        "What is the difference between asyncio tasks and threads in Python?"
    )
    exported = chat.export_session()
    # Re-open with the same session id and DB to prove state was persisted,
    # not merely kept in memory.
    reopened = PersistentResearchChat(service, db_path=db_path, session_id=sid)
    messages = reopened.get_messages()
    markdown = reopened.export_markdown()
    assistant = [m for m in messages if m.role == "assistant"]
    passed = (
        bool(turn.content)
        and bool(turn.citations)
        and len(messages) >= 2
        and bool(assistant)
        and exported.topic == "Python Concurrency Models"
        and "Python Concurrency Models" in markdown
    )
    return {
        "status": "PASS" if passed else ("PARTIAL" if messages else "FAIL"),
        "session_id": sid,
        "database_path": str(db_path),
        "citations_count": len(turn.citations),
        "persisted_message_count": len(messages),
        "exported_topic": exported.topic,
        "exported_total_sources": exported.total_sources,
        "assertions": {
            "assistant_content_present": bool(turn.content),
            "citations_present": bool(turn.citations),
            "messages_persisted": len(messages) >= 2,
            "reopened_session_has_assistant": bool(assistant),
            "topic_persisted": exported.topic == "Python Concurrency Models",
            "markdown_export_contains_topic": "Python Concurrency Models" in markdown,
        },
        "latency_ms": _elapsed(t0),
    }


APPS: dict[str, tuple[str, Callable[..., Awaitable[dict[str, Any]]]]] = {
    "deep_research": ("app_1_deep_research", app_deep_research),
    "company": ("app_2_company_researcher", app_company),
    "chat": ("app_3_chat_answer_engine", app_chat),
    "crawl2rag": ("app_4_crawl2rag", app_crawl2rag),
    "market": ("app_5_market_researcher", app_market),
    "sheets": ("app_6_sheets_enricher", app_sheets),
    "meeting": ("app_7_meeting_prep", app_meeting),
    "tutorial": ("app_8_tutorial_101", app_tutorial),
    "persistent_chat": ("app_9_persistent_research_chat", app_persistent_chat),
}


async def run_all_apps(only: set[str] | None = None) -> dict[str, Any]:
    print("==================================================================")
    print("   WEBLENS V10: VERIFIED NINE-APPLICATION END-TO-END RUN          ")
    print("==================================================================")

    service = WebLens()
    outcomes: dict[str, Any] = {}
    work_dir = Path(tempfile.mkdtemp(prefix="weblens_nine_apps_"))
    selected = [k for k in APPS if not only or k in only]

    try:
        for idx, key in enumerate(selected, start=1):
            label, fn = APPS[key]
            print(f"\n[{idx}/{len(selected)}] {label}...")
            try:
                if key in ("crawl2rag", "persistent_chat"):
                    outcome = await fn(service, work_dir)
                else:
                    outcome = await fn(service)
            except Exception as exc:  # an app crash is a FAIL, not a missing result
                outcome = {
                    "status": "FAIL",
                    "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                    "latency_ms": 0.0,
                }
            outcomes[label] = outcome
            print(f"  -> {outcome.get('status')} in {outcome.get('latency_ms')} ms")
    finally:
        await service.close()

    total = len(outcomes)
    passed = sum(1 for v in outcomes.values() if v.get("status") == "PASS")
    partial = sum(1 for v in outcomes.values() if v.get("status") == "PARTIAL")
    failed = sum(1 for v in outcomes.values() if v.get("status") == "FAIL")
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "verification_version": "v10-assertions",
        "total_workflows": total,
        "passed": passed,
        "partial": partial,
        "failed": failed,
        "all_passed": passed == total and total == 9,
        "work_dir": str(work_dir),
        "outcomes": outcomes,
    }

    out_file = ROOT / "reports" / "nine_applications_verification.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    evidence_dir = ROOT / "evidence" / "raw_results" / "nine_apps"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (evidence_dir / f"nine_apps_verification_{stamp}.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    print("\n==================================================================")
    print(f"   VERIFIED: {passed} PASS / {partial} PARTIAL / {failed} FAIL of {total}")
    print("==================================================================")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        default=None,
        help="comma-separated subset: " + ",".join(APPS),
    )
    args = parser.parse_args()
    only = set(args.only.split(",")) if args.only else None
    summary = asyncio.run(run_all_apps(only))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
