"""Search provider contract + engines shared output pipeline.

SearchHit: the one unit all providers produce. The search engine then:
  1) normalizes + dedupes near-duplicates (url fingerprint + title fuzzy),
  2) ranks with a transparent baseline (see ranking.py),
  3) emits a token-capped compact payload. No numeric scores, ever (R2).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Protocol


@dataclass
class SearchHit:
    provider: str
    url: str
    title: str
    snippet: str
    date: str = ""      # ISO-ish why not; '' means unknown (we only claim when known)
    provider_rank: int = 0
    extra: dict = field(default_factory=dict)


ProviderStatuses = ("ok", "no_results", "provider_error")


@dataclass
class ProviderResult:
    provider: str
    status: str
    hits: List[SearchHit]
    raw_query_url: str = ""       # provenance: the provider query endpoint used
    error: str = ""
    latency_ms: float = 0.0


class SearchProvider(Protocol):
    id: str
    def search(self, query: str, *, max_results: int, freshness_days: Optional[int],
               allowed_domains: Optional[List[str]]) -> ProviderResult: ...


from urllib.parse import urlencode  # noqa: E402


def build_bing_rss_url(query: str, max_results: int) -> str:
    qs = urlencode({"q": query, "format": "rss", "count": str(max_results)})
    return "https://www.bing.com/search?" + qs


def _clean_sender(html: str) -> str:
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def try_parse_date_gmt(s: str):
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(s)
        return dt
    except Exception:
        return None
