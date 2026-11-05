"""
High-Speed Live Web Search Provider via Bing.

Uses the light RSS endpoint first (pinned to the en-US market: without the
market parameters Bing serves locale-poisoned results such as Hindi news or
currency pages for English technical queries). Falls back to the HTML SERP when
RSS is unavailable so the provider degrades instead of failing.
"""

from __future__ import annotations

import base64
import html as html_lib
import re

try:
    from defusedxml.ElementTree import ParseError as XMLParseError
    from defusedxml.ElementTree import fromstring as safe_xml_fromstring
except ImportError:
    from xml.etree.ElementTree import ParseError as XMLParseError  # type: ignore[no-redef] # nosec B405
    from xml.etree.ElementTree import fromstring as safe_xml_fromstring

from bs4 import BeautifulSoup

from src.engine.config import CONFIG
from src.engine.search.base import SearchProvider, SearchResult
from src.engine.security import get_shared_http_client

_MARKET = {"mkt": "en-US", "setlang": "en-US", "cc": "US"}
_HEADERS = {
    "User-Agent": CONFIG.user_agent,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _clean_text(value: str) -> str:
    return BeautifulSoup(html_lib.unescape(value or ""), "html.parser").get_text(" ", strip=True)


def _decode_bing_url(raw_href: str) -> str:
    if "u=a1" not in raw_href:
        return raw_href
    try:
        encoded = raw_href.split("u=a1", 1)[1].split("&", 1)[0]
        padded = encoded + "=" * (-len(encoded) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
        return decoded if decoded.startswith("http") else raw_href
    except Exception:
        return raw_href


def _published(value: str) -> str | None:
    if not value:
        return None
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(value).date().isoformat()
    except Exception:
        return None


class BingSearchProvider(SearchProvider):
    @property
    def name(self) -> str:
        return "bing"

    def _effective_query(
        self,
        query: str,
        domains: list[str] | None,
    ) -> str:
        if not domains:
            return query
        filters = " OR ".join(f"site:{domain.strip()}" for domain in domains if domain.strip())
        return f"{query} ({filters})" if filters else query

    async def search(
        self,
        query: str,
        count: int = 5,
        time_filter: str | None = None,
        domains: list[str] | None = None,
    ) -> list[SearchResult]:
        effective_query = self._effective_query(query, domains)
        wanted = max(count, 8)
        try:
            client = await get_shared_http_client()
        except Exception:
            return []

        try:
            response = await client.get(
                "https://www.bing.com/search",
                params={"q": effective_query, "format": "rss", "count": str(wanted), **_MARKET},
                headers=_HEADERS,
                timeout=6.0,
                follow_redirects=True,
            )
            if response.status_code == 200:
                parsed = self._parse_rss(response.text, count)
                if parsed:
                    return parsed
        except Exception:
            parsed = []

        try:
            response = await client.get(
                "https://www.bing.com/search",
                params={"q": effective_query, "count": str(wanted), **_MARKET},
                headers=_HEADERS,
                timeout=6.0,
                follow_redirects=True,
            )
            if response.status_code != 200:
                return []
            return self._parse_html(response.text, count)
        except Exception:
            return []

    @staticmethod
    def _parse_rss(document: str, count: int) -> list[SearchResult]:
        payload = (document or "").lstrip("\ufeff \r\n\t")
        if not payload.startswith("<?xml"):
            return []
        try:
            root = safe_xml_fromstring(payload)  # nosec B314
        except XMLParseError:
            return []
        results: list[SearchResult] = []
        for item in root.iter("item"):
            title = _clean_text(item.findtext("title") or "")
            url = _decode_bing_url((item.findtext("link") or "").strip())
            snippet = _clean_text(item.findtext("description") or "")
            if not title or not url.startswith("http"):
                continue
            # RSS descriptions occasionally embed the title again as a prefix.
            snippet = re.sub(rf"^{re.escape(title)}\s*", "", snippet).strip()
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source_date=_published(item.findtext("pubDate") or ""),
                    provider="bing",
                )
            )
            if len(results) >= count:
                break
        return results

    @staticmethod
    def _parse_html(document: str, count: int) -> list[SearchResult]:
        soup = BeautifulSoup(document, "html.parser")
        results: list[SearchResult] = []
        for item in soup.select("li.b_algo"):
            heading = item.select_one("h2 a")
            if heading is None:
                continue
            title = heading.get_text(" ", strip=True)
            raw_href = heading.get("href", "")
            href = raw_href if isinstance(raw_href, str) else (raw_href[0] if raw_href else "")
            url = _decode_bing_url(href)
            snippet_node = item.select_one(".b_caption p")
            snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""
            if title and url.startswith("http"):
                results.append(SearchResult(title=title, url=url, snippet=snippet, provider="bing"))
            if len(results) >= count:
                break
        return results
