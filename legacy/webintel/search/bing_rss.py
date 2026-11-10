"""Keyless SERP: Bing search RSS endpoint - measured evidence (docs/research.md,
2026-10-20): HTTP 200 + structured RSS on 3/3 query classes, ~1.5s, no API key.
UNOFFICIAL endpoint - reliability risk disclosed; it is the permanent fallback
behind keyed providers. pubDate here is crawl time, NOT content date, so this
provider never claims a date (R2).
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from html import unescape
from typing import List, Optional
from urllib.parse import urlencode

import httpx

from ..security import UnsafeURLError, validate_url
from ..utils import normalize_url
from .base import ProviderResult, SearchHit


class BingRssProvider:
    id = "bing_rss"

    def __init__(self, pool) -> None:
        self._pool = pool

    @staticmethod
    def _rss_url(query: str, max_results: int, allowed_domains: Optional[List[str]]) -> str:
        q = query
        if allowed_domains:
            doms = [d.strip().lower().split("/")[0] for d in allowed_domains[:3]]
            ops = " OR ".join(f"site:{d}" for d in doms)
            q = f"({ops}) {query}"
        from .base import build_bing_rss_url
        return build_bing_rss_url(q, max_results)

    async def search(self, query: str, *, max_results: int, freshness_days: Optional[int],
                     allowed_domains: Optional[List[str]]) -> ProviderResult:
        t0 = time.perf_counter()
        rss = self._rss_url(query, max(3, min(12, max_results)), allowed_domains)
        try:
            res = await self._pool.fetch(rss, timeout=None, text_only=True)
            if res.status != 200:
                return ProviderResult(self.id, "provider_error", [], rss, f"HTTP {res.status}",
                                      (time.perf_counter() - t0) * 1000)
            items = parse_rss_items(res.text)
            hits: List[SearchHit] = []
            rank_i = 0
            for title, link, desc in items:
                if not link:
                    continue
                try:
                    url = normalize_url(validate_url(link))
                except (UnsafeURLError, ValueError):
                    continue
                rank_i += 1
                hits.append(SearchHit(provider=self.id, url=url,
                                      title=unescape(title).strip(),
                                      snippet=re.sub(r"\s+", " ", unescape(desc)).strip()[:320],
                                      provider_rank=rank_i))
                if rank_i >= max_results:
                    break
            (time.perf_counter() - t0)
            return ProviderResult(self.id, "ok" if hits else "no_results", hits, rss, "",
                                  (time.perf_counter() - t0) * 1000)
        except httpx.TimeoutException:
            return ProviderResult(self.id, "provider_error", [], rss, "timeout",
                                  (time.perf_counter() - t0) * 1000)
        except (UnsafeURLError, ValueError):
            # internal endpoint only; treat as unexpected config problem
            return ProviderResult(self.id, "provider_error", [], rss, "bad query url",
                                  (time.perf_counter() - t0) * 1000)


def parse_rss_items(xml_text: str) -> List[tuple]:
    out: List[tuple] = []
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = (it.findtext("description") or "").strip()
        out.append((title, link, desc))
    return out
