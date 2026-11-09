"""SearXNG adapter (self-hosted, official JSON API).

Public instances usually disable the JSON output; point WEBLENS_SEARXNG_URL at
your own instance. Example docker command is in the README.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from ..errors import ErrCode, FetchError, ProviderError
from ..net import SafeFetcher
from .base import Hit, make_hit

_FRESH = {"day": "day", "week": "week", "month": "month", "year": "year"}


class SearXNGSsearch:
    name = "searxng"

    def __init__(self, fetcher: SafeFetcher, base_url: str | None):
        if not base_url:
            raise ProviderError("WEBLENS_SEARXNG_URL is not set", code=ErrCode.NO_PROVIDER)
        self.fetcher = fetcher
        self.base = base_url.rstrip("/")

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
        url = f"{self.base}/search?q={quote_plus(q)}&format=json&language=en"
        if freshness in _FRESH:
            url += f"&time_range={_FRESH[freshness]}"
        try:
            resp = await self.fetcher.fetch(
                url,
                headers={"Accept": "application/json"},
                cache_ttl=300,
                max_bytes=2_000_000,
            )
        except FetchError as exc:
            if exc.status == 429:
                raise ProviderError("searxng rate-limited the request", code=ErrCode.PROVIDER, retryable=True) from exc
            raise ProviderError(f"searxng fetch failed: {exc.message}", code=ErrCode.PROVIDER) from exc
        ctype = resp.content_type
        if "json" not in ctype:
            raise ProviderError(
                "searxng did not return JSON (format=json may be disabled)",
                code=ErrCode.PROVIDER,
            )
        try:
            data = resp.json()
        except ValueError as e:
            raise ProviderError("searxng returned invalid JSON", code=ErrCode.PROVIDER) from e
        hits: list[Hit] = []
        for i, item in enumerate(data.get("results") or []):
            if len(hits) >= k:
                break
            hit = make_hit(
                item.get("title", ""),
                item.get("url", ""),
                item.get("content", ""),
                provider=self.name,
                rank=i,
                date_hint=item.get("publishedDate") or "",
            )
            if hit:
                hits.append(hit)
        return hits
