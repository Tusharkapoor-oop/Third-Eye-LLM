"""
Search Provider Interfaces and Data Structures
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source_date: str | None = None
    provider: str = ""

    def to_dict(self) -> dict:
        d = {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet
        }
        if self.source_date:
            d["source_date"] = self.source_date
        return d

@dataclass
class SearchResponse:
    query: str
    status: str  # "success" | "no_reliable_result" | "possibly_outdated" | "conflicting_sources"
    results: list[SearchResult] = field(default_factory=list)
    total_found: int = 0
    latency_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "status": self.status,
            "results": [r.to_dict() for r in self.results],
            "total_found": self.total_found,
            "latency_seconds": round(self.latency_seconds, 3)
        }

class SearchProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        count: int = 5,
        time_filter: str | None = None,
        domains: list[str] | None = None
    ) -> list[SearchResult]:
        pass
