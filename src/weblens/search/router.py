"""Provider routing, fusion, dedupe and transparent ranking.

No relevance score is returned to callers. Ranking is used only to order
results; the ordering is a documented heuristic (reciprocal rank fusion plus a
small static authority prior), not a calibrated probability.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..config import Settings
from ..errors import ErrCode, ProviderError, WebLensError
from ..net import SafeFetcher
from ..urls import host_of
from .base import Hit, dedupe, diversify, near_duplicate, parse_date
from .bing import BingHTML
from .brave import BraveSearch
from .duckduckgo import DuckDuckGoLite
from .searxng import SearXNGSsearch
from .tavily import TavilySearch
from .wikipedia import WikipediaSearch

AUTHORITY = {
    "docs.python.org": 3.0,
    "developer.mozilla.org": 3.0,
    "learn.microsoft.com": 2.5,
    "docs.rs": 2.5,
    "go.dev": 2.5,
    "nodejs.org": 2.5,
    "rust-lang.org": 2.5,
    "python.org": 2.0,
    "github.com": 2.0,
    "stackoverflow.com": 1.5,
    "arxiv.org": 1.5,
    "wikipedia.org": 1.0,
    "nature.com": 1.5,
    "science.org": 1.5,
    "acm.org": 1.2,
    "ieee.org": 1.2,
    "w3.org": 1.5,
    "ietf.org": 1.5,
    "rfc-editor.org": 1.5,
    "owasp.org": 1.2,
    "nvd.nist.gov": 1.5,
    "cve.org": 1.5,
}

_FRESH_DAYS = {"day": 1, "week": 7, "month": 31, "year": 365}

_CONVERSATIONAL = re.compile(
    r"^(?:please\s+)?(?:can you|could you|would you|i want to|i need to|help me|tell me|"
    r"find me|search for|look up|what is|what are|who is|how do i|how to)\s+",
    re.I,
)


def clean_query(query: str) -> str:
    q = (query or "").strip()
    q = re.sub(r"\s+", " ", q)
    q = _CONVERSATIONAL.sub("", q).strip(" ?!.")
    return q or (query or "").strip()


def _authority(url: str) -> float:
    host = host_of(url)
    best = 0.0
    for domain, weight in AUTHORITY.items():
        if host == domain or host.endswith("." + domain):
            best = max(best, weight)
    if host.endswith(".gov") or host.endswith(".edu"):
        best = max(best, 1.2)
    return best


def rank(hits: list[Hit], *, fused: bool = False) -> list[Hit]:
    """Order by RRF (if fused) + static authority + recency. No score is exposed."""
    if not hits:
        return []
    today = date.today()
    groups: dict[str, list[Hit]] = {}
    for h in hits:
        groups.setdefault(h.provider, []).append(h)
    for group in groups.values():
        group.sort(key=lambda h: h.rank)

    scored: list[tuple[float, int, Hit]] = []
    for idx, h in enumerate(hits):
        s = 0.0
        if fused:
            for group in groups.values():
                for pos, gh in enumerate(group):
                    if gh is h:
                        s += 1.0 / (60.0 + pos)
                        break
        else:
            s = 1.0 / (1.0 + max(0, h.rank))
        s += 0.08 * _authority(h.url)
        d = parse_date(h.date)
        if d:
            age_days = (today - d).days
            if 0 <= age_days <= 30:
                s += 0.15
            elif age_days > 730:
                s -= 0.1
        scored.append((s, idx, h))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [t[2] for t in scored]


@dataclass
class SearchOutcome:
    query: str
    used_query: str
    hits: list[Hit]
    providers: list[str] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)
    status: str = "ok"
    elapsed_ms: int = 0
    warnings: list[str] = field(default_factory=list)


class SearchRouter:
    def __init__(self, settings: Settings, fetcher: SafeFetcher):
        self.s = settings
        self.fetcher = fetcher
        self._providers: list[object] = []
        self.unavailable: dict[str, str] = {}
        self._build()

    def _build(self) -> None:
        s = self.s
        for name in s.provider_list:
            try:
                if name == "brave":
                    if not s.brave_api_key:
                        self.unavailable[name] = "BRAVE_API_KEY not set"
                        continue
                    self._providers.append(BraveSearch(self.fetcher, s.brave_api_key))
                elif name == "ddg":
                    self._providers.append(DuckDuckGoLite(self.fetcher))
                elif name == "tavily":
                    if not s.tavily_api_key:
                        self.unavailable[name] = "TAVILY_API_KEY not set"
                        continue
                    self._providers.append(TavilySearch(self.fetcher, s.tavily_api_key))
                elif name == "searxng":
                    if not s.searxng_url:
                        self.unavailable[name] = "WEBLENS_SEARXNG_URL not set"
                        continue
                    self._providers.append(SearXNGSsearch(self.fetcher, s.searxng_url))
                elif name == "bing":
                    self._providers.append(BingHTML(self.fetcher))
                elif name == "wikipedia":
                    self._providers.append(WikipediaSearch(self.fetcher))
            except ProviderError as e:
                self.unavailable[name] = e.message

    @property
    def provider_names(self) -> list[str]:
        return [getattr(p, "name", "?") for p in self._providers]

    async def search(
        self,
        query: str,
        *,
        k: int = 5,
        freshness: str | None = None,
        domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        mode: str | None = None,
    ) -> SearchOutcome:
        started = time.perf_counter()
        used = clean_query(query)
        outcome = SearchOutcome(query=query, used_query=used, hits=[])
        if not used:
            outcome.status = "error"
            outcome.failures["input"] = "empty query"
            return outcome
        if len(used) > 400:
            used = used[:400]
        if not self._providers:
            raise ProviderError(
                "no search provider configured; set WEBLENS_SEARCH_PROVIDERS and keys",
                code=ErrCode.NO_PROVIDER,
            )
        mode = mode or self.s.search_mode
        if mode == "fuse" and len(self._providers) > 1:
            merged = await self._fuse(
                used,
                k=k,
                freshness=freshness,
                domains=domains,
                exclude_domains=exclude_domains,
                outcome=outcome,
            )
        else:
            merged = await self._fallback(
                used,
                k=k,
                freshness=freshness,
                domains=domains,
                exclude_domains=exclude_domains,
                outcome=outcome,
            )

        merged = dedupe(merged)
        # near-duplicate snippets across different URLs (syndicated copies)
        unique: list[Hit] = []
        for h in merged:
            if any(near_duplicate(h.title + " " + h.snippet, p.title + " " + p.snippet) for p in unique):
                outcome.warnings.append("duplicate_text_removed")
                continue
            unique.append(h)
        merged = diversify(rank(unique, fused=(mode == "fuse")), per_domain=2)[:k]

        outcome.hits = merged
        if not merged:
            outcome.status = "no_reliable_result"
            outcome.warnings.append("no_results")
        elif freshness in _FRESH_DAYS:
            window = _FRESH_DAYS[freshness]
            cutoff = date.today() - timedelta(days=window)
            dated = [parse_date(h.date) for h in merged[:3]]
            known = [d for d in dated if d]
            if known and all(d < cutoff for d in known):
                outcome.status = "possibly_outdated"
                outcome.warnings.append(f"top_results_older_than_{freshness}")
            elif not known:
                outcome.warnings.append("dates_unknown")
        if outcome.failures and merged:
            outcome.status = outcome.status if outcome.status != "ok" else "partial"
        outcome.elapsed_ms = int((time.perf_counter() - started) * 1000)
        return outcome

    async def _fallback(
        self, q: str, *, k: int, freshness, domains, exclude_domains, outcome: SearchOutcome
    ) -> list[Hit]:
        collected: list[Hit] = []
        for provider in self._providers:
            name = getattr(provider, "name", "?")
            try:
                hits = await provider.search(  # type: ignore[attr-defined]
                    q,
                    k=k,
                    freshness=freshness,
                    domains=domains,
                    exclude_domains=exclude_domains,
                )
                outcome.providers.append(name)
                collected.extend(hits)
                if len({h.url for h in collected}) >= k:
                    break
            except WebLensError as e:
                outcome.failures[name] = str(e.code)
            except Exception as e:  # provider bugs must not kill the request
                outcome.failures[name] = type(e).__name__
        return collected

    async def _fuse(
        self, q: str, *, k: int, freshness, domains, exclude_domains, outcome: SearchOutcome
    ) -> list[Hit]:
        async def one(p):
            name = getattr(p, "name", "?")
            try:
                hits = await p.search(  # type: ignore[attr-defined]
                    q,
                    k=max(k, 8),
                    freshness=freshness,
                    domains=domains,
                    exclude_domains=exclude_domains,
                )
                return name, hits, None
            except Exception as e:
                return name, [], e

        results = await asyncio.gather(*(one(p) for p in self._providers))
        merged: list[Hit] = []
        for name, hits, err in results:
            if err is None:
                outcome.providers.append(name)
                merged.extend(hits)
            else:
                outcome.failures[name] = type(err).__name__
        return merged
