"""Three Provider Adapters for Evaluation Lab:
1. Local WebLens MCP (System 1)
2. Deployed WebLens MCP (System 2)
3. Tavily Direct API (System 3)
"""

from .common_interface.base import (
    AnswerResponse,
    ExtractItem,
    ExtractResponse,
    ProviderUsage,
    ResearchProvider,
    ResearchResponse,
    SearchItem,
    SearchResponse,
)
from .deployed_adapter.adapter import DeployedWebLensAdapter
from .gemini_adapter.adapter import GeminiAdapter
from .tavily_adapter.adapter import TavilyAdapter
from .weblens_adapter.adapter import WebLensAdapter

__all__ = [
    "AnswerResponse",
    "DeployedWebLensAdapter",
    "ExtractItem",
    "ExtractResponse",
    "GeminiAdapter",
    "ProviderUsage",
    "ResearchProvider",
    "ResearchResponse",
    "SearchItem",
    "SearchResponse",
    "TavilyAdapter",
    "WebLensAdapter",
]

