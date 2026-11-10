"""Typed contracts shared by the upgraded retrieval and evaluation paths.

The existing MCP wire format remains backwards compatible.  These models are
used at the boundaries where a caller needs explicit validation rather than a
loosely shaped dictionary.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChunkResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    char_count: int = Field(ge=1)
    section: str = ""
    char_start: int = Field(default=0, ge=0)
    char_end: int = Field(default=0, ge=0)


class SourceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = ""
    url: str
    content: str = ""
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_content: str | None = None
    published_date: str | None = None
    favicon: str | None = None
    chunks: list[ChunkResult] = Field(default_factory=list)


class FailedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    error: str
    blocked_by_waf: bool = False


class UnifiedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = None
    answer: str | None = None
    results: list[SourceItem] = Field(default_factory=list)
    failed_results: list[FailedItem] = Field(default_factory=list)
    response_time: float = Field(default=0.0, ge=0.0)
    source_engine: Literal["local_cache", "local_live", "tavily_fallback"] = "local_live"

    @field_validator("response_time")
    @classmethod
    def finite_response_time(cls, value: float) -> float:
        if value != value or value == float("inf") or value == float("-inf"):
            raise ValueError("response_time must be finite")
        return value


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_query: str = Field(min_length=1)
    primary_keyword_query: str
    semantic_expansion_query: str
    authority_query: str
    bm25_tokens: list[str] = Field(default_factory=list)
    lexical_locks: list[str] = Field(default_factory=list)
    sub_queries: list[str] = Field(default_factory=list, max_length=3)
    intent: Literal["general", "technical", "comparison", "news", "how_to"] = "general"
