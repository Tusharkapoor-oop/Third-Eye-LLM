"""Application service: one object that composes every subsystem.

The MCP server and CLI are thin adapters over this module. Every public method
returns a compact JSON-ready dict with a stable ``status`` field.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import platform
import re
import sys
import time
from typing import Any

from . import __version__
from .cache import Cache, build_cache
from .config import Settings, get_settings
from .crawl.crawler import CrawlOutcome, MapOutcome, SiteCrawler
from .errors import ErrCode, WebLensError, resolve_budget
from .extract import ExtractionService
from .net import SafeFetcher
from .research import ResearchEngine, SynthesisEngine
from .search import SearchRouter
from .tokens import TOKENIZER_NAME, count_json_tokens

log = logging.getLogger("weblens")


def _clip(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]).rstrip(" ,;:") + "…"


class WebLens:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self.s.ensure_dirs()
        self.cache: Cache = build_cache(self.s)  # type: ignore[assignment]
        self.fetcher = SafeFetcher(self.s, self.cache)
        self.router = SearchRouter(self.s, self.fetcher)
        self.extractor = ExtractionService(self.s, self.fetcher, self.cache)
        self.crawler = SiteCrawler(self.s, self.fetcher, self.extractor)
        self.research = ResearchEngine(self.s, self.router, self.extractor)

    async def close(self) -> None:
        await self.extractor.close()
        await self.fetcher.close()
        aclose = getattr(self.cache, "aclose", None)
        if aclose is not None:
            await aclose()
        else:
            self.cache.close()

    # -- error boundary --------------------------------------------------
    async def _guard(self, coro) -> dict[str, Any]:
        try:
            return await coro
        except WebLensError as e:
            return e.as_dict()
        except TimeoutError:
            return {
                "status": "error",
                "err": str(ErrCode.TIMEOUT),
                "msg": "operation deadline exceeded",
                "retry": True,
            }
        except Exception as e:  # never let a tool crash the transport
            log.exception("unhandled service error")
            if self.s.log_level.upper() == "DEBUG":
                import traceback

                traceback.print_exc(file=sys.stderr)
            return {
                "status": "error",
                "err": str(ErrCode.INTERNAL),
                "msg": f"{type(e).__name__}: {str(e)[:180]}",
                "retry": False,
            }

    async def _enrich_search_snippets(
        self,
        hits: list,
        *,
        query: str,
        budget: int,
    ) -> None:
        """Replace short provider blurbs with a relevant passage from the page.

        Search is usually the first tool an agent calls. Provider snippets are
        often too short to answer the question, forcing a second extract call
        for every result. Enriching only the first few results keeps latency
        bounded while making the returned evidence materially more useful.
        Failure is always non-fatal: the original provider snippet remains.
        """
        top = int(getattr(self.s, "search_enrich_top", 0) or 0)
        extractor = getattr(self, "extractor", None)
        if not hits or top <= 0 or extractor is None or budget < 220:
            return
        timeout = float(getattr(self.s, "search_enrich_timeout_s", 2.5))
        terms = {t for t in re.findall(r"[a-z0-9]{3,}", query.lower())}

        async def one(hit) -> None:
            try:
                extracted = await asyncio.wait_for(
                    extractor.extract(
                        hit.url,
                        query=query,
                        max_tokens=500,
                        allow_browser=False,
                    ),
                    timeout=timeout,
                )
            except Exception:
                return
            passages = getattr(extracted, "passages", None) or []
            if not passages or getattr(extracted, "status", "") in {
                "error",
                "no_reliable_result",
            }:
                return

            def coverage(passage) -> int:
                text = (getattr(passage, "text", "") or "").lower()
                return sum(1 for term in terms if term in text)

            best = max(passages, key=coverage)
            text = " ".join((getattr(best, "text", "") or "").split())
            if len(text) < 40:
                return
            old = " ".join((hit.snippet or "").split())
            generic = not old or len(old) < 80 or hit.provider.startswith("official")
            if coverage(best) == 0 and not generic:
                return
            hit.snippet = text[:1200]
            title = " ".join((getattr(extracted, "title", "") or "").split())
            if title and hit.provider.startswith("official"):
                hit.title = title[:220]

        await asyncio.gather(*(one(hit) for hit in hits[:top]), return_exceptions=True)

    # -- search ----------------------------------------------------------
    async def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        freshness: str | None = None,
        domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        async def run() -> dict[str, Any]:
            k = max(1, min(10, max_results or self.s.default_results))
            if not query or not query.strip():
                raise WebLensError("query must not be empty", code=ErrCode.BAD_INPUT)
            if len(query) > 2000:
                raise WebLensError("query exceeds maximum allowed length of 2000 characters", code=ErrCode.BAD_INPUT)
            if freshness not in (None, "day", "week", "month", "year"):
                raise WebLensError("freshness must be day, week, month or year", code=ErrCode.BAD_INPUT)
            budget = resolve_budget(max_tokens, self.s.max_search_tokens, minimum=120, maximum=2000)
            out = await self.router.search(
                query,
                k=k,
                freshness=freshness,
                domains=[d.strip() for d in (domains or []) if d.strip()][:10],
                exclude_domains=[d.strip() for d in (exclude_domains or []) if d.strip()][:10],
            )
            await self._enrich_search_snippets(
                out.hits,
                query=out.used_query,
                budget=budget,
            )
            payload: dict[str, Any] = {
                "status": out.status,
                "q": out.used_query,
                "n": 0,
                "res": [],
                "ms": out.elapsed_ms,
                "tok": 0,
            }
            if out.providers:
                payload["prov"] = out.providers
            if out.failures:
                payload["fail"] = out.failures
            if out.warnings:
                payload["warn"] = list(dict.fromkeys(out.warnings))
            cut = False
            target = max(80, budget - 6)
            for h in out.hits:
                item: dict[str, Any] = {
                    "t": _clip(h.title, 180),
                    "u": h.url,
                    "s": _clip(h.snippet, 240),
                }
                if h.date:
                    item["d"] = h.date
                trial = {**payload, "n": len(payload["res"]) + 1, "res": payload["res"] + [item]}
                if count_json_tokens({**trial, "tok": 0}) > target:
                    cut = True
                    break
                payload["res"].append(item)
            payload["n"] = len(payload["res"])
            if cut:
                payload["cut"] = True
            payload["tok"] = count_json_tokens({**payload, "tok": 0})
            while count_json_tokens(payload) > budget and payload["res"]:
                payload["res"].pop()
                payload["n"] = len(payload["res"])
                payload["cut"] = True
                payload["tok"] = count_json_tokens({**payload, "tok": 0})
            if cut and not payload["res"] and payload["status"] == "ok":
                payload["status"] = "partial"
                payload["warn"] = list(dict.fromkeys([*(payload.get("warn") or []), "budget_exhausted"]))
            return payload

        return await self._guard(run())

    # -- extract ---------------------------------------------------------
    async def extract(
        self,
        url: str,
        *,
        query: str | None = None,
        max_tokens: int | None = None,
        full: bool = False,
    ) -> dict[str, Any]:
        async def run() -> dict[str, Any]:
            out = await self.extractor.extract(
                url,
                query=query,
                max_tokens=max_tokens,
                full=full,
            )
            payload = self.extractor.payload(out)
            if out.status == "error":
                payload["err"] = str(ErrCode.EXTRACT)
                payload["msg"] = "no extractable text (JavaScript-only, blocked or empty page)"
            return payload

        return await self._guard(run())

    # -- crawl / map -----------------------------------------------------
    async def crawl_site(
        self,
        url: str,
        *,
        mode: str = "map",
        max_pages: int = 10,
        max_depth: int = 2,
        query: str | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        async def run() -> dict[str, Any]:
            if mode not in ("map", "crawl"):
                raise WebLensError("mode must be map or crawl", code=ErrCode.BAD_INPUT)
            if mode == "map":
                out: MapOutcome = await self.crawler.site_map(url, max_urls=max_pages, max_tokens=max_tokens)
                return self.crawler.map_payload(out)
            out_crawl: CrawlOutcome = await self.crawler.crawl(
                url,
                max_pages=max_pages,
                max_depth=max_depth,
                query=query,
                max_tokens=max_tokens,
            )
            return self.crawler.payload(out_crawl)

        return await self._guard(run())

    # -- research --------------------------------------------------------
    async def deep_research(
        self,
        query: str,
        *,
        max_tokens: int | None = None,
        max_searches: int = 4,
        max_pages: int = 6,
    ) -> dict[str, Any]:
        async def run() -> dict[str, Any]:
            if not query or not query.strip():
                raise WebLensError("query must not be empty", code=ErrCode.BAD_INPUT)
            if len(query) > 2000:
                raise WebLensError("query exceeds maximum allowed length of 2000 characters", code=ErrCode.BAD_INPUT)
            out = await self.research.research(
                query,
                max_tokens=max_tokens,
                max_searches=max_searches,
                max_pages=max_pages,
            )
            return self.research.payload(out)

        return await self._guard(run())

    async def synthesize(
        self,
        query: str,
        *,
        max_tokens: int | None = None,
        max_hops: int = 2,
        max_searches: int = 4,
        max_pages: int = 6,
    ) -> dict[str, Any]:
        """Test explicit hypotheses against collected evidence and resolve conflicts.

        This is deterministic and LLM-free: hypotheses are generated from the
        question, claims are classified as supporting/refuting by lexical
        stance rules, and contradictions are resolved by source tier, recency
        and independent-domain support. It never paraphrases a source.
        """

        async def run() -> dict[str, Any]:
            if not query or not query.strip():
                raise WebLensError("query must not be empty", code=ErrCode.BAD_INPUT)
            if len(query) > 2000:
                raise WebLensError(
                    "query exceeds maximum allowed length of 2000 characters",
                    code=ErrCode.BAD_INPUT,
                )
            engine = SynthesisEngine(self.research)
            out = await engine.run(
                query,
                max_tokens=max_tokens,
                max_hops=max_hops,
                max_searches=max_searches,
                max_pages=max_pages,
            )
            return out.payload()

        return await self._guard(run())

    # -- diagnostics -----------------------------------------------------
    async def doctor(self, *, live: bool = False) -> dict[str, Any]:
        has_playwright = importlib.util.find_spec("playwright") is not None
        cache_stats_fn = getattr(self.cache, "stats_async", None)
        cache_stats = await cache_stats_fn() if cache_stats_fn is not None else self.cache.stats()
        info: dict[str, Any] = {
            "ok": True,
            "version": __version__,
            "python": platform.python_version(),
            "platform": f"{platform.system()} {platform.release()}",
            "providers": self.router.provider_names,
            "unavailable": self.router.unavailable,
            "browser": has_playwright and self.s.allow_browser,
            "cache": cache_stats,
            "cache_dir": str(self.s.cache_dir),
            "tokenizer": TOKENIZER_NAME,
            "budgets": {
                "search": self.s.max_search_tokens,
                "extract": self.s.max_extract_tokens,
                "research": self.s.max_research_tokens,
            },
        }
        if live:
            t0 = time.perf_counter()
            res = await self.search("python asyncio", max_results=1)
            info["live"] = {
                "status": res.get("status"),
                "ms": int((time.perf_counter() - t0) * 1000),
                "providers": res.get("prov", []),
                "error": res.get("err"),
            }
        return info
