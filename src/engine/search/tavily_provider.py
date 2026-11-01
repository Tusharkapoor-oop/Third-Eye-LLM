"""
Tavily Search Provider.
Integrates Tavily Search API as a search provider for the WebIntel engine.
Requires TAVILY_API_KEY environment variable. Falls back gracefully if key missing.
"""

from __future__ import annotations

import os

from src.engine.config import CONFIG
from src.engine.search.base import SearchProvider, SearchResult


class TavilySearchProvider(SearchProvider):
    """Tavily Search API provider.

    Uses the Tavily REST /search endpoint directly (no SDK dependency required)
    to avoid adding a hard dependency. Falls back to empty results if the API
    key is not configured or the request fails.
    """

    def __init__(self):
        self.api_key = CONFIG.tavily_api_key or os.getenv("TAVILY_API_KEY", "")
        self.base_url = "https://api.tavily.com/search"
        self.timeout = 10.0

    @property
    def name(self) -> str:
        return "tavily"

    def is_available(self) -> bool:
        """Returns True if a Tavily API key is configured."""
        return bool(self.api_key and self.api_key.strip())

    async def search(
        self,
        query: str,
        count: int = 5,
        time_filter: str | None = None,
        domains: list[str] | None = None,
    ) -> list[SearchResult]:
        """Search using Tavily API.

        Args:
            query: Search query string.
            count: Maximum number of results to return.
            time_filter: One of "day", "week", "month", "year" (Tavily uses days).
            domains: Optional list of domains to restrict to.

        Returns:
            List of SearchResult objects. Empty list if unavailable or on error.
        """
        if not self.is_available():
            return []

        try:
            import httpx
        except ImportError:
            return []

        # Map time_filter to Tavily's days parameter
        days = None
        if time_filter:
            time_map = {"day": 1, "week": 7, "month": 30, "year": 365}
            days = time_map.get(time_filter.lower())

        # Build domains include parameter
        include_domains = None
        if domains:
            include_domains = [d.strip() for d in domains if d.strip()]

        payload = {
            "query": query,
            "search_depth": "basic",
            "max_results": min(max(count, 1), 10),
            "include_answer": False,
            "include_images": False,
            "include_raw_content": False,
        }
        if days is not None:
            payload["days"] = days
        if include_domains:
            payload["include_domains"] = include_domains

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=CONFIG.connect_timeout)
            ) as client:
                resp = await client.post(self.base_url, json=payload, headers=headers)
                if resp.status_code != 200:
                    return []
                data = resp.json()
        except Exception:
            return []

        results: list[SearchResult] = []
        for item in data.get("results", [])[:count]:
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            content = item.get("content", "").strip()
            if title and url:
                results.append(
                    SearchResult(
                        title=title,
                        url=url,
                        snippet=content,
                        provider=self.name,
                        source_date=item.get("published_date"),
                    )
                )
        return results
