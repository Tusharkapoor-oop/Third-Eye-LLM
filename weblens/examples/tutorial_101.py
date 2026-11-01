"""WebLens 101: Runnable Tutorial Script.

Demonstrates the core WebLens search, extract, crawl, deep research, and application APIs.
"""

import asyncio
from weblens.apps import (
    AdvancedDeepResearch,
    CompanyResearcher,
    Crawl2RAG,
    MarketResearcher,
    MeetingPrepAgent,
    ResearchChatSession,
)
from weblens.service import WebLens


async def main() -> None:
    print("=== WebLens 101: System Initialization ===")
    service = WebLens()

    # 1. System Diagnostics
    print("\n[1] Checking System Health...")
    diag = await service.doctor()
    print(f"WebLens Version: {diag.get('version')}")
    print(f"Active Providers: {diag.get('providers')}")
    print(f"Tokenizer: {diag.get('tokenizer')}")

    # 2. Keyless Web Search
    print("\n[2] Executing Web Search...")
    search_res = await service.search("Python asyncio event loop", max_results=2)
    print(f"Search Status: {search_res.get('status')}")
    for idx, hit in enumerate(search_res.get("res", [])):
        print(f"  Hit {idx+1}: {hit.get('t')} -> {hit.get('u')}")

    # 3. Research Chat Session
    print("\n[3] Conversational Research Chat...")
    chat = ResearchChatSession(service)
    turn1 = await chat.send_message("What is the primary benefit of Python's asyncio?")
    print(f"Chat Turn 1 Status: {turn1.get('status')}")
    print(f"Citations Returned: {len(turn1.get('citations', []))}")

    # 4. Company Researcher
    print("\n[4] Company Intelligence...")
    comp = CompanyResearcher(service)
    profile = await comp.research_company("Python Software Foundation")
    print(f"Company Research Status: {profile.get('status')}")
    print(f"Detected Domain: {profile.get('detected_domain')}")

    # 5. Market Researcher
    print("\n[5] Market Research & Filing Disclosures...")
    market = MarketResearcher(service)
    market_res = await market.analyze_asset("Apple Inc.")
    print(f"Market Status: {market_res.get('status')}")
    print(f"Disclosures Discovered: {market_res.get('disclosures_found')}")

    # 6. Meeting Preparation
    print("\n[6] Meeting Briefing...")
    meeting = MeetingPrepAgent(service)
    brief = await meeting.prepare_brief(
        "Open Source Python Ecosystem Planning",
        ["Guido van Rossum"],
        company_or_org="Python Software Foundation",
    )
    print(f"Meeting Brief Status: {brief.get('status')}")
    print(f"Attendees Researched: {brief.get('attendees_researched')}")

    # 7. Knowledge Base (Crawl2RAG)
    print("\n[7] Crawl2RAG Knowledge Base Query...")
    kb = Crawl2RAG(service)
    stats = kb.stats()
    print(f"Local Knowledge Base Docs: {stats.get('documents')}")

    await service.close()
    print("\n=== WebLens 101 Tutorial Complete ===")


if __name__ == "__main__":
    asyncio.run(main())

