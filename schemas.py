"""Unified Agent Schemas and Protocol Contracts.

Provides Pydantic models for Search, Extract, Map, Crawl, and Deep Research
conforming to Tavily's unified agent contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChunkResult(BaseModel):
    """Ranked text chunk extracted from a source webpage."""

    content: str = Field(description="Cleaned text content of the passage")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Relevance score (0.0 to 1.0)")
    char_count: int = Field(default=0, description="Character length of content")
    section_title: str | None = Field(default=None, description="Parent section heading breadcrumb")


class SourceItem(BaseModel):
    """Standardized search/extract source item with stitched passages."""

    title: str = Field(default="", description="Webpage or document title")
    url: str = Field(description="Canonical URL of the source")
    content: str = Field(default="", description="Stitched top-scoring content passages")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall source relevance score")
    raw_content: str | None = Field(default=None, description="Full raw text if requested")
    published_date: str | None = Field(default=None, description="Detected publication date ISO string")
    favicon: str | None = Field(default=None, description="Favicon URL if extracted")
    chunks: list[ChunkResult] = Field(default_factory=list, description="Individual ranked chunks")


class FailedItem(BaseModel):
    """Failure record for a URL that could not be processed."""

    url: str = Field(description="Target URL that failed")
    error: str = Field(description="Description of the error or failure")
    blocked_by_waf: bool = Field(default=False, description="True if blocked by Cloudflare, DataDome, or WAF")


class UnifiedResponse(BaseModel):
    """Universal response envelope matching the Tavily agent contract."""

    query: str | None = Field(default=None, description="Original or expanded query string")
    answer: str | None = Field(default=None, description="Synthesized direct answer or executive summary")
    results: list[SourceItem] = Field(default_factory=list, description="List of successful source items")
    failed_results: list[FailedItem] = Field(default_factory=list, description="List of failed URLs")
    response_time: float = Field(default=0.0, description="Total pipeline latency in seconds")
    source_engine: Literal["local_cache", "local_live", "tavily_fallback"] = Field(
        default="local_live", description="Primary engine that fulfilled the request"
    )


class SearchRequest(BaseModel):
    """Input parameters for the /search endpoint."""

    query: str = Field(min_length=1, description="Search query string")
    search_depth: Literal["ultra-fast", "fast", "basic", "advanced"] = Field(
        default="basic", description="Search execution depth"
    )
    topic: Literal["general", "news", "finance", "coding"] = Field(
        default="general", description="Subject area domain"
    )
    max_results: int = Field(default=5, ge=1, le=20, description="Maximum number of sources to return")
    chunks_per_source: int = Field(default=3, ge=1, le=10, description="Passages to keep per source")
    time_range: Literal["day", "week", "month", "year"] | None = Field(
        default=None, description="Optional recency filter"
    )
    include_domains: list[str] | None = Field(default=None, description="Restrict to these domains")
    exclude_domains: list[str] | None = Field(default=None, description="Exclude these domains")
    include_raw_content: bool = Field(default=False, description="Include unbudgeted full text")


class ExtractRequest(BaseModel):
    """Input parameters for the /extract endpoint."""

    urls: list[str] = Field(min_length=1, max_length=20, description="URLs to extract (up to 20)")
    query: str | None = Field(default=None, description="Optional query to guide intra-page passage ranking")
    chunks_per_source: int = Field(default=3, ge=1, le=10, description="Top passages to return")
    extract_depth: Literal["basic", "advanced"] = Field(
        default="basic", description="Basic for fast HTTP, advanced for JS rendering"
    )
    js_code: list[str] | None = Field(default=None, description="JavaScript snippets to execute in browser")
    wait_for: str | None = Field(default=None, description="CSS selector or ms to wait for before extraction")


class MapRequest(BaseModel):
    """Input parameters for the /map link graph discovery endpoint."""

    url: str = Field(description="Target base website URL to map")
    max_depth: int = Field(default=2, ge=1, le=5, description="Maximum link crawl depth")
    max_breadth: int = Field(default=20, ge=1, le=100, description="Maximum outgoing links per node")
    limit: int = Field(default=50, ge=1, le=200, description="Maximum total discovered URLs to return")
    select_paths: list[str] | None = Field(default=None, description="Regex patterns URLs must match")
    exclude_paths: list[str] | None = Field(default=None, description="Regex patterns URLs must not match")
    instructions: str | None = Field(default=None, description="Semantic criteria to filter URL paths")


class MapResponse(BaseModel):
    """Output envelope for the /map link discovery endpoint."""

    url: str = Field(description="Base URL mapped")
    discovered_urls: list[str] = Field(default_factory=list, description="Discovered URLs matching criteria")
    count: int = Field(default=0, description="Total count of discovered URLs")
    response_time: float = Field(default=0.0, description="Execution time in seconds")


class CrawlRequest(BaseModel):
    """Input parameters for the /crawl site ingestion endpoint."""

    url: str = Field(description="Target site URL to crawl and ingest")
    max_depth: int = Field(default=2, ge=1, le=4, description="Maximum graph depth")
    max_breadth: int = Field(default=20, ge=1, le=50, description="Maximum links followed per page")
    limit: int = Field(default=25, ge=1, le=50, description="Maximum pages to ingest")
    select_paths: list[str] | None = Field(default=None, description="Regex patterns required")
    exclude_paths: list[str] | None = Field(default=None, description="Regex patterns to exclude")
    instructions: str | None = Field(default=None, description="Guiding topic for in-flight pruning")
    chunks_per_source: int = Field(default=3, ge=1, le=5, description="Chunks kept per page")
    extract_depth: Literal["basic", "advanced"] = Field(default="basic", description="Extraction depth")


class ResearchRequest(BaseModel):
    """Input parameters for the /research autonomous multi-hop agent."""

    input_prompt: str = Field(min_length=3, description="Complex research question or instruction")
    mode: Literal["mini", "pro"] = Field(default="mini", description="mini (2 hops) or pro (up to 4 hops)")


class ResearchResponse(BaseModel):
    """Output report from the autonomous deep research agent."""

    query: str = Field(description="Initial research query")
    answer: str = Field(description="Comprehensive Markdown synthesis with citations")
    sources: list[SourceItem] = Field(default_factory=list, description="Verified sources cited")
    sub_queries: list[str] = Field(default_factory=list, description="Sub-queries executed in research")
    evidence_summary: str = Field(default="", description="Structured findings and key statistics")
    response_time: float = Field(default=0.0, description="Total execution duration in seconds")

