"""Tavily adapter. Provider relevance scores are deliberately discarded (R2)."""

from __future__ import annotations

from ..errors import ErrCode, FetchError, ProviderError
from ..net import SafeFetcher
from .base import Hit, make_hit

_FRESH = {"day": "day", "week": "week", "month": "month", "year": "year"}


class TavilySearch:
    name = "tavily"
    # A cold TLS/DNS setup can exceed the generic 3.5 s fallback. The first
    # live request measured 5.1 s; subsequent requests were sub-second.
    timeout_s = 8.0

    def __init__(self, fetcher: SafeFetcher, api_key: str):
        self.fetcher = fetcher
        self.api_key = api_key
        if not api_key:
            raise ProviderError("TAVILY_API_KEY is not set", code=ErrCode.NO_PROVIDER)

    async def search(
        self,
        query: str,
        *,
        k: int = 5,
        freshness: str | None = None,
        domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[Hit]:
        body: dict[str, object] = {
            "query": query,
            "max_results": min(20, max(1, k)),
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
            "include_published_date": True,
            "topic": "general",
        }
        if freshness in _FRESH:
            body["time_range"] = _FRESH[freshness]
        if domains:
            body["include_domains"] = domains[:20]
        if exclude_domains:
            body["exclude_domains"] = exclude_domains[:20]

        try:
            resp = await self.fetcher.fetch(
                "https://api.tavily.com/search",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                },
                json_body=body,
                method="POST",
                cache_ttl=300,
                max_bytes=2_000_000,
            )
        except FetchError as exc:
            if exc.status == 429:
                raise ProviderError("tavily rate limited", code=ErrCode.PROVIDER, retryable=True) from exc
            if exc.status in (401, 403):
                raise ProviderError("tavily rejected the API key", code=ErrCode.PROVIDER) from exc
            raise ProviderError(f"tavily fetch failed: {exc.message}", code=ErrCode.PROVIDER) from exc
        try:
            data = resp.json()
        except ValueError as e:
            raise ProviderError("tavily returned invalid JSON", code=ErrCode.PROVIDER) from e

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
                date_hint=item.get("published_date") or "",
            )
            if hit:
                hits.append(hit)
        return hits
