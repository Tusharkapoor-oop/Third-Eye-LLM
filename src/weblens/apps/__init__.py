"""WebLens Applications Layer.

Modular research, knowledge-base, and intelligence applications built on the core
WebLens search, extraction, crawling, and security primitives.
"""

from __future__ import annotations

from .chat import ResearchChatSession
from .company import CompanyResearcher
from .crawl2rag import Crawl2RAG
from .deep_research import AdvancedDeepResearch
from .market import MarketResearcher
from .meeting import MeetingPrepAgent
from .sheets import SheetsEnricher

__all__ = [
    "Crawl2RAG",
    "AdvancedDeepResearch",
    "CompanyResearcher",
    "ResearchChatSession",
    "MarketResearcher",
    "SheetsEnricher",
    "MeetingPrepAgent",
]
