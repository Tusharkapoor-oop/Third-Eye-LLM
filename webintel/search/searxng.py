"""SearXNG adapter for self-hosted instances (SEARXNG_URL). Public instances are
hostile to programmatic use (measured 2026-10-20: JSON disabled/blocked on the
three largest) - this adapter is intended for your OWN instance only."""
from __future__ import annotations

import time

import httpx

from ..security import UnsafeURLError, validate_url
from ..utils import normalize_url
from .base import ProviderResult, SearchHit


class SearxngProvider:
    id = "searxng"

    def __init__(self, pool, base_url: str) -> None:
        self._pool = pool
        self._base = base_url.rstrip("/") + "/search"
        self._ok_format: str | None = None   # 'json' | 'html' autodetected once

    async def search(self, query: str, *, max_results: int, freshness_days, allowed_domains) -> ProviderResult:
        t0 = time.perf_counter()
        params = {"q": query, "language": "auto"}
        if allowed_domains:
            params["q"] = query + " (" + " OR ".join("site:" + d for d in allowed_domains[:3]) + ")"
        if self._ok_format == "json" or self._ok_format is None:
            try:
                res = await self._pool.client.get(self._base,
                                                  params={**params, "format": "json"})
                if res.status_code == 200 and (res.text[:1] == "{"):
                    self._ok_format = "json"
                    return self._from_json(res, t0, max_results)
                self._ok_format = "html"
            except httpx.TimeoutException:
                self._ok_format = None
                return ProviderResult(self.id, "provider_error", [], self._base, "timeout",
                                      (time.perf_counter()-t0)*1000)
        # HTML fallback (parse standard results list)
        res = await self._pool.client.get(self._base, params={**params, "format": "html"})
        if res.status_code != 200:
            return ProviderResult(self.id, "provider_error", [], self._base, f"HTTP {res.status_code}",
                                  (time.perf_counter()-t0)*1000)
        import re
        hits = []
        rank = 0
        for m in re.finditer(r'<article class="result[^>]*>.*?</article>', res.text, re.S):
            block = m.group(0)
            mu = re.search(r'<h3><a href="(http[^"]+)"', block)
            mt = re.search(r"<h3><a[^>]*>(.*?)</a>", block, re.S)
            if not mu:
                continue
            rank += 1
            try:
                u = normalize_url(validate_url(mu.group(1)))
            except (UnsafeURLError, ValueError):
                continue
            title = re.sub(r"<[^>]+>", "", mt.group(1)) if mt else ""
            hits.append(SearchHit(provider=self.id, url=u, title=title.strip(),
                                  snippet="", provider_rank=rank))
            if rank >= max_results:
                break
        return ProviderResult(self.id, "ok" if hits else "no_results", hits, self._base, "",
                              (time.perf_counter()-t0)*1000)

    def _from_json(self, res, t0, max_results) -> ProviderResult:
        hits = []
        for rank, r in enumerate(res.json().get("results", [])[:max_results]):
            try:
                u = normalize_url(validate_url(r.get("url", "")))
            except (UnsafeURLError, ValueError):
                continue
            hits.append(SearchHit(provider=self.id, url=u, title=(r.get("title") or "").strip(),
                                  snippet=(r.get("content") or "")[:320],
                                  date="", provider_rank=rank + 1))
        return ProviderResult(self.id, "ok" if hits else "no_results", hits, self._base, "",
                              (time.perf_counter()-t0)*1000)
