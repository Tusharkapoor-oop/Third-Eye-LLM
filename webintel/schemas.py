"""Typed contracts for the upgraded retrieval pipeline.

Two families of models live here:

*   **Internal models** (``QueryPlan``, ``Candidate``, ``Passage``, ``Extraction``)
    carry ranking signals. They are *never* serialised into MCP tool output.
    The project invariant R2 forbids emitting uncalibrated relevance numbers to
    agents, so numeric scores stay inside the process boundary.
*   **Wire models** (``WebSearchPayload``, ``ExtractPayload``, ``MapPayload``,
    ``CrawlPayload``, ``ResearchPayload``) are the exact JSON shapes the MCP
    tools return. They use the short keys documented in each tool description.

Everything is pydantic v2 and strict about types; every field has a default so
that partially-populated payloads can be constructed during error handling.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

TimeRange = Literal["day", "week", "month", "year"]
Intent = Literal["code", "comparison", "news", "research", "general"]
PassageKind = Literal["text", "code", "table"]
ExtractStatus = Literal[
    "ok", "no_content", "thin_content_js", "blocked", "unreachable",
    "unsupported_type", "error",
]
ResearchStatus = Literal[
    "ok", "evidence_only", "partial_budget", "no_reliable_result", "error",
]


def utc_now_iso() -> str:
    """Second-resolution UTC timestamp used for every fetch marker."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Internal planning / retrieval models
# --------------------------------------------------------------------------
class GeminiQueryPlan(BaseModel):
    """Subset sent to Gemini as a response_schema (kept small on purpose).

    Gemini structured output rejects very wide schemas; this is the minimum
    information the search pipeline needs from the model.
    """

    primary_keyword_query: str = Field(min_length=1, max_length=400)
    semantic_expansion_query: str = Field(min_length=1, max_length=400)
    authority_query: str = Field(min_length=1, max_length=400)
    bm25_tokens: list[str] = Field(default_factory=list, max_length=16)
    technical: bool = False


class QueryPlan(BaseModel):
    """Normalised expansion result used by every downstream stage."""

    original: str
    primary_keyword_query: str
    semantic_expansion_query: str
    authority_query: str
    bm25_tokens: list[str] = Field(default_factory=list)
    lexical_locks: list[str] = Field(default_factory=list)
    technical: bool = False
    intent: Intent = "general"
    source: Literal["gemini", "rules"] = "rules"
    expand_ms: int = 0

    def subqueries(self) -> list[str]:
        """Distinct queries to fan out, preserving priority order."""
        out: list[str] = []
        seen: set[str] = set()
        for q in (
            self.primary_keyword_query,
            self.semantic_expansion_query,
            self.authority_query,
        ):
            key = " ".join(q.lower().split())
            if key and key not in seen:
                seen.add(key)
                out.append(q)
        return out or [self.original]


class Candidate(BaseModel):
    """A deduplicated search hit with internal authority/consensus signals."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    url: str
    title: str = ""
    snippet: str = ""
    date: str = ""
    providers: list[str] = Field(default_factory=list)
    subqueries: list[str] = Field(default_factory=list)
    consensus: int = 1
    authority: float = 0.0
    term_overlap: float = 0.0
    score: float = 0.0
    provider_rank: int = 0


class SearchOutcome(BaseModel):
    status: Literal["ok", "no_reliable_result"] = "ok"
    candidates: list[Candidate] = Field(default_factory=list)
    provider_log: list[dict[str, Any]] = Field(default_factory=list)
    rescued_by: Optional[str] = None
    blocked_ratio: float = 0.0
    elapsed_ms: int = 0


class Passage(BaseModel):
    """A query-selected passage. ``score`` stays internal (R2)."""

    url: str
    title: str = ""
    section: str = ""
    span: str
    kind: PassageKind = "text"
    order: int = 0
    score: float = 0.0
    bm25: float = 0.0
    selector: Literal["cross-encoder", "bm25", "identifier"] = "bm25"


class Extraction(BaseModel):
    """Full-page extraction outcome before passage selection."""

    url: str
    final_url: str = ""
    status: ExtractStatus = "ok"
    tier: Literal[0, 1, 2, 3] = 0
    markdown: str = ""
    title: str = ""
    date: str = ""
    site: str = ""
    canonical: str = ""
    http_status: int = 0
    bytes_read: int = 0
    truncated: bool = False
    reason: str = ""
    elapsed_ms: int = 0
    from_cache: bool = False

    @field_validator("date")
    @classmethod
    def _strip_crawl_date(cls, v: str) -> str:
        """Reject a 'date' that is really the crawl date (honesty rule R2)."""
        if v and v[:10] == utc_now_iso()[:10]:
            return ""
        return v


# --------------------------------------------------------------------------
# Wire models (what MCP callers actually receive)
# --------------------------------------------------------------------------
class SearchItem(BaseModel):
    u: str
    t: str = ""
    s: str = ""
    d: Optional[str] = None


class ProviderStatus(BaseModel):
    p: str
    st: str
    ms: int = 0
    n: int = 0
    note: Optional[str] = None


class WebSearchPayload(BaseModel):
    status: Literal["ok", "no_reliable_result", "error"]
    q: str
    r: list[SearchItem] = Field(default_factory=list)
    prov: list[ProviderStatus] = Field(default_factory=list)
    note: str = ""


class ExtractedPassage(BaseModel):
    sec: str = ""
    span: str
    kind: Optional[PassageKind] = None


class ExtractPayload(BaseModel):
    status: ExtractStatus
    u: str
    fetched_at: str = Field(default_factory=utc_now_iso)
    t: Optional[str] = None
    date: Optional[str] = None
    site: Optional[str] = None
    canon: Optional[str] = None
    x: list[ExtractedPassage] = Field(default_factory=list)
    full: Optional[str] = None
    tier: Optional[int] = None
    note: str = ""
    ms: int = 0
    cache: bool = False


class MapItem(BaseModel):
    u: str
    d: int = 0


class MapPayload(BaseModel):
    status: Literal["ok", "no_content", "error"]
    u: str
    urls: list[MapItem] = Field(default_factory=list)
    n: int = 0
    truncated: bool = False
    note: str = ""
    ms: int = 0


class CrawlPage(BaseModel):
    u: str
    status: str
    t: Optional[str] = None
    x: list[ExtractedPassage] = Field(default_factory=list)
    note: Optional[str] = None


class CrawlPayload(BaseModel):
    status: Literal["ok", "partial_budget", "no_content", "error"]
    u: str
    pages: list[CrawlPage] = Field(default_factory=list)
    n: int = 0
    budget: dict[str, int] = Field(default_factory=dict)
    note: str = ""
    ms: int = 0


class EvidenceItem(BaseModel):
    x: str
    u: str
    sec: str = ""
    ts: Optional[str] = None
    kind: Optional[PassageKind] = None


class Citation(BaseModel):
    title: str
    url: str
    idx: int = 0


class ResearchPayload(BaseModel):
    status: ResearchStatus
    q: str
    answer: Optional[str] = None
    citations: list[Citation] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    plan: Optional[dict[str, Any]] = None
    budget: dict[str, int] = Field(default_factory=dict)
    note: str = ""
    ms: int = 0


class ErrorPayload(BaseModel):
    status: Literal["error"] = "error"
    note: str
    ms: int = 0


def dump(model: BaseModel) -> dict[str, Any]:
    """Compact wire serialisation: drop nulls, keep empty lists explicit."""
    return model.model_dump(exclude_none=True)
