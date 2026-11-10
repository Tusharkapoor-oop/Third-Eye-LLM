"""
Wikipedia Factual Reference Search Provider.
Provides authoritative, high-density factual information with zero rate limits or API key requirements.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from src.engine.config import CONFIG
from src.engine.search.base import SearchProvider, SearchResult
from src.engine.security import get_shared_http_client


class WikipediaSearchProvider(SearchProvider):
    @property
    def name(self) -> str:
        return "wikipedia"

    async def search(
        self,
        query: str,
        count: int = 5,
        time_filter: str | None = None,
        domains: list[str] | None = None
    ) -> list[SearchResult]:
        # Compliant User-Agent required by Wikimedia API policy
        headers = {"User-Agent": "WebIntelEngine/1.0 (https://github.com/autonomous-ai/web-intel; contact@local.dev)"}
        params: dict[str, str | int] = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": count,
            "format": "json"
        }

        try:
            client = await get_shared_http_client()
            resp = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params=params,
                headers=headers,
                timeout=CONFIG.read_timeout,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
        except Exception:
            return []

        search_items = data.get("query", {}).get("search", [])
        results: list[SearchResult] = []
        for item in search_items:
            title = item.get("title", "")
            snippet_html = item.get("snippet", "")
            # Strip HTML tags like <span class="searchmatch">
            clean_snippet = BeautifulSoup(snippet_html, "html.parser").get_text(strip=True)
            timestamp = item.get("timestamp")
            page_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"

            results.append(SearchResult(
                title=title,
                url=page_url,
                snippet=clean_snippet,
                source_date=timestamp,
                provider=self.name
            ))

        return results
