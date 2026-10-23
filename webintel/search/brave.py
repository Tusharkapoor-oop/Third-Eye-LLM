"""Brave Search API adapter (requires BRAVE_SEARCH_API_KEY). Independent index;
free data tier: ~1 request/s, quota resets monthly (verify at signup)."""
from __future__ import annotations

import time

import httpx

from ..security import UnsafeURLError, validate_url
from ..utils import normalize_url
from .base import ProviderResult, SearchHit
from urllib.parse import urlencode


class BraveProvider:
    id = "brave"

    def __init__(self, pool, api_key: str) -> None:
        self._pool = pool
        self._key = api_key

    async def search(self, query: str, *, max_results: int, freshness_days, allowed_domains) -> ProviderResult:
        t0 = time.perf_counter()
        params = {"q": query, "count": str(max(3, min(10, max_results))), "country": "all"}
        if freshness_days:
            from datetime import datetime, timedelta, timezone
            dt = datetime.now(timezone.utc) - timedelta(days=freshness_days)
            params["freshness_date"] = dt.strftime("%Y-%m-%d")
        url = "https://api.search.brave.com/res/v1/web/search?" + urlencode(params)
        if allowed_domains:
            q = params.get("q", "") + " (" + " OR ".join("site:" + d for d in allowed_domains[:3]) + ")"
            url = "https://api.search.brave.com/res/v1/web/search?" + urlencode({**params, "q": q})
        try:
            res = await self._pool.client.get(
                url, headers={"X-Subscription-Token": self._key, "Accept": "application/json"})
        except httpx.TimeoutException:
            return ProviderResult(self.id, "provider_error", [], url, "timeout", (time.perf_counter()-t0)*1000)
        if res.status_code != 200:
            return ProviderResult(self.id, "provider_error", [], url, f"HTTP {res.status_code}",
                                  (time.perf_counter()-t0)*1000)
        data = res.json()
        hits = []
        for rank, r in enumerate((data.get("web") or {}).get("results", [])[:max_results]):
            try:
                u = normalize_url(validate_url(r.get("url", "")))
            except (UnsafeURLError, ValueError):
                continue
            hits.append(SearchHit(provider=self.id, url=u, title=(r.get("title") or "").strip(),
                                  snippet=(r.get("description") or "")[:320],
                                  date=r.get("age", ""), provider_rank=rank + 1))
        return ProviderResult(self.id, "ok" if hits else "no_results", hits, url, "",
                              (time.perf_counter()-t0)*1000)
