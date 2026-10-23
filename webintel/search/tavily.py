"""Tavily adapter (requires TAVILY_API_KEY). Basic search = 1 credit (docs, verified
2026-10-20: 1000 credits/mo free, $0.008/credit). We use basic depth only, request
no auto answer generation (tokens), no raw_content. Tavily is the evaluation
baseline (R2 comparisons)."""
from __future__ import annotations

import time
from typing import Optional

import httpx

from ..security import UnsafeURLError, validate_url
from ..utils import normalize_url
from .base import ProviderResult, SearchHit

class TavilyProvider:
    id = "tavily"

    def __init__(self, pool, api_key: str) -> None:
        self._pool = pool
        self._key = api_key

    async def search(self, query: str, *, max_results: int, freshness_days: Optional[int],
                     allowed_domains: Optional[List[str]]) -> ProviderResult:
        t0 = time.perf_counter()
        body: dict = {
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }
        if allowed_domains:
            body["include_domains"] = list(allowed_domains)[:4]
        if freshness_days:
            body["days"] = int(freshness_days)
        try:
            res = await self._pool.client.post(
                "https://api.tavily.com/search",
                json=body,
                headers={"Authorization": f"Bearer {self._key}"},
            )
        except httpx.TimeoutException:
            return ProviderResult(self.id, "provider_error", [], "https://api.tavily.com/search",
                                  "timeout", (time.perf_counter()-t0)*1000)
        if res.status_code != 200:
            err = f"HTTP {res.status_code}"
            try:
                err += " " + res.json().get("detail", "")
            except Exception:
                pass
            return ProviderResult(self.id, "provider_error", [], "https://api.tavily.com/search",
                                  err, (time.perf_counter()-t0)*1000)
        data = res.json()
        hits = []
        for rank, r in enumerate(data.get("results", [])[: max_results]):
            try:
                url = normalize_url(validate_url(r.get("url", "")))
            except (UnsafeURLError, ValueError):
                continue
            hits.append(SearchHit(provider=self.id, url=url,
                                  title=(r.get("title") or "").strip(),
                                  snippet=(r.get("content") or "")[:320],
                                  date="", provider_rank=rank + 1))
        return ProviderResult(self.id, "ok" if hits else "no_results", hits,
                              "https://api.tavily.com/search", "", (time.perf_counter()-t0)*1000)
