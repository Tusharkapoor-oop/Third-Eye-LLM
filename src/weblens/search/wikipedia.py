"""Wikipedia search adapter (official MediaWiki API, keyless).

Used as a last-resort provider for encyclopedic queries. It is not a general
web search engine and is labelled as such in provenance.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from ..errors import ErrCode, ProviderError
from ..net import SafeFetcher
from .base import Hit, clean_snippet, make_hit


class WikipediaSearch:
    name = "wikipedia"

    def __init__(self, fetcher: SafeFetcher, lang: str = "en"):
        self.fetcher = fetcher
        self.lang = lang

    async def search(
        self,
        query: str,
        *,
        k: int = 5,
        freshness: str | None = None,
        domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[Hit]:
        if domains and not any(d.endswith("wikipedia.org") for d in domains):
            return []
        url = (
            f"https://{self.lang}.wikipedia.org/w/api.php?action=query&list=search"
            f"&srsearch={quote(query)}&srlimit={min(10, max(1, k))}"
            "&srprop=snippet%7Ctimestamp&format=json&formatversion=2&origin=*"
        )
        resp = await self.fetcher.fetch(
            url,
            headers={"Accept": "application/json"},
            cache_ttl=1800,
            max_bytes=1_000_000,
        )
        try:
            data = resp.json()
        except ValueError as e:
            raise ProviderError("wikipedia returned invalid JSON", code=ErrCode.PROVIDER) from e
        if "error" in data:
            raise ProviderError("wikipedia API error", code=ErrCode.PROVIDER)
        hits: list[Hit] = []
        for i, item in enumerate((data.get("query") or {}).get("search") or []):
            if len(hits) >= k:
                break
            title = item.get("title", "")
            snippet = clean_snippet(re.sub(r"<[^>]+>", " ", item.get("snippet", "")))
            hit = make_hit(
                title,
                f"https://{self.lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
                snippet,
                provider=self.name,
                rank=i,
                date_hint=item.get("timestamp", ""),
            )
            if hit:
                hits.append(hit)
        return hits
