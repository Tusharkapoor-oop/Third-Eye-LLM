"""Common adapter interface for WebLens vs Tavily evaluation.

Defines a provider-neutral protocol and standardized result dataclasses
to guarantee apples-to-apples comparisons across quality, latency, tokens,
reliability, and cost.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


@dataclass
class ProviderUsage:
    requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    credits_consumed: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_latency_ms: float = 0.0


@dataclass
class SearchItem:
    url: str
    title: str
    content: str
    score: float | None = None
    raw_content: str | None = None
    published_date: str | None = None


@dataclass
class SearchResponse:
    provider: str
    query: str
    results: list[SearchItem]
    # ok          -> transport ok and at least one result, engine status ok
    # partial     -> results returned but engine reported a degraded state
    # empty       -> transport ok and the engine deliberately returned nothing
    # error       -> transport or tool error
    status: Literal["ok", "partial", "empty", "no_reliable_result", "error"]
    latency_ms: float
    tokens_returned: int
    credits_used: float = 0.0
    error: str | None = None
    raw_response: dict[str, Any] | None = field(default=None, repr=False)
    raw_status: str | None = None
    http_status: int | None = None
    response_bytes: int | None = None
    response_hash: str | None = None
    backend_provider: str | None = None
    cache_state: str = "unknown"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def successful(self) -> bool:
        return self.status in ("ok", "partial") and bool(self.results)


@dataclass
class ExtractItem:
    url: str
    raw_content: str
    markdown: str
    status: Literal["ok", "failed", "unsupported"]
    error: str | None = None


@dataclass
class ExtractResponse:
    provider: str
    results: list[ExtractItem]
    latency_ms: float
    tokens_returned: int
    credits_used: float = 0.0
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AnswerResponse:
    provider: str
    query: str
    answer: str
    citations: list[dict[str, Any]]
    confidence: float | None
    latency_ms: float
    tokens_returned: int
    credits_used: float = 0.0
    status: Literal["ok", "uncertain", "abstain", "error"] = "ok"
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ResearchResponse:
    provider: str
    query: str
    report_markdown: str
    subqueries: list[str]
    sources: list[dict[str, Any]]
    contradictions: list[str]
    latency_ms: float
    tokens_returned: int
    credits_used: float = 0.0
    status: Literal["ok", "partial", "error"] = "ok"
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ResearchProvider(ABC):
    """Abstract provider interface for search, extraction, and research operations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'weblens_independent', 'tavily')."""
        pass

    @property
    @abstractmethod
    def is_independent(self) -> bool:
        """True if results are sourced independently of Tavily."""
        pass

    @abstractmethod
    async def search(self, query: str, *, max_results: int = 5, **options: Any) -> SearchResponse:
        """Execute a web search query."""
        pass

    @abstractmethod
    async def extract(self, urls: list[str], **options: Any) -> ExtractResponse:
        """Extract content from one or more URLs."""
        pass

    @abstractmethod
    async def crawl(self, url: str, *, max_pages: int = 10, **options: Any) -> ExtractResponse:
        """Crawl a website and extract structured content."""
        pass

    @abstractmethod
    async def answer(self, query: str, **options: Any) -> AnswerResponse:
        """Generate a synthesized factual answer with citations."""
        pass

    @abstractmethod
    async def research(self, query: str, **options: Any) -> ResearchResponse:
        """Execute an iterative, multi-hop deep research investigation."""
        pass

    @abstractmethod
    def get_usage(self) -> ProviderUsage:
        """Retrieve telemetry and resource usage statistics."""
        pass

