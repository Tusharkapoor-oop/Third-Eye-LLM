"""DuckDuckGo Lite adapter (keyless, best effort).

This parses the lightweight HTML endpoint. It is rate-limited and cached. The
markup is not a stable public contract; use the Brave API or a self-hosted
SearXNG instance when reliability matters.
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import parse_qs, quote_plus, urlsplit

from lxml import html as lxml_html

from ..errors import ErrCode, ProviderError
from ..net import SafeFetcher
from .base import Hit, make_hit

_FRESH = {"day": "d", "week": "w", "month": "m", "year": "y"}


def unwrap(href: str) -> str:
    """Resolve DDG's /l/?uddg= redirect wrapper."""
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    try:
        p = urlsplit(href)
    except ValueError:
        return href
    if "duckduckgo.com" in (p.hostname or "") and p.path.startswith("/l/"):
        q = parse_qs(p.query)
        if q.get("uddg"):
            return q["uddg"][0]
    return href


class DuckDuckGoLite:
    name = "ddg"
    timeout_s = 3.5
    _last_call = 0.0
    _lock = asyncio.Lock()
    _min_interval = 1.5

    def __init__(self, fetcher: SafeFetcher):
        self.fetcher = fetcher

    async def search(
        self,
        query: str,
        *,
        k: int = 5,
        freshness: str | None = None,
        domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[Hit]:
        q = query
        if domains:
            q += " (" + " OR ".join(f"site:{d}" for d in domains[:6]) + ")"
        if exclude_domains:
            q += "".join(f" -site:{d}" for d in exclude_domains[:6])
        url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(q)}&kl=us-en"
        if freshness in _FRESH:
            url += f"&df={_FRESH[freshness]}"

        async with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            # Reserve the slot before fetching so concurrent research queries
            # are spaced by start time instead of serializing whole requests.
            self._last_call = time.monotonic()

        resp = await self.fetcher.fetch(
            url,
            headers={"Accept": "text/html"},
            cache_ttl=600,
            max_bytes=1_500_000,
        )

        if resp.status == 202 or "anomaly-modal" in resp.text or "bots use DuckDuckGo" in resp.text:
            raise ProviderError("ddg returned a bot challenge", code=ErrCode.PROVIDER, retryable=True)
        try:
            doc = lxml_html.fromstring(resp.text)
        except (ValueError, TypeError) as e:
            raise ProviderError("ddg HTML parse failed", code=ErrCode.PROVIDER) from e

        anchors = doc.cssselect("a.result-link")
        snippets = doc.cssselect("td.result-snippet")
        hits: list[Hit] = []
        for i, a in enumerate(anchors):
            if len(hits) >= k:
                break
            href = unwrap(a.get("href", ""))
            title = " ".join(a.text_content().split())
            snippet = ""
            if i < len(snippets):
                snippet = " ".join(snippets[i].text_content().split())
            hit = make_hit(title, href, snippet, provider=self.name, rank=i)
            if hit:
                hits.append(hit)
        if not hits and "No results." in resp.text:
            return []
        if not hits:
            raise ProviderError("ddg returned no parseable results", code=ErrCode.PROVIDER)
        return hits
