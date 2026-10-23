"""
High-Speed Live Web Search Provider via Bing.
Provides sub-second (p50 ~0.8s) live web search without requiring an API key.
Decodes target URLs from redirect payloads.
"""

from __future__ import annotations

import base64

import httpx
from bs4 import BeautifulSoup

from src.engine.config import CONFIG
from src.engine.search.base import SearchProvider, SearchResult


class BingSearchProvider(SearchProvider):
    @property
    def name(self) -> str:
        return "bing"

    async def search(
        self,
        query: str,
        count: int = 5,
        time_filter: str | None = None,
        domains: list[str] | None = None
    ) -> list[SearchResult]:
        effective_query = query
        if domains:
            domain_filter = " OR ".join(f"site:{d.strip()}" for d in domains if d.strip())
            if domain_filter:
                effective_query = f"{query} ({domain_filter})"

        headers = {
            "User-Agent": CONFIG.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        params = {"q": effective_query}

        try:
            async with httpx.AsyncClient(headers=headers, timeout=5.0, follow_redirects=True) as client:
                resp = await client.get("https://www.bing.com/search", params=params)
                if resp.status_code != 200:
                    return []
                html = resp.text
        except Exception:
            return []

        soup = BeautifulSoup(html, "html.parser")
        results: list[SearchResult] = []

        for li in soup.select("li.b_algo"):
            h2 = li.select_one("h2 a")
            snippet_elem = li.select_one(".b_caption p")
            if not h2:
                continue

            title = h2.get_text(strip=True)
            val = h2.get("href", "")
            raw_href = val if isinstance(val, str) else (val[0] if isinstance(val, list) and val else "")
            actual_url = raw_href

            # Decode target URL from Bing's u=a1<base64> parameter
            if "u=a1" in raw_href:
                try:
                    b64_part = raw_href.split("u=a1")[1].split("&")[0]
                    padded = b64_part + "=" * (-len(b64_part) % 4)
                    decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
                    if decoded.startswith("http"):
                        actual_url = decoded
                except Exception:
                    actual_url = raw_href

            snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

            if title and actual_url.startswith("http"):
                results.append(SearchResult(
                    title=title,
                    url=actual_url,
                    snippet=snippet,
                    provider=self.name
                ))
            if len(results) >= count:
                break

        return results
