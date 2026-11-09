"""Yahoo Search HTML adapter (keyless, best effort).

Yahoo's public result page is useful as a second independent web index when
DuckDuckGo is rate-limited. The markup is not a stable API contract; results are
cached and failures are isolated by the router.
"""

from __future__ import annotations

import asyncio
import re
from urllib.parse import quote_plus, unquote, urlsplit

from lxml import html as lxml_html

from ..errors import ErrCode, FetchError, ProviderError
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

        # Yahoo's US and Japanese edges intermittently return different result
        # sets (or HTTP 500) for the same query. Query both in parallel and
        # merge by URL; this is deterministic and avoids losing an official
        # documentation page merely because one edge omitted it.
        hosts = ("https://search.yahoo.com/search", "https://search.yahoo.co.jp/search")
        results = await asyncio.gather(
            *(self._fetch_host(base, q, freshness, k) for base in hosts),
            return_exceptions=True,
        )
        from ..urls import document_canonical_key

        best: dict[str, Hit] = {}
        errors: list[BaseException] = []
        for result in results:
            if isinstance(result, BaseException):
                errors.append(result)
                continue
            for hit in result:
                key = document_canonical_key(hit.url)
                prev = best.get(key)
                if prev is None:
                    best[key] = hit
                elif hit.rank < prev.rank:
                    if len(prev.snippet) > len(hit.snippet):
                        hit.snippet = prev.snippet
                    best[key] = hit
                elif len(hit.snippet) > len(prev.snippet):
                    prev.snippet = hit.snippet

        hits = sorted(best.values(), key=lambda h: (h.rank, h.url))[:k]
        for i, hit in enumerate(hits):
            hit.rank = i
        if hits:
            return hits
        provider_error = next((e for e in errors if isinstance(e, ProviderError)), None)
        if provider_error is not None:
            raise provider_error
        if errors:
            raise ProviderError("yahoo search failed", code=ErrCode.PROVIDER) from errors[0]
        return []

    async def _fetch_host(self, base: str, q: str, freshness: str | None, k: int) -> list[Hit]:
        url = f"{base}?p={quote_plus(q)}&ei=UTF-8"
        if freshness in _FRESH:
            url += f"&btf={_FRESH[freshness]}"
        try:
            resp = await self.fetcher.fetch(
                url,
                headers={"Accept": "text/html"},
                cache_ttl=600,
                max_bytes=1_500_000,
            )
        except FetchError as exc:
            if exc.status == 429:
                raise ProviderError("yahoo rate-limited the request", code=ErrCode.PROVIDER, retryable=True) from exc
            if exc.status in (401, 403):
                # Yahoo blocks/deprecates some clients outright; retrying on the
                # same response key would just burn another request.
                raise ProviderError("yahoo blocked the request", code=ErrCode.PROVIDER) from exc
            raise ProviderError("yahoo fetch failed", code=ErrCode.PROVIDER, retryable=True) from exc
        if "unusual traffic" in resp.text.lower():
            raise ProviderError("yahoo rate-limited the request", code=ErrCode.PROVIDER, retryable=True)
        hits = self._parse(resp.text, k)
        if hits:
            return hits
        if "No results" in resp.text or "We did not find results" in resp.text:
            return []
        raise ProviderError("yahoo returned no parseable results", code=ErrCode.PROVIDER)

    def _parse(self, text: str, k: int) -> list[Hit]:
        try:
            doc = lxml_html.fromstring(text)
        except (ValueError, TypeError) as e:
            raise ProviderError("yahoo HTML parse failed", code=ErrCode.PROVIDER) from e

        hits: list[Hit] = []
        # US/global markup.
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
            snippet = " ".join(snippet_node[0].text_content().split()) if snippet_node else ""
            hit = make_hit(title, href, snippet, provider=self.name, rank=i)
            if hit:
                hits.append(hit)

        # Japanese edge markup.
        if not hits:
            for i, block in enumerate(doc.cssselect("div.sw-Card.Algo")):
                if len(hits) >= k:
                    break
                title_node = block.cssselect("h3.sw-Card__titleMain") or block.cssselect("h3")
                links = block.cssselect("a[href]")
                if not title_node or not links:
                    continue
                title = " ".join(title_node[0].text_content().split())
                href = unwrap(links[0].get("href", ""))
                snippet_node = block.cssselect("p.sw-Card__summary") or block.cssselect(".sw-Card__summary")
                snippet = " ".join(snippet_node[0].text_content().split()) if snippet_node else ""
                hit = make_hit(title, href, snippet, provider=self.name, rank=i)
                if hit:
                    hits.append(hit)
        return hits
