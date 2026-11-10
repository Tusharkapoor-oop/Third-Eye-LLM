"""
Direct DuckDuckGo Lite & HTML Fallback Search Provider.
Uses direct HTTP POST to lite.duckduckgo.com and html.duckduckgo.com
for ultra-fast (sub-1.5s), reliable live search without API key dependencies.
"""

from __future__ import annotations

from urllib.parse import unquote

from bs4 import BeautifulSoup

from src.engine.config import CONFIG
from src.engine.search.base import SearchProvider, SearchResult
from src.engine.security import get_shared_http_client


class DDGHTMLSearchProvider(SearchProvider):
    @property
    def name(self) -> str:
        return "ddg_html"

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
        data = {"q": effective_query, "b": ""}
        if time_filter:
            time_map = {"day": "d", "d": "d", "week": "w", "w": "w", "month": "m", "m": "m"}
            tf = time_map.get(time_filter.lower())
            if tf:
                data["df"] = tf

        results: list[SearchResult] = []

        # 1. Try DuckDuckGo Lite first (lowest latency ~1.2s)
        try:
            client = await get_shared_http_client()
            resp = await client.post(
                "https://lite.duckduckgo.com/lite/",
                data=data,
                headers=headers,
                timeout=CONFIG.read_timeout,
                follow_redirects=True,
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for tr in soup.select("table tr"):
                    a = tr.select_one("a.result-link")
                    if not a:
                        continue
                    val = a.get("href", "")
                    raw_href = val if isinstance(val, str) else (val[0] if isinstance(val, list) and val else "")
                    if "uddg=" in raw_href:
                        try:
                            actual_url = unquote(raw_href.split("uddg=")[1].split("&")[0])
                        except Exception:
                            actual_url = raw_href
                    else:
                        actual_url = raw_href

                    title = a.get_text(strip=True)
                    snippet_tr = tr.find_next_sibling("tr")
                    snippet = snippet_tr.get_text(strip=True) if snippet_tr else ""

                    if title and actual_url.startswith("http"):
                        results.append(SearchResult(
                            title=title,
                            url=actual_url,
                            snippet=snippet,
                            provider=self.name
                        ))
                    if len(results) >= count:
                        break
        except Exception:
            pass

        if len(results) >= count:
            return results

        # 2. Try DuckDuckGo HTML if Lite returned 0
        if not results:
            try:
                client = await get_shared_http_client()
                resp = await client.post(
                    "https://html.duckduckgo.com/html/",
                    data=data,
                    headers=headers,
                    timeout=CONFIG.read_timeout,
                    follow_redirects=True,
                )
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for body_elem in soup.select(".result__body"):
                        title_elem = body_elem.select_one(".result__title a")
                        snippet_elem = body_elem.select_one(".result__snippet")
                        if not title_elem:
                            continue

                        val = title_elem.get("href", "")
                        raw_href = val if isinstance(val, str) else (val[0] if isinstance(val, list) and val else "")
                        if "uddg=" in raw_href:
                            try:
                                actual_url = unquote(raw_href.split("uddg=")[1].split("&")[0])
                            except Exception:
                                actual_url = raw_href
                        else:
                            actual_url = raw_href

                        title = title_elem.get_text(strip=True)
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
            except Exception:
                pass

        return results
