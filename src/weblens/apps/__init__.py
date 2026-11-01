"""WebLens Application Suite (9 Workflows).

1. Deep Research (multi-hop factual inquiry)
2. Company Researcher (company profiles & disclosures)
3. Chat / Answer Engine (conversational search with citations)
4. Crawl2RAG (polite crawl & local FTS5 indexing)
5. Market Researcher (financial & regulatory intelligence)
6. Sheets (batch spreadsheet enrichment with formula injection defense)
7. Meeting Prep (corporate & professional attendee research)
8. Tutorial 101 (executable developer guide)
9. Research Agent Chat (persistent stateful research sessions)
"""

from .chat import ResearchChatSession
from .company import CompanyResearcher
from .crawl2rag import Crawl2RAG
from .deep_research import DeepResearchAgent
from .market import MarketResearcher
from .meeting import MeetingPrepAgent
from .research_chat import PersistentResearchChat
from .sheets import SheetsEnricher
from .tutorial_101 import run_tutorial

__all__ = [
    "CompanyResearcher",
    "Crawl2RAG",
    "DeepResearchAgent",
    "MarketResearcher",
    "MeetingPrepAgent",
    "PersistentResearchChat",
    "ResearchChatSession",
    "SheetsEnricher",
    "run_tutorial",
]
