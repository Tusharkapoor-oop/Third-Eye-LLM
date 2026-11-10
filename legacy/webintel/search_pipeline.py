"""High-recall multi-query search with pre-scrape authority ranking.

Flow
----
1. Fan the expanded sub-queries out to every configured provider concurrently.
2. Over-fetch (``max_results * 3``) per sub-query, then canonicalise URLs
   (tracking parameters and fragments removed) and deduplicate.
3. Score each candidate *before* spending extraction budget on it:
   multi-sub-query consensus, domain authority tier, title/snippet term
   coverage, provider rank and recency when a time range is active.
4. If every local provider yields nothing, rescue the request through Tavily
   (when a key exists) and label the payload so the caller knows why.

Numeric scores are internal only (rule R2); callers receive ordering plus a
provider log.
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from typing import Iterable, Optional
from urllib.parse import urlsplit, urlunsplit

import httpx

from .authority import authority_label, authority_score
from .config import Config
from .limits import TokenBudget, json_tokens
from .schemas import (Candidate, ProviderStatus, QueryPlan, SearchItem,
                      SearchOutcome, TimeRange, WebSearchPayload)
from .search.base import ProviderResult, SearchHit
from .search.bing_rss import BingRssProvider
from .search.brave import BraveProvider
from .search.searxng import SearxngProvider
from .search.tavily import TavilyProvider

_TIME_RANGE_DAYS: dict[str, int] = {"day": 1, "week": 7, "month": 31, "year": 365}

_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d %b %Y",
    "%b %d, %Y",
)

LEGEND = ("r entries: u=url t=title s=snippet d=date when the provider exposes one. "
          "Ordering uses internal signals that are deliberately not emitted (uncalibrated).")


def canonicalize(url: str) -> str:
    """Strip fragments, tracking parameters, default ports and www."""
    from .utils import track_params

    try:
        cleaned = track_params(url)
        parts = urlsplit(cleaned)
    except Exception:
        return url
    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower().removeprefix("www.")
    if not host:
        return url
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = parts.path or "/"
    if path == "/index.html":
        path = "/"
    if len(path) > 1:
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def _parse_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    raw = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(raw[: len(fmt) + 6], fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _term_overlap(query_terms: Iterable[str], text: str) -> float:
    terms = [t for t in query_terms if t]
    if not terms:
        return 0.0
    low = (text or "").lower()
    return sum(1 for t in terms if t in low) / len(terms)


class HybridSearchPipeline:
    def __init__(self, cfg: Config, pool):
        self.cfg = cfg
        self.pool = pool
        self._providers: dict[str, object] = {}
        order = cfg.search.order
        for pid in order:
            if pid == "searxng" and cfg.search.searxng_url:
                self._providers[pid] = SearxngProvider(pool, cfg.search.searxng_url)
            elif pid == "tavily" and cfg.search.tavily_key:
                self._providers[pid] = TavilyProvider(pool, cfg.search.tavily_key)
            elif pid == "brave" and cfg.search.brave_key:
                self._providers[pid] = BraveProvider(pool, cfg.search.brave_key)
            elif pid == "bing_rss":
                self._providers[pid] = BingRssProvider(pool)
        # The keyless provider is always a legal fallback.
        if "bing_rss" not in self._providers:
            self._providers["bing_rss"] = BingRssProvider(pool)
        self.order = list(self._providers)

    # ------------------------------------------------------------------
    # Provider fan-out
    # ------------------------------------------------------------------
    async def _provider_call(self, pid: str, query: str, limit: int,
                             freshness_days: Optional[int],
                             domains: Optional[list[str]]) -> ProviderResult:
        provider = self._providers[pid]
        start = time.perf_counter()
        try:
            result: ProviderResult = await provider.search(
                query, max_results=limit, freshness_days=freshness_days,
                allowed_domains=domains,
            )
            return result
        except (httpx.TimeoutException, asyncio.TimeoutError):
            return ProviderResult(pid, "provider_error", [], query, "timeout",
                                  (time.perf_counter() - start) * 1000)
        except Exception as exc:
            return ProviderResult(pid, "provider_error", [], query,
                                  f"{type(exc).__name__}: {exc}"[:120],
                                  (time.perf_counter() - start) * 1000)

    async def _fan_out(self, plan: QueryPlan, per_query: int,
                       freshness_days: Optional[int],
                       domains: Optional[list[str]]) -> tuple[list[SearchHit], list[dict],
                                                              list[set[str]]]:
        subqueries = plan.subqueries()
        tasks = []
        labels: list[tuple[int, str]] = []
        for idx, subquery in enumerate(subqueries):
            for pid in self.order:
                tasks.append(self._provider_call(pid, subquery, per_query,
                                                 freshness_days, domains))
                labels.append((idx, pid))

        results = await asyncio.gather(*tasks)
        hits: list[SearchHit] = []
        sources: list[set[str]] = []
        log: list[dict] = []
        for (idx, pid), result in zip(labels, results):
            entry = {
                "p": pid if idx == 0 else f"{pid}#{idx + 1}",
                "st": result.status,
                "ms": int(result.latency_ms),
                "n": len(result.hits),
            }
            if result.error:
                entry["note"] = result.error[:80]
            log.append(entry)
            for hit in result.hits:
                hits.append(hit)
                sources.append({"q" + str(idx), pid})
        return hits, log, sources

    # ------------------------------------------------------------------
    # Tavily rescue
    # ------------------------------------------------------------------
    async def _tavily_rescue(self, plan: QueryPlan, max_results: int,
                             freshness_days: Optional[int]) -> list[Candidate]:
        if not self.cfg.search.tavily_key:
            return []
        from tavily import TavilyClient

        def run() -> list[Candidate]:
            client = TavilyClient(api_key=self.cfg.search.tavily_key)
            payload = client.search(
                plan.primary_keyword_query or plan.original,
                search_depth="advanced",
                max_results=max(5, max_results),
                include_answer=False,
                include_raw_content=False,
                chunks_per_source=2,
                topic="general",
            )
            out: list[Candidate] = []
            for rank, item in enumerate(payload.get("results", []), start=1):
                url = canonicalize(str(item.get("url") or ""))
                if not url:
                    continue
                out.append(Candidate(
                    url=url,
                    title=str(item.get("title") or "")[:180],
                    snippet=re.sub(r"\s+", " ", str(item.get("content") or ""))[:400],
                    date=str(item.get("published_date") or "")[:32],
                    providers=["tavily-rescue"],
                    subqueries=[plan.primary_keyword_query],
                    consensus=1,
                    authority=authority_score(url),
                    score=10.0 - rank,
                    provider_rank=rank,
                ))
            return out

        try:
            return await asyncio.wait_for(asyncio.to_thread(run), timeout=20.0)
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Public search
    # ------------------------------------------------------------------
    async def search(self, plan: QueryPlan, *, max_results: int = 5,
                     time_range: Optional[TimeRange] = None,
                     domains: Optional[list[str]] = None) -> SearchOutcome:
        t0 = time.perf_counter()
        max_results = max(1, min(int(max_results or 5), 10))
        per_query = min(30, max(6, max_results * 3))
        freshness_days = _TIME_RANGE_DAYS.get(time_range or "", None)
        window_days = freshness_days

        hits, log, sources = await self._fan_out(plan, per_query, freshness_days, domains)

        candidates: dict[str, Candidate] = {}
        consensus: dict[str, set[str]] = {}
        query_hits: dict[str, set[str]] = {}
        for hit, source in zip(hits, sources):
            url = canonicalize(hit.url)
            if not url:
                continue
            query_key = next(iter(source))
            query_hits.setdefault(query_key, set()).add(url)
            entry = candidates.get(url)
            if entry is None:
                entry = Candidate(
                    url=url,
                    title=(hit.title or "").strip()[:180],
                    snippet=re.sub(r"\s+", " ", hit.snippet or "").strip()[:400],
                    date=(hit.date or "").strip()[:32],
                    providers=[hit.provider],
                    subqueries=[query_key],
                    provider_rank=hit.provider_rank,
                )
                candidates[url] = entry
                consensus[url] = set()
            else:
                if hit.provider not in entry.providers:
                    entry.providers.append(hit.provider)
                if hit.provider_rank and hit.provider_rank < (entry.provider_rank or 99):
                    entry.provider_rank = hit.provider_rank
                if not entry.snippet and hit.snippet:
                    entry.snippet = re.sub(r"\s+", " ", hit.snippet).strip()[:400]
            consensus[url].add(query_key)

        rescued_by = None
        if not candidates:
            rescued = await self._tavily_rescue(plan, max_results, freshness_days)
            for candidate in rescued:
                candidates.setdefault(candidate.url, candidate)
            if candidates:
                rescued_by = "tavily"

        now = datetime.now(timezone.utc)
        query_terms = plan.bm25_tokens or [plan.original]
        for url, candidate in candidates.items():
            candidate.consensus = max(1, len(consensus.get(url, {candidate.subqueries[0] if candidate.subqueries else "q0"})))
            provider_base = 3.0 - min(candidate.provider_rank or 12, 12) * 0.2
            overlap = _term_overlap(query_terms, f"{candidate.title} {candidate.snippet}")
            candidate.term_overlap = round(overlap, 4)
            candidate.authority = authority_score(url)
            recency = 0.0
            parsed = _parse_date(candidate.date)
            if window_days:
                if parsed is None:
                    recency = -0.35
                else:
                    age_days = max(0.0, (now - parsed).total_seconds() / 86400)
                    if age_days > window_days * 1.6:
                        recency = -2.5
                    else:
                        recency = 0.4
            candidate.score = round(
                provider_base
                + 1.0 * candidate.authority
                + 0.35 * (candidate.consensus - 1)
                + 1.2 * overlap
                + recency,
                4,
            )

        ranked = sorted(candidates.values(), key=lambda c: -c.score)[:max_results]
        self._cap_per_domain(ranked)
        status = "ok" if ranked else "no_reliable_result"
        return SearchOutcome(
            status=status,
            candidates=ranked,
            provider_log=log,
            rescued_by=rescued_by,
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
        )

    @staticmethod
    def _cap_per_domain(candidates: list[Candidate]) -> None:
        """In-place: at most two results from one registrable domain."""
        from .ranking import registrable_domain

        seen: dict[str, int] = {}
        keep: list[int] = []
        for idx, candidate in enumerate(candidates):
            host = urlsplit(candidate.url).hostname or ""
            domain = registrable_domain(host)
            if seen.get(domain, 0) >= 2:
                continue
            seen[domain] = seen.get(domain, 0) + 1
            keep.append(idx)
        if len(keep) != len(candidates):
            kept = [candidates[i] for i in keep]
            candidates.clear()
            candidates.extend(kept)


def to_search_payload(plan: QueryPlan, outcome: SearchOutcome, *,
                      max_tokens: int = 600) -> WebSearchPayload:
    """Compact token-capped wire payload. No numeric relevance is exposed."""
    payload = WebSearchPayload(status=outcome.status, q=plan.original, r=[])
    budget = TokenBudget(max_tokens)
    fixed = json_tokens({"status": "ok", "q": plan.original, "note": LEGEND}) + 40

    for candidate in outcome.candidates:
        item = SearchItem(
            u=candidate.url,
            t=candidate.title[:120],
            s=candidate.snippet[:220],
        )
        if candidate.date:
            item.d = candidate.date[:24]
        cost = json_tokens(item.model_dump(exclude_none=True)) + 2
        if budget.used + cost > max_tokens - fixed:
            break
        payload.r.append(item)
        budget.admit("", est=cost)

    payload.prov = [ProviderStatus(**{k: v for k, v in entry.items() if k in
                                      {"p", "st", "ms", "n", "note"}})
                    for entry in outcome.provider_log]
    notes: list[str] = [LEGEND]
    if outcome.rescued_by:
        notes.append(f"local providers returned zero results; rescued via {outcome.rescued_by}.")
    if not payload.r:
        notes.append("no results after canonical dedupe and authority ranking; "
                     "try a narrower query or set allowed_domains.")
    payload.note = " | ".join(notes)
    return payload
