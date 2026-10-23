"""Mwmbl search adapter (keyless, open-source index).

Mwmbl is a small community search engine. Its JSON API returns title and
extract fields as arrays of ``{value, is_bold}`` segments rather than plain
strings. Results are sparse for some queries, so this provider is a fallback
rather than a primary engine.

Endpoint: https://api.mwmbl.org/search/?s=<query>
"""

from __future__ import annotations

from urllib.parse import quote_plus

from ..errors import ErrCode, ProviderError
from ..net import SafeFetcher
from .base import Hit, make_hit


def _segments_text(value: object) -> str:
    """Join Mwmbl's segment arrays (or tolerate a plain string)."""
    if isinstance(value, str):
        return " ".join(value.split())
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for segment in value:
        if isinstance(segment, dict):
            text = segment.get("value")
            if isinstance(text, str):
                parts.append(text)
        elif isinstance(segment, str):
            parts.append(segment)
    return " ".join("".join(parts).split())


class MwmblSearch:
    name = "mwmbl"
    timeout_s = 2.5

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
        # Mwmbl has no site: operator, so domain constraints are enforced by
        # the router after retrieval.
        if domains or exclude_domains:
            pass
        url = f"https://api.mwmbl.org/search/?s={quote_plus(query)}"
        resp = await self.fetcher.fetch(
            url,
            headers={"Accept": "application/json"},
            cache_ttl=600,
            max_bytes=1_500_000,
        )
        try:
            data = resp.json()
        except ValueError as e:
            raise ProviderError("mwmbl returned invalid JSON", code=ErrCode.PROVIDER) from e
        if not isinstance(data, list):
            raise ProviderError("mwmbl returned an unexpected payload", code=ErrCode.PROVIDER)

        hits: list[Hit] = []
        seen: set[str] = set()
        for item in data:
            if len(hits) >= k:
                break
            if not isinstance(item, dict):
                continue
            title = _segments_text(item.get("title"))
            snippet = _segments_text(item.get("extract"))
            target = item.get("url")
            if not isinstance(target, str):
                continue
            hit = make_hit(title, target, snippet, provider=self.name, rank=len(hits))
            if hit is None or hit.url in seen:
                continue
            seen.add(hit.url)
            hits.append(hit)
        return hits
