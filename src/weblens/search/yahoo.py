"""Yahoo Search HTML adapter (keyless, best effort).

Yahoo's public result page is useful as a second independent web index when
DuckDuckGo is rate-limited. The markup is not a stable API contract; results are
cached and failures are isolated by the router.
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus, unquote, urlsplit

from lxml import html as lxml_html

from ..errors import ErrCode, ProviderError
from ..net import SafeFetcher
from .base import Hit, make_hit

_FRESH = {"day": "d", "week": "w", "month": "m", "year": "y"}


def unwrap(href: str) -> str:
    """Resolve Yahoo's ``r.search.yahoo.com`` redirect wrapper."""
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    try:
        parts = urlsplit(href)
    except ValueError:
        return href
    if "search.yahoo.com" not in (parts.hostname or ""):
        return href
    # Yahoo encodes the destination as a path segment: .../RU=<percent-encoded>/RK=...
    match = re.search(r"/RU=([^/]+)", parts.path)
    if match:
        return unquote(match.group(1))
    return href


class YahooSearch:
    name = "yahoo"
    timeout_s = 4.0

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
        url = f"https://search.yahoo.com/search?p={quote_plus(q)}&ei=UTF-8"
        if freshness in _FRESH:
            url += f"&btf={_FRESH[freshness]}"

        resp = await self.fetcher.fetch(
            url,
            headers={"Accept": "text/html"},
            cache_ttl=600,
            max_bytes=1_500_000,
        )
        if resp.status in {403, 429} or "unusual traffic" in resp.text.lower():
            raise ProviderError("yahoo rate-limited the request", code=ErrCode.PROVIDER, retryable=True)
        try:
            doc = lxml_html.fromstring(resp.text)
        except (ValueError, TypeError) as e:
            raise ProviderError("yahoo HTML parse failed", code=ErrCode.PROVIDER) from e

        hits: list[Hit] = []
        for i, block in enumerate(doc.cssselect("div.algo")):
            if len(hits) >= k:
                break
            title_node = block.cssselect("h3")
            links = block.cssselect("a[href]")
            if not title_node or not links:
                continue
            title = " ".join(title_node[0].text_content().split())
            href = unwrap(links[0].get("href", ""))
            snippet_node = block.cssselect(".compText")
            snippet = ""
            if snippet_node:
                snippet = " ".join(snippet_node[0].text_content().split())
            hit = make_hit(title, href, snippet, provider=self.name, rank=i)
            if hit:
                hits.append(hit)
        if not hits and ("No results" in resp.text or "We did not find results" in resp.text):
            return []
        if not hits:
            raise ProviderError("yahoo returned no parseable results", code=ErrCode.PROVIDER)
        return hits
