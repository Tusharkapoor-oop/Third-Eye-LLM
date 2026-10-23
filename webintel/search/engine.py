"""Search engine: ordered provider chain with fallback, near-duplicate removal,
transparent baseline ranking (ranking.rank_search_hits), token-capped output.
No relevance scores are ever emitted (R2).
Output shape (legend lives in the tool description; one source of truth):
  status: ok | no_reliable_result
  q, r[{u,t,s,d?}], prov[{p,st,ms}], note
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

import httpx

from ..config import Config
from ..limits import TokenBudget, json_tokens
from ..ranking import rank_search_hits
from ..utils import dedup_by, fingerprint_url, normalize_text
from .base import ProviderResult
from .bing_rss import BingRssProvider
from .brave import BraveProvider
from .searxng import SearxngProvider
from .tavily import TavilyProvider

_LEGEND = ("r results legend: u=url t=title s=snippet d=date only when known. "
           "No relevance scores are returned - they are uncalibrated (see engine docs).")


class SearchEngine:
    def __init__(self, cfg: Config, pool):
        self.cfg = cfg
        prov = cfg.search
        self._providers: Dict[str, object] = {}
        for pid in prov.order:
            if pid == "bing_rss":
                self._providers[pid] = BingRssProvider(pool)
            elif pid == "tavily":
                self._providers[pid] = TavilyProvider(pool, prov.tavily_key)
            elif pid == "brave":
                self._providers[pid] = BraveProvider(pool, prov.brave_key)
            elif pid == "searxng":
                self._providers[pid] = SearxngProvider(pool, prov.searxng_url)
        self.order: List[str] = prov.order

    # ------------------------------------------------------------------ core
    async def _run_chain(self, query: str, max_results: int, freshness: Optional[int],
                         domains: Optional[List[str]], deadline: float) -> tuple:
        log = []
        all_hits: List[SearchHit.__class__.__module__] = []  # placeholder; see below
        from .base import SearchHit
        all_hits = []
        for pid in self.order:
            if time.monotonic() > deadline:
                break
            provider = self._providers[pid]
            try:
                r: ProviderResult = await provider.search(
                    query,
                    max_results=max_results,
                    freshness_days=freshness,
                    allowed_domains=domains,
                )
            except Exception as e:
                log.append({"p": pid, "st": "provider_error", "note": type(e).__name__})
                continue
            entry = {"p": pid, "st": r.status, "ms": round(r.latency_ms), "n": len(r.hits)}
            if r.error:
                entry["note"] = r.error[:60]
            log.append(entry)
            if r.status == "ok":
                all_hits.extend(r.hits)
                if all_hits and len(all_hits) >= max_results:
                    break  # enough from this provider; fallback unnecessary
        return all_hits, log

    @staticmethod
    def _dedupe(hits: List) -> List:
        from difflib import SequenceMatcher
        out = dedup_by(hits, lambda h: fingerprint_url(h.url))
        titles: List[str] = []
        final = []
        for h in out:
            tn = normalize_text(h.title)[:70]
            if tn and any(SequenceMatcher(None, tn, s).ratio() > 0.92 for s in titles):
                continue
            if tn:
                titles.append(tn)
            final.append(h)
        return final

    # ----------------------------------------------------------------- public
    async def web_search(self, query: str, *, max_results: int, freshness: Optional[int],
                         domains: Optional[List[str]], max_tokens: int,
                         cache, cache_key: str) -> dict:
        cache = cache
        cached = cache.get("search", cache_key, self.cfg.ttl_search) if cache else None
        if cached is not None:
            return cached
        deadline = time.monotonic() + self.cfg.http_timeout_search + 2.0
        hits, log = await self._run_chain(query, max_results, freshness, domains, deadline)
        deduped = self._dedupe(hits)
        ranked = rank_search_hits(deduped, query)[: max_results]
        payload = self._format(query, ranked, log, max_tokens)
        if freshness and any(e.get("p") == "bing_rss" for e in log):
            # honesty (R2): bing_rss cannot filter by date; disclose in the payload
            base_note = payload.get("note", "")
            payload["note"] = (base_note + " | freshness_days not applied by provider "
                               "bing_rss (endpoint limitation); dates in results, if any, "
                               "are unverified by this engine.").strip(" |")
        if cache:
            cache.put("search", cache_key, payload)
        return payload

    def _format(self, query: str, hits: List, log: List[dict], max_tokens: int) -> dict:
        out = {"status": "ok" if hits else "no_reliable_result", "q": query, "r": []}
        budget = TokenBudget(max_tokens)
        fixed = json_tokens(out) + json_tokens({"note": _LEGEND}) + 60
        for h in hits:
            item = {"u": h.url, "t": (h.title or "")[:120], "s": (h.snippet or "")[:220]}
            if h.date and isinstance(h.date, str):
                item["d"] = h.date[:24]
            tk = json_tokens(item) + 2
            if budget.used + tk > max_tokens - fixed:
                break
            out["r"].append(item)
            budget.admit("", est=tk)
        if not hits:
            msg = "no results after dedupe+ranking; consider different query or provider"
            if log and any(e.get("st") == "provider_error" for e in log):
                msg = "provider errors: " + ";".join(e["p"] for e in log if e.get("st") == "provider_error")
            out["note"] = msg
        else:
            out["note"] = _LEGEND
        if log:
            out["prov"] = log
        return out
