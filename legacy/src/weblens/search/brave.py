"""Brave Search API adapter (official, key required)."""

from __future__ import annotations

from urllib.parse import quote_plus

from ..errors import ErrCode, FetchError, ProviderError
from ..net import SafeFetcher
from .base import Hit, make_hit, parse_date

_FRESH = {"day": "pd", "week": "pw", "month": "pm", "year": "py"}


class BraveSearch:
    name = "brave"
    # Match the keyed-provider transport budget. Brave's first cold request
    # also pays TLS setup; this is a deadline, not a latency claim.
    timeout_s = 8.0

    def __init__(self, fetcher: SafeFetcher, api_key: str):
        self.fetcher = fetcher
        self.api_key = api_key
        if not api_key:
            raise ProviderError("BRAVE_API_KEY is not set", code=ErrCode.NO_PROVIDER)

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
        url = (
            f"https://api.search.brave.com/res/v1/web/search?q={quote_plus(q)}"
            f"&count={min(20, max(5, k))}&text_decorations=false&result_filter=web"
        )
        if freshness in _FRESH:
            url += f"&freshness={_FRESH[freshness]}"
        try:
            resp = await self.fetcher.fetch(
                url,
                headers={
                    "X-Subscription-Token": self.api_key,
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                },
                cache_ttl=300,
                max_bytes=2_000_000,
            )
        except FetchError as exc:
            if exc.status == 429:
                raise ProviderError("brave rate limited", code=ErrCode.PROVIDER, retryable=True) from exc
            if exc.status == 401:
                raise ProviderError("brave rejected the API key", code=ErrCode.PROVIDER) from exc
            raise ProviderError(f"brave fetch failed: {exc.message}", code=ErrCode.PROVIDER) from exc
        try:
            data = resp.json()
        except ValueError as e:
            raise ProviderError("brave returned invalid JSON", code=ErrCode.PROVIDER) from e
        hits: list[Hit] = []
        for i, item in enumerate((data.get("web") or {}).get("results") or []):
            if len(hits) >= k:
                break
            hit = make_hit(
                item.get("title", ""),
                item.get("url", ""),
                item.get("description", ""),
                provider=self.name,
                rank=i,
                date_hint=item.get("page_age") or item.get("age") or "",
            )
            if hit:
                hits.append(hit)
        return hits


def _iso(value: str | None) -> str | None:
    return parse_date(value)
