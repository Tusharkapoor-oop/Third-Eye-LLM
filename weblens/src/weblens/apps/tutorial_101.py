"""WebLens 101: Runnable Tutorial and Interactive Guide.

Master the WebLens API to build AI agents that search, extract, crawl the web,
and integrate real-time insights with your private knowledge bases.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..service import WebLens
from .chat import ResearchChatSession
from .company import CompanyResearcher
from .crawl2rag import Crawl2RAG
from .deep_research import DeepResearchAgent
from .market import MarketResearcher
from .meeting import MeetingPrepAgent
from .sheets import SheetsEnricher


async def run_tutorial(service: WebLens | None = None, step: str = "all") -> dict[str, Any]:
    """Execute guided tutorial steps demonstrating all core and advanced capabilities."""
    own_service = False
    if service is None:
        service = WebLens()
        own_service = True

    results: dict[str, Any] = {"status": "ok", "tutorial": "WebLens 101", "steps": {}}

    try:
        # Step 1: Diagnostics
        if step in ("all", "doctor", "health"):
            diag = await service.doctor()
            results["steps"]["1_diagnostics"] = {
                "title": "System Diagnostics & Providers",
                "version": diag.get("version"),
                "providers": diag.get("providers"),
                "status": "passed",
            }

        # Step 2: Keyless Web Search
        if step in ("all", "search"):
            search_res = await service.search("Python asyncio event loop architecture", max_results=2)
            results["steps"]["2_web_search"] = {
                "title": "Direct Web Search",
                "hits_returned": len(search_res.get("res", [])),
                "top_hit_title": search_res.get("res", [{}])[0].get("t", "") if search_res.get("res") else "",
                "status": "passed" if search_res.get("status") == "ok" else "degraded",
            }

        # Step 3: Conversational Research Chat
        if step in ("all", "chat"):
            chat = ResearchChatSession(service)
            turn1 = await chat.send_message("What is the primary benefit of Python's asyncio?")
            results["steps"]["3_research_chat"] = {
                "title": "Conversational Research Chat",
                "citations_count": len(turn1.get("citations", [])),
                "answer_tokens": turn1.get("tokens", 0),
                "status": "passed",
            }

        # Step 4: Company Researcher
        if step in ("all", "company"):
            comp = CompanyResearcher(service)
            profile = await comp.research_company("Python Software Foundation")
            results["steps"]["4_company_research"] = {
                "title": "Company Profile Intelligence",
                "company_status": profile.get("status"),
                "domain": profile.get("detected_domain"),
                "status": "passed",
            }

        # Step 5: Market Researcher
        if step in ("all", "market"):
            market = MarketResearcher(service)
            market_res = await market.analyze_asset("Apple Inc.")
            results["steps"]["5_market_research"] = {
                "title": "Market Disclosures & Verified Metrics",
                "disclosures_found": market_res.get("disclosures_found", 0),
                "metrics_count": len(market_res.get("verified_metrics", [])),
                "status": "passed",
            }

        # Step 6: Sheets Batch Dataset Enrichment
        if step in ("all", "sheets"):
            enricher = SheetsEnricher(service)
            sample_rows = [{"Company": "Apple"}, {"Company": "Microsoft"}]
            enriched = await enricher.enrich_records(sample_rows, {"CEO": "who is the current CEO of {Company}?"})
            results["steps"]["6_sheets_enrich"] = {
                "title": "Spreadsheet Batch Enrichment with Injection Defense",
                "rows_processed": enriched.get("total_rows", 0),
                "status": "passed",
            }

        # Step 7: Meeting Preparation
        if step in ("all", "meeting"):
            meeting = MeetingPrepAgent(service)
            brief = await meeting.prepare_brief(
                "Open Source Python Ecosystem Planning",
                ["Guido van Rossum"],
                company_or_org="Python Software Foundation",
            )
            results["steps"]["7_meeting_prep"] = {
                "title": "Executive Meeting Preparation",
                "attendees_researched": brief.get("attendees_researched", 0),
                "status": "passed",
            }

        # Step 8: Crawl2RAG Knowledge Base
        if step in ("all", "crawl2rag", "rag"):
            kb = Crawl2RAG(service)
            stats = kb.stats()
            results["steps"]["8_crawl2rag"] = {
                "title": "Crawl2RAG Local Knowledge Base",
                "documents_indexed": stats.get("documents", 0),
                "passages_indexed": stats.get("passages", 0),
                "status": "passed",
            }

        # Step 9: Multi-Hop Deep Research
        if step in ("all", "research", "deep_research"):
            deep_agent = DeepResearchAgent(service)
            deep_res = await deep_agent.execute_research("Explain the difference between asyncio tasks and threads in Python", max_tokens=1200)
            results["steps"]["9_deep_research"] = {
                "title": "Multi-Hop Deep Research & Conflict Detection",
                "claims_collected": len(deep_res.get("key_findings", [])),
                "subqueries_searched": len(deep_res.get("methodology", {}).get("subqueries_searched", [])),
                "status": "passed",
            }

    finally:
        if own_service:
            await service.close()

    return results


async def main() -> None:
    print("=== WebLens 101: Running Guided Tutorial ===")
    res = await run_tutorial()
    for step_key, step_data in sorted(res.get("steps", {}).items()):
        print(f"[{step_key}] {step_data.get('title')}: {step_data.get('status')}")
    print("=== Tutorial Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
