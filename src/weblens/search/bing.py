"""Bing HTML adapter (keyless, best effort).

Microsoft retired the Bing Search APIs, so this adapter parses the public
results page. It is rate-limited, cached, and treated as a fallback: HTML
markup can change without notice. Use Brave/Tavily/SearXNG for production.
"""

from __future__ import annotations

import asyncio
from urllib.parse import quote_plus

from lxml import html as lxml_html

from ..errors import ErrCode, ProviderError
from ..net import SafeFetcher
from ..urls import decode_bing_redirect
from .base import Hit, make_hit

_FRESH = {
    "day": "+filterui:age-lt1440",
    "week": "+filterui:age-lt10080",
    "month": "+filterui:age-lt43200",
    "year": "+filterui:age-lt525600",
}


class BingHTML:
    name = "bing"
    _last_call = 0.0
    _lock = asyncio.Lock()
    _min_interval = 1.2

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
        url = "https://www.bing.com/search?q=" + quote_plus(q) + f"&count={max(10, k)}&setlang=en&cc=us"
        if freshness in _FRESH:
            url += "&qft=" + quote_plus(_FRESH[freshness])

        async with self._lock:
            import time

            wait = self._min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                resp = await self.fetcher.fetch(
                    url,
                    headers={"Accept": "text/html,application/xhtml+xml"},
                    cache_ttl=600,
                    max_bytes=1_500_000,
                )
            finally:
                self._last_call = time.monotonic()

        if "anomaly-modal" in resp.text or "challenge-form" in resp.text:
            raise ProviderError("bing returned a bot challenge", code=ErrCode.PROVIDER)
        try:
            doc = lxml_html.fromstring(resp.text)
        except (ValueError, TypeError) as e:
            raise ProviderError("bing HTML parse failed", code=ErrCode.PROVIDER) from e

        hits: list[Hit] = []
        for i, li in enumerate(doc.cssselect("li.b_algo")):
            if len(hits) >= k:
                break
            a = li.cssselect("h2 a")
            if not a:
                continue
            href = a[0].get("href", "")
            href = decode_bing_redirect(href)
            title = a[0].text_content()
            snip_el = li.cssselect(".b_caption p, p")
            snippet = snip_el[0].text_content() if snip_el else ""
            date_el = li.cssselect(".news_dt, .b_attribution")
            date_hint = date_el[0].text_content() if date_el else ""
            hit = make_hit(
                title,
                href,
                snippet,
                provider=self.name,
                rank=i,
                date_hint=date_hint,
            )
            if hit:
                hits.append(hit)
        # Some layouts move the visible URL into <cite>; nothing else to mine.
        if not hits and "b_no" in resp.text:
            return []
        return hits


def decode_redirect(url: str) -> str:  # re-exported for tests
    return decode_bing_redirect(url)
