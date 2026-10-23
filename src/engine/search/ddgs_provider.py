"""
DuckDuckGo Search Provider using the official ddgs library.
Provides fast, zero-configuration, live web search without requiring an API key.
"""

from __future__ import annotations

import asyncio

from src.engine.search.base import SearchProvider, SearchResult


class DDGSearchProvider(SearchProvider):
    def __init__(self):
        self._ddgs = None

    @property
    def name(self) -> str:
        return "ddgs"

    def _get_ddgs(self):
        if self._ddgs is None:
            from ddgs import DDGS
            self._ddgs = DDGS()
        return self._ddgs

    async def search(
        self,
        query: str,
        count: int = 5,
        time_filter: str | None = None,
        domains: list[str] | None = None
    ) -> list[SearchResult]:
        time_map = {
            "day": "d",
            "d": "d",
            "week": "w",
            "w": "w",
            "month": "m",
            "m": "m",
            "year": "y",
            "y": "y",
        }
        timelimit = time_map.get(time_filter.lower()) if time_filter else None

        effective_query = query
        if domains:
            domain_filter = " OR ".join(f"site:{d.strip()}" for d in domains if d.strip())
            if domain_filter:
                effective_query = f"{query} ({domain_filter})"

        def _do_search():
            ddgs_client = self._get_ddgs()
            try:
                return list(ddgs_client.text(
                    effective_query,
                    max_results=max(count, 5),
                    timelimit=timelimit
                ))
            except Exception:
                # Re-instantiate in case of connection socket drop
                try:
                    from ddgs import DDGS
                    self._ddgs = DDGS()
                    return list(self._ddgs.text(
                        effective_query,
                        max_results=max(count, 5),
                        timelimit=timelimit
                    ))
                except Exception:
                    return []

        try:
            loop = asyncio.get_running_loop()
            raw_results = await loop.run_in_executor(None, _do_search)
        except Exception:
            return []

        results: list[SearchResult] = []
        for r in raw_results:
            title = r.get("title", "").strip()
            href = r.get("href", "").strip()
            body = r.get("body", "").strip()
            if title and href:
                results.append(SearchResult(
                    title=title,
                    url=href,
                    snippet=body,
                    provider=self.name
                ))
        return results[:count]
