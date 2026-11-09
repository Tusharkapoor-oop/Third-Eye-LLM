"""WebLens 101: Runnable Tutorial and Interactive Guide.

Master the WebLens API to build AI agents that search, extract, crawl the web,
and integrate real-time insights with your private knowledge bases.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from ..service import WebLens
from .chat import ResearchChatSession
from .company import CompanyResearcher
from .crawl2rag import Crawl2RAG
from .deep_research import DeepResearchAgent
from .market import MarketResearcher
from .meeting import MeetingPrepAgent
from .sheets import SheetsEnricher

# A stable, public, server-rendered page used to prove that the Crawl2RAG step
# really crawls and indexes text instead of merely printing empty stats.
TUTORIAL_CRAWL_URL = "https://docs.python.org/3/library/asyncio-task.html"


def _status(passed: bool, degraded: bool = False) -> str:
    if passed:
        return "passed"
    return "degraded" if degraded else "failed"


async def run_tutorial(service: WebLens | None = None, step: str = "all") -> dict[str, Any]:
    """Execute guided tutorial steps and report a *verified* status for each.

    Every step returns ``passed`` only when its own observable output proves the
    step worked (hits, citations, indexed passages, findings). Previously all
    steps reported ``passed`` unconditionally, which made the tutorial unable to
    detect a broken workflow.
    """
    own_service = False
    if service is None:
        service = WebLens()
        own_service = True

    results: dict[str, Any] = {"status": "ok", "tutorial": "WebLens 101", "steps": {}}

    try:
        # Step 1: Diagnostics
        if step in ("all", "doctor", "health"):
            diag = await service.doctor()
            providers = diag.get("providers") or []
            results["steps"]["1_diagnostics"] = {
                "title": "System Diagnostics & Providers",
                "version": diag.get("version"),
                "providers": providers,
                "status": _status(bool(providers)),
            }

        # Step 2: Keyless Web Search
        if step in ("all", "search"):
            search_res = await service.search("Python asyncio event loop architecture", max_results=2)
            if not search_res.get("res"):
                # Keyless providers sometimes return nothing for long queries;
                # retry once with a shorter query rather than reporting a pass
                # on an empty result.
                search_res = await service.search("asyncio event loop", max_results=2)
            hits = search_res.get("res", [])
            results["steps"]["2_web_search"] = {
                "title": "Direct Web Search",
                "hits_returned": len(hits),
                "search_status": search_res.get("status"),
                "top_hit_title": hits[0].get("t", "") if hits else "",
                "status": _status(bool(hits), degraded=search_res.get("status") == "partial"),
            }

        # Step 3: Conversational Research Chat
        if step in ("all", "chat"):
            chat = ResearchChatSession(service)
            turn1 = await chat.send_message("What is the primary benefit of Python's asyncio?")
            citations = turn1.get("citations", [])
            results["steps"]["3_research_chat"] = {
                "title": "Conversational Research Chat",
                "citations_count": len(citations),
                "answer_present": bool(turn1.get("answer")),
                "status": _status(bool(citations) and bool(turn1.get("answer")), degraded=True),
            }

        # Step 4: Company Researcher
        if step in ("all", "company"):
            comp = CompanyResearcher(service)
            profile = await comp.research_company("Python Software Foundation")
            results["steps"]["4_company_research"] = {
                "title": "Company Profile Intelligence",
                "company_status": profile.get("status"),
                "domain": profile.get("detected_domain"),
                "status": _status(
                    profile.get("status") == "found" and bool(profile.get("detected_domain")),
                    degraded=True,
                ),
            }

        # Step 5: Market Researcher
        if step in ("all", "market"):
            market = MarketResearcher(service)
            market_res = await market.analyze_asset("Apple Inc.")
            disclosures = market_res.get("disclosures_found", 0)
            metrics = market_res.get("verified_metrics", [])
            results["steps"]["5_market_research"] = {
                "title": "Market Disclosures & Verified Metrics",
                "disclosures_found": disclosures,
                "metrics_count": len(metrics),
                "status": _status(disclosures > 0, degraded=True),
            }

        # Step 6: Sheets Batch Dataset Enrichment
        if step in ("all", "sheets"):
            enricher = SheetsEnricher(service)
            sample_rows = [{"Company": "Apple"}, {"Company": "Microsoft"}]
            enriched = await enricher.enrich_records(sample_rows, {"CEO": "who is the current CEO of {Company}?"})
            records = enriched.get("records", [])
            verified = sum(1 for r in records if r.get("CEO_status") == "verified" and r.get("CEO"))
            results["steps"]["6_sheets_enrich"] = {
                "title": "Spreadsheet Batch Enrichment with Injection Defense",
                "rows_processed": enriched.get("total_rows", 0),
                "rows_verified": verified,
                "status": _status(enriched.get("total_rows") == 2 and verified >= 1, degraded=True),
            }

        # Step 7: Meeting Preparation
        if step in ("all", "meeting"):
            meeting = MeetingPrepAgent(service)
            brief = await meeting.prepare_brief(
                "Open Source Python Ecosystem Planning",
                ["Guido van Rossum"],
                company_or_org="Python Software Foundation",
            )
            profiles = brief.get("attendee_profiles", [])
            sourced = sum(1 for p in profiles if p.get("sources"))
            results["steps"]["7_meeting_prep"] = {
                "title": "Executive Meeting Preparation",
                "attendees_researched": brief.get("attendees_researched", 0),
                "attendees_with_sources": sourced,
                "status": _status(sourced >= 1 and bool(brief.get("privacy_notice")), degraded=True),
            }

        # Step 8: Crawl2RAG Knowledge Base -- actually crawl and query.
        if step in ("all", "crawl2rag", "rag"):
            tmp_dir = Path(tempfile.mkdtemp(prefix="weblens_tutorial_"))
            kb = Crawl2RAG(service, db_path=tmp_dir / "tutorial_kb.db")
            ingest = await kb.ingest(TUTORIAL_CRAWL_URL, max_pages=1, max_depth=0)
            stats = kb.stats()
            rag_query = await kb.query("asyncio task event loop", top_k=3)
            results["steps"]["8_crawl2rag"] = {
                "title": "Crawl2RAG Local Knowledge Base",
                "pages_crawled": ingest.get("pages_crawled", 0),
                "documents_indexed": stats.get("documents", 0),
                "passages_indexed": stats.get("passages", 0),
                "query_hits": rag_query.get("n", 0),
                "status": _status(
                    stats.get("documents", 0) > 0 and stats.get("passages", 0) > 0 and rag_query.get("n", 0) > 0,
                    degraded=ingest.get("pages_crawled", 0) > 0,
                ),
            }

        # Step 9: Multi-Hop Deep Research
        if step in ("all", "research", "deep_research"):
            deep_agent = DeepResearchAgent(service)
            deep_res = await deep_agent.execute_research(
                "Explain the difference between asyncio tasks and threads in Python", max_tokens=1200
            )
            findings = deep_res.get("key_findings", [])
            subqueries = deep_res.get("methodology", {}).get("subqueries_searched", [])
            results["steps"]["9_deep_research"] = {
                "title": "Multi-Hop Deep Research & Conflict Detection",
                "claims_collected": len(findings),
                "subqueries_searched": len(subqueries),
                "status": _status(
                    bool(findings) and bool(subqueries),
                    degraded=bool(subqueries),
                ),
            }

    finally:
        if own_service:
            await service.close()

    statuses = [s.get("status") for s in results["steps"].values()]
    results["passed_steps"] = sum(1 for s in statuses if s == "passed")
    results["total_steps"] = len(statuses)
    results["status"] = "ok" if statuses and all(s == "passed" for s in statuses) else "partial"
    return results


async def main() -> None:
    print("=== WebLens 101: Running Guided Tutorial ===")
    res = await run_tutorial()
    for step_key, step_data in sorted(res.get("steps", {}).items()):
        print(f"[{step_key}] {step_data.get('title')}: {step_data.get('status')}")
    print("=== Tutorial Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
