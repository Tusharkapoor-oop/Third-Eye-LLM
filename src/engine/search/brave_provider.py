"""
Brave Search and SearXNG API Providers.
Activated when corresponding environment credentials or URLs are provided.
"""

from __future__ import annotations

from src.engine.config import CONFIG
from src.engine.search.base import SearchProvider, SearchResult
from src.engine.security import get_shared_http_client


class BraveSearchProvider(SearchProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    @property
    def name(self) -> str:
        return "brave"

    async def search(
        self,
        query: str,
        count: int = 5,
        time_filter: str | None = None,
        domains: list[str] | None = None
    ) -> list[SearchResult]:
        if not self.api_key:
            return []

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
            "User-Agent": CONFIG.user_agent
        }
        params: dict[str, str | int] = {"q": query, "count": count}
        if time_filter:
            params["freshness"] = time_filter

        try:
            client = await get_shared_http_client()
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params=params,
                headers=headers,
                timeout=CONFIG.read_timeout,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
        except Exception:
            return []

        web_results = data.get("web", {}).get("results", [])
        results: list[SearchResult] = []
        for r in web_results:
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("description", ""),
                source_date=r.get("page_age"),
                provider=self.name
            ))
        return results

class SearXNGProvider(SearchProvider):
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    @property
    def name(self) -> str:
        return "searxng"

    async def search(
        self,
        query: str,
        count: int = 5,
        time_filter: str | None = None,
        domains: list[str] | None = None
    ) -> list[SearchResult]:
        if not self.base_url:
            return []

        params = {
            "q": query,
            "format": "json"
        }
        if time_filter:
            params["time_range"] = time_filter

        try:
            client = await get_shared_http_client()
            resp = await client.get(
                f"{self.base_url}/search",
                params=params,
                timeout=CONFIG.read_timeout,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
        except Exception:
            return []

        results: list[SearchResult] = []
        for r in data.get("results", []):
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("content", ""),
                provider=self.name
            ))
            if len(results) >= count:
                break
        return results
