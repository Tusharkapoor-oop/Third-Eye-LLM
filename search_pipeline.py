"""Multi-Query Search Pipeline and Pre-Scrape Domain Authority Scoring.

Implements:
- Sub-query consensus scoring (+0.35 multi-hit boost)
- Domain Authority tiering (Tier 1 / Tier 2 boosts, SEO farm penalties)
- Concurrent URL extraction with early-exit streaming
- Automatic hybrid fallback to Tavily API
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlsplit, urlunparse

import httpx

from cache import SQLiteCache
from config import CONFIG
from extractor import TieredExtractor
from query_engine import QueryPlan, plan_query_fast
from schemas import ChunkResult, FailedItem, SourceItem, UnifiedResponse
from security import shared_ssl_context


def normalize_url(raw_url: str) -> str:
    """Strip tracking query parameters (utm_*, ref, etc.) and fragments."""
    try:
        parts = urlsplit(raw_url.strip())
        query_params = parse_qs(parts.query, keep_blank_values=False)
        # Strip tracking keys
        filtered_params = {
            k: v for k, v in query_params.items()
            if not k.lower().startswith(("utm_", "fbclid", "gclid", "ref", "source", "mc_eid"))
        }
        clean_query = urlencode(filtered_params, doseq=True)
        # Rebuild without fragment
        clean_url = urlunparse((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", clean_query, ""))
        return clean_url
    except Exception:
        return raw_url.strip()


def calculate_domain_authority(url: str) -> float:
    """Calculate Domain Authority weight based on authoritative lists and penalties."""
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]

        # Tier 1 Official / Research Sources
        for t1 in CONFIG.tier1_domains:
            if host == t1 or host.endswith("." + t1):
                return 0.50

        # Tier 1 TLDs (.gov, .edu)
        if host.endswith(".gov") or host.endswith(".edu") or host.endswith(".ac.uk"):
            return 0.50

        # Tier 2 Reputable Tech & News
        for t2 in CONFIG.tier2_domains:
            if host == t2 or host.endswith("." + t2):
                return 0.20

        # Penalized low-quality scraper content farms
        for p in CONFIG.penalized_domains:
            if host == p or host.endswith("." + p):
                return -0.60

        return 0.0
    except Exception:
        return 0.0


async def _search_searxng(query: str, count: int = 15, time_range: str | None = None) -> list[dict[str, str]]:
    """Query SearXNG JSON API endpoint."""
    params: dict[str, str | int] = {
        "q": query,
        "format": "json",
    }
    if time_range:
        params["time_range"] = time_range

    try:
        async with httpx.AsyncClient(timeout=3.0, verify=shared_ssl_context()) as client:
            resp = await client.get(f"{CONFIG.searxng_url.rstrip('/')}/search", params=params)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                return [
                    {
                        "url": r.get("url", ""),
                        "title": r.get("title", ""),
                        "snippet": r.get("content", ""),
                    }
                    for r in results if r.get("url")
                ]
    except Exception:
        pass
    return []


async def _search_ddg_html(query: str, count: int = 15, time_range: str | None = None) -> list[dict[str, str]]:
    """Local fallback search using DuckDuckGo HTML without API keys."""
    headers = {
        "User-Agent": CONFIG.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    data = {"q": query, "b": ""}
    if time_range:
        time_map = {"day": "d", "week": "w", "month": "m", "year": "y"}
        if time_range.lower() in time_map:
            data["df"] = time_map[time_range.lower()]

    try:
        from bs4 import BeautifulSoup
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True, verify=shared_ssl_context()) as client:
            resp = await client.post("https://lite.duckduckgo.com/lite/", data=data, headers=headers)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                results: list[dict[str, str]] = []
                for a_tag in soup.find_all("a", class_="result-link"):
                    href = a_tag.get("href", "")
                    title = a_tag.get_text().strip()
                    if href and href.startswith("http"):
                        results.append({"url": href, "title": title, "snippet": ""})
                    if len(results) >= count:
                        break
                return results
    except Exception:
        pass
    return []


async def execute_multi_search(
    queries: list[str],
    overfetch_limit: int = 20,
    time_range: str | None = None,
) -> list[tuple[str, str, float]]:
    """Execute queries concurrently and rank candidate URLs with Consensus & Authority boosts.

    Returns:
        list[tuple[str, str, float]]: (url, title, composite_score) sorted descending.
    """
    tasks = []
    for q in queries:
        tasks.append(_search_searxng(q, count=overfetch_limit, time_range=time_range))

    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    # If SearXNG returned 0 results across all queries, fallback to DDG HTML
    all_empty = all(isinstance(res, Exception) or not res for res in gathered)
    if all_empty:
        ddg_tasks = [_search_ddg_html(q, count=overfetch_limit, time_range=time_range) for q in queries]
        gathered = await asyncio.gather(*ddg_tasks, return_exceptions=True)

    url_metadata: dict[str, dict[str, Any]] = {}

    for res in gathered:
        if isinstance(res, list):
            for rank_idx, item in enumerate(res):
                u = normalize_url(item.get("url", ""))
                if not u or not u.startswith("http"):
                    continue

                if u not in url_metadata:
                    url_metadata[u] = {
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                        "subquery_hits": 1,
                        "best_rank": rank_idx,
                    }
                else:
                    url_metadata[u]["subquery_hits"] += 1
                    url_metadata[u]["best_rank"] = min(url_metadata[u]["best_rank"], rank_idx)

    # Score each candidate URL
    scored_candidates: list[tuple[str, str, float]] = []

    for u, meta in url_metadata.items():
        # Baseline rank score: 1.0 down to 0.1
        rank_score = max(0.1, 1.0 - (meta["best_rank"] * 0.05))

        # Multi-query consensus boost (+0.35 for each additional subquery hit)
        consensus_boost = (meta["subquery_hits"] - 1) * 0.35

        # Domain authority tier boost / penalty
        authority_boost = calculate_domain_authority(u)

        composite = rank_score + consensus_boost + authority_boost
        scored_candidates.append((u, meta["title"], composite))

    # Sort descending by composite score
    scored_candidates.sort(key=lambda x: x[2], reverse=True)
    return scored_candidates


class SearchPipeline:
    """End-to-end multi-query search and passage extraction engine."""

    def __init__(self, extractor: TieredExtractor | None = None, cache: SQLiteCache | None = None):
        self.extractor = extractor or TieredExtractor()
        self.cache = cache or SQLiteCache()

    async def close(self) -> None:
        """Cleanly close pipeline cache and extractor resources."""
        try:
            await self.cache.close()
        except Exception:
            pass
        try:
            await self.extractor.close()
        except Exception:
            pass

    async def _execute_tavily_fallback(
        self,
        query: str,
        max_results: int,
        chunks_per_source: int,
        search_depth: str = "advanced",
    ) -> UnifiedResponse:
        """Call Tavily API directly and normalize into UnifiedResponse."""
        t0 = time.perf_counter()
        if not query or not query.strip():
            return UnifiedResponse(
                query=query or "",
                answer="No query provided.",
                results=[],
                failed_results=[],
                response_time=0.0,
                source_engine="local_live",
            )

        from tavily import TavilyClient

        max_results = max(1, min(int(max_results or 5), 50))
        chunks_per_source = max(1, min(int(chunks_per_source or 3), 10))

        cache_key = f"search:{query.strip()}:{search_depth}:{max_results}"
        try:
            cached = await self.cache.get(cache_key)
            if cached:
                res = UnifiedResponse.model_validate_json(cached)
                res.source_engine = "local_cache"
                res.response_time = round(time.perf_counter() - t0, 4)
                return res
        except Exception:
            pass

        client = TavilyClient(api_key=CONFIG.tavily_api_key)
        loop = asyncio.get_running_loop()

        try:
            res = await loop.run_in_executor(
                None,
                lambda: client.search(
                    query=query,
                    search_depth=search_depth,
                    max_results=max_results,
                    include_answer="advanced",
                ),
            )
        except Exception as exc:
            return UnifiedResponse(
                query=query,
                answer=f"Fallback search error: {exc}",
                results=[],
                failed_results=[FailedItem(url="tavily_fallback", error=str(exc), blocked_by_waf=False)],
                response_time=round(time.perf_counter() - t0, 3),
                source_engine="tavily_fallback",
            )

        sources: list[SourceItem] = []
        for r in res.get("results", []):
            content_text = r.get("content", "")
            chunk = ChunkResult(content=content_text, score=r.get("score", 0.9), char_count=len(content_text))
            sources.append(
                SourceItem(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    content=content_text,
                    score=r.get("score", 0.9),
                    published_date=r.get("published_date"),
                    chunks=[chunk],
                )
            )

        elapsed = round(time.perf_counter() - t0, 3)
        return UnifiedResponse(
            query=query,
            answer=res.get("answer"),
            results=sources,
            failed_results=[],
            response_time=elapsed,
            source_engine="tavily_fallback",
        )

    async def search(
        self,
        query: str,
        *,
        search_depth: str = "basic",
        topic: str = "general",
        max_results: int = 5,
        chunks_per_source: int = 3,
        time_range: str | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> UnifiedResponse:
        """Execute full search pipeline with query planning, overfetching, and passage ranking."""
        t0 = time.perf_counter()
        if not query or not query.strip():
            return UnifiedResponse(
                query=query or "",
                answer="No query provided.",
                results=[],
                failed_results=[],
                response_time=0.0,
                source_engine="local_live",
            )

        max_results = max(1, min(int(max_results or 5), 50))
        chunks_per_source = max(1, min(int(chunks_per_source or 3), 10))

        cache_key = f"search:{query.strip()}:{search_depth}:{max_results}"
        try:
            cached = await self.cache.get(cache_key)
            if cached:
                res = UnifiedResponse.model_validate_json(cached)
                res.source_engine = "local_cache"
                res.response_time = round(time.perf_counter() - t0, 4)
                return res
        except Exception:
            pass

        # Step 1: Query Intelligence & Sub-query planning
        plan: QueryPlan = await plan_query_fast(query)

        # Build list of queries to fire
        query_candidates = [plan.primary_keyword_query]
        if search_depth in ("basic", "advanced"):
            query_candidates.append(plan.semantic_expansion_query)
            query_candidates.extend(plan.sub_queries)

        query_candidates = list(dict.fromkeys(query_candidates))[:3]

        # Step 2: Multi-query search execution & Domain Authority Scoring
        overfetch_cap = max_results * 3
        candidate_urls = await execute_multi_search(
            query_candidates,
            overfetch_limit=overfetch_cap,
            time_range=time_range,
        )

        # Domain inclusion / exclusion filtering
        filtered_candidates: list[tuple[str, str, float]] = []
        for u, title, score in candidate_urls:
            host = urlparse(u).netloc.lower()
            if include_domains and not any(host == d.lower() or host.endswith("." + d.lower()) for d in include_domains):
                continue
            if exclude_domains and any(host == d.lower() or host.endswith("." + d.lower()) for d in exclude_domains):
                continue
            filtered_candidates.append((u, title, score))

        # Check if local search completely failed -> Trigger Tavily Fallback
        if not filtered_candidates and CONFIG.tavily_api_key:
            return await self._execute_tavily_fallback(
                query=query,
                max_results=max_results,
                chunks_per_source=chunks_per_source,
                search_depth="advanced" if search_depth == "advanced" else "basic",
            )

        max_results = max(1, min(int(max_results or 5), 50))
        chunks_per_source = max(1, min(int(chunks_per_source or 3), 10))

        cache_key = f"search:{query.strip()}:{search_depth}:{max_results}"
        try:
            cached = await self.cache.get(cache_key)
            if cached:
                res = UnifiedResponse.model_validate_json(cached)
                res.source_engine = "local_cache"
                res.response_time = round(time.perf_counter() - t0, 4)
                return res
        except Exception:
            pass

        # Step 3: Concurrent URL extraction with early-exit
        target_candidates = filtered_candidates[:max_results * 2]
        extract_timeout = 6.0 if search_depth == "advanced" else 4.0
        extract_tasks = [
            asyncio.create_task(
                asyncio.wait_for(
                    self.extractor.extract_url(
                        u,
                        query=query,
                        chunks_per_source=chunks_per_source,
                        force_tier2=(search_depth == "advanced"),
                    ),
                    timeout=extract_timeout,
                )
            )
            for u, _, _ in target_candidates
        ]

        extracted_sources: list[SourceItem] = []
        failed_items: list[FailedItem] = []

        # Stream extraction results as they finish
        for fut in asyncio.as_completed(extract_tasks):
            try:
                res = await fut
                if isinstance(res, SourceItem):
                    extracted_sources.append(res)
                    # Early exit once we have reached max_results valid sources
                    if len(extracted_sources) >= max_results:
                        break
                elif isinstance(res, FailedItem):
                    failed_items.append(res)
            except Exception as e:
                failed_items.append(FailedItem(url="timeout_or_error", error=str(e), blocked_by_waf=False))

        # Cleanly cancel any pending stragglers and wait for cancellation so
        # pytest-asyncio does not report leaked tasks during teardown.
        for t in extract_tasks:
            if not t.done():
                t.cancel()
        for t in extract_tasks:
            if t.cancelled():
                continue
            try:
                await t
            except asyncio.CancelledError:
                pass
            except Exception:
                # A failed extraction task must not turn cleanup into a new
                # request failure. The failure was already recorded above.
                pass

        # Step 4: If local extraction yielded 0 sources, trigger Tavily rescue fallback
        if len(extracted_sources) == 0 and CONFIG.tavily_api_key:
            return await self._execute_tavily_fallback(
                query=query,
                max_results=max_results,
                chunks_per_source=chunks_per_source,
                search_depth="advanced" if search_depth == "advanced" else "basic",
            )

        # Sort final extracted sources by relevance score
        extracted_sources.sort(key=lambda s: s.score, reverse=True)

        elapsed = round(time.perf_counter() - t0, 3)
        final_res = UnifiedResponse(
            query=query,
            answer=None,
            results=extracted_sources[:max_results],
            failed_results=failed_items,
            response_time=elapsed,
            source_engine="local_live",
        )
        try:
            await self.cache.set(cache_key, final_res.model_dump_json())
        except Exception:
            pass
        return final_res

