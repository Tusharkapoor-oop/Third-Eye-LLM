"""webintel MCP server (SDK v2, ``mcp>=2.3``).

Tool surface (5 tools):
  web_search     - expanded multi-query search, authority-ranked, token-capped
  extract_url    - tiered extraction + structure-aware passage selection
  web_map        - bounded same-domain URL map
  crawl_website  - bounded same-domain crawl
  deep_research  - grounded multi-hop research with MCP progress + citations

Heavy resources (SQLite cache, HTTP pool, warm Chromium, cross-encoder) are
created once in the server lifespan and shared by every tool call. Each tool
returns compact JSON; the legend for each payload lives in its description.
No relevance score is ever emitted to callers (project rule R2).
"""
from __future__ import annotations

import asyncio
import inspect
import sys
import time
from collections import deque
from typing import Optional
from urllib.parse import urlsplit

from mcp.server.mcpserver import Context

from .cache import Cache
from .config import Config, load_config
from .crawl import BoundedCrawler, crawl_links, crawl_website as _crawl_website
from .crawl import normalize_crawl_target, same_site
from .extractor import BrowserEngine, TieredExtractor
from .http_client import HttpPool
from .limits import json_tokens, trim_text
from .query_engine import expand_query
from .reranker import PassageSelector
from .research_engine import GroundedResearcher
from .schemas import (CrawlPage, CrawlPayload, ExtractedPassage, ExtractPayload,
                      MapItem, MapPayload, Passage, ResearchPayload, dump)
from .search_pipeline import HybridSearchPipeline, to_search_payload
from .security import UnsafeURLError, validate_url
from .utils import fingerprint_url


class Runtime:
    """Lazily-initialised singleton holding every expensive dependency."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.cache: Optional[Cache] = None
        self.pool: Optional[HttpPool] = None
        self.browser: Optional[BrowserEngine] = None
        self.search: Optional[HybridSearchPipeline] = None
        self.extractor: Optional[TieredExtractor] = None
        self.selector: Optional[PassageSelector] = None
        self.researcher: Optional[GroundedResearcher] = None
        self._ready = False
        self._lock = asyncio.Lock()
        self._browser_task: Optional[asyncio.Task] = None

    async def ready(self) -> "Runtime":
        if self._ready:
            return self
        async with self._lock:
            if self._ready:
                return self
            self.cfg.cache_dir.mkdir(parents=True, exist_ok=True)
            self.cache = Cache(self.cfg.cache_dir / "cache.sqlite3")
            self.pool = HttpPool(self.cfg)
            self.search = HybridSearchPipeline(self.cfg, self.pool)
            if self.cfg.js_render:
                self.browser = BrowserEngine(
                    self.cfg.browser_profile_dir,
                    timeout_ms=self.cfg.browser_timeout_ms,
                )
            self.extractor = TieredExtractor(self.cfg, self.pool, self.cache, self.browser)
            self.selector = PassageSelector()
            self.researcher = GroundedResearcher(
                self.cfg, self.search, self.extractor, self.selector
            )
            self._ready = True
        if self.browser is not None:
            # Warm in the background: tools/list and web_search must not wait
            # for Chromium. The first Tier 2 extraction awaits the same task.
            self._browser_task = asyncio.create_task(self._warm_browser())
        return self

    async def _warm_browser(self) -> None:
        try:
            await self.browser.start()  # type: ignore[union-attr]
        except Exception:
            pass

    async def close(self) -> None:
        if self._browser_task is not None:
            self._browser_task.cancel()
            try:
                await self._browser_task
            except (asyncio.CancelledError, Exception):
                pass
        if self.browser is not None:
            await self.browser.close()
        if self.pool is not None:
            await self.pool.aclose()
        if self.cache is not None:
            self.cache.close()


async def _report(ctx, pct: float, message: str) -> None:
    """Best-effort MCP progress. Never let telemetry break a tool call."""
    if ctx is None:
        return None
    try:
        result = ctx.report_progress(pct, 100, message)
        if inspect.isawaitable(result):
            await result
    except Exception:
        pass
    return None


def build_app() -> "tuple[object, Config]":
    from mcp.server import MCPServer
    from mcp.server.mcpserver import Context

    cfg = load_config()
    runtime = Runtime(cfg)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_server):
        await runtime.ready()
        try:
            yield runtime
        finally:
            await runtime.close()

    mcp = MCPServer(
        "webintel",
        version="1.0.0",
        instructions=(
            "Web intelligence tools for evidence work. Outputs are compact JSON with "
            "short keys. Evidence passages are verbatim quotes with url + fetch time. "
            "No relevance scores are returned because they are uncalibrated. Use "
            "web_search for lookups, extract_url(url, query) to read one page, web_map "
            "to inventory a site, crawl_website for a bounded crawl, deep_research for "
            "multi-source questions (it reports MCP progress)."
        ),
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------ search
    @mcp.tool()
    async def web_search(query: str, max_results: int = 5, max_tokens: int = 600,
                         freshness_days: int = 0, time_range: str = "",
                         allowed_domains: list[str] | None = None) -> dict:
        """Search live web. query; max_results<=10; max_tokens cap; freshness_days>0
        or time_range=day|week|month|year; allowed_domains<=4.
        Returns {status,q,r:[{u,t,s,d?}],prov,note}. r is authority-ranked; no scores."""
        if not query or not isinstance(query, str):
            return {"status": "error", "note": "query must be a non-empty string"}
        try:
            await runtime.ready()
            results = max(3, min(int(max_results or 5), 10))
            tokens = max(150, min(int(max_tokens or 600), 1200))
            window = time_range if time_range in ("day", "week", "month", "year") else None
            if not window and freshness_days and int(freshness_days) > 0:
                days = int(freshness_days)
                window = "day" if days <= 1 else "week" if days <= 7 else "month" if days <= 31 else "year"
            domains = [d.strip() for d in (allowed_domains or []) if d.strip()][:4]
            plan = await expand_query(query.strip())
            outcome = await runtime.search.search(
                plan, max_results=results, time_range=window, domains=domains or None
            )
            return dump(to_search_payload(plan, outcome, max_tokens=tokens))
        except Exception as exc:
            return {"status": "error", "note": f"{type(exc).__name__}: {exc}"[:200]}

    # ----------------------------------------------------------------- extract
    @mcp.tool()
    async def extract_url(url: str, query: str = "", max_tokens: int = 1500,
                          chunks_per_source: int = 3, full: bool = False) -> dict:
        """Read one page. url; query selects passages; chunks_per_source 1-5;
        full=true returns whole markdown. Returns {status,u,fetched_at,x:[{sec,span,kind}],
        t?,date?,site?,tier?,note}. x spans are verbatim; code fences and tables kept."""
        if not url or not isinstance(url, str):
            return {"status": "error", "note": "url must be a non-empty string"}
        try:
            await runtime.ready()
            tokens = max(200, min(int(max_tokens or 1500), 12000 if full else 4000))
            top_k = max(1, min(int(chunks_per_source or 3), 5))
            extraction = await runtime.extractor.extract(url, query=query)
            if extraction.status != "ok":
                return dump(ExtractPayload(
                    status=extraction.status, u=extraction.final_url or url,
                    t=extraction.title or None,
                    note=extraction.reason[:200], tier=extraction.tier or None,
                    ms=extraction.elapsed_ms,
                ))
            payload = ExtractPayload(
                status="ok",
                u=extraction.final_url or url,
                t=extraction.title or None,
                date=extraction.date or None,
                site=extraction.site or None,
                canon=(extraction.canonical
                       if extraction.canonical and extraction.canonical != (extraction.final_url or url)
                       else None),
                tier=extraction.tier,
                ms=extraction.elapsed_ms,
                cache=extraction.from_cache,
            )
            if full:
                payload.full = trim_text(extraction.markdown, tokens)
                payload.note = "full=true; markdown trimmed to max_tokens; code/tables preserved."
                return dump(payload)

            if query.strip():
                plan = await expand_query(query.strip())
                passages = await runtime.selector.select(
                    extraction.markdown, query, plan, top_k=top_k
                )
            else:
                chunks = runtime.selector.chunker.chunk(extraction.markdown)
                passages = [
                    Passage(url=extraction.final_url or url, section=c.section,
                            span=c.text, kind=c.kind, order=c.order)
                    for c in chunks[:top_k]
                ]

            budget = 0
            for passage in passages:
                entry = ExtractedPassage(
                    sec=passage.section, span=passage.span, kind=passage.kind
                )
                cost = json_tokens(dump(entry)) + 2
                if budget + cost > tokens and payload.x:
                    break
                payload.x.append(entry)
                budget += cost
            payload.note = ("x = verbatim query-selected passages in reading order; "
                            "sec is the heading breadcrumb; kind marks code/table blocks.")
            return dump(payload)
        except Exception as exc:
            return {"status": "error", "note": f"{type(exc).__name__}: {exc}"[:200]}

    # -------------------------------------------------------------------- map
    @mcp.tool()
    async def web_map(url: str, max_depth: int = 2, max_urls: int = 40) -> dict:
        """Map a site without extracting text. url; max_depth 0-3; max_urls<=100.
        Same-domain, robots.txt respected. Returns {status,u,urls:[{u,d}],n,note}."""
        if not url or not isinstance(url, str):
            return {"status": "error", "note": "url must be a non-empty string"}
        try:
            await runtime.ready()
            target = validate_url(url, cfg.allow_private_net)
            depth_cap = max(0, min(int(max_depth or 2), 3))
            limit = max(5, min(int(max_urls or 40), 100))
            crawler = BoundedCrawler(runtime.pool, runtime.cache, cfg)
            robots = await crawler._robots(target)  # shared robots policy with crawl
            queue: deque[tuple[str, int]] = deque([(target, 0)])
            seen = {fingerprint_url(target)}
            urls: list[MapItem] = []
            truncation = False
            while queue and len(urls) < limit:
                current, level = queue.popleft()
                if robots is not None and not robots.can_fetch("*", current):
                    continue
                urls.append(MapItem(u=current, d=level))
                if level >= depth_cap:
                    continue
                try:
                    fetched = await runtime.pool.fetch(current, timeout=8.0,
                                                       max_bytes=700_000)
                except Exception:
                    continue
                if fetched.status != 200:
                    continue
                try:
                    links = crawl_links(fetched.text, fetched.url)
                except Exception:
                    links = []
                for link in links:
                    next_url = normalize_crawl_target(link)
                    if not same_site(next_url, target):
                        continue
                    fingerprint = fingerprint_url(next_url)
                    if fingerprint in seen:
                        continue
                    seen.add(fingerprint)
                    if len(seen) > limit * 4:
                        truncation = True
                        continue
                    queue.append((next_url, level + 1))
            if queue:
                truncation = True
            return dump(MapPayload(
                status="ok", u=target, urls=urls, n=len(urls), truncated=truncation,
                note="urls are same-domain and robots-allowed; d is depth from the root.",
            ))
        except UnsafeURLError as exc:
            return {"status": "error", "note": str(exc)[:160]}
        except Exception as exc:
            return {"status": "error", "note": f"{type(exc).__name__}: {exc}"[:200]}

    # ------------------------------------------------------------------ crawl
    @mcp.tool()
    async def crawl_website(url: str, max_pages: int = 5, max_depth: int = 1,
                            max_tokens: int = 4000) -> dict:
        """Crawl one site. url; max_pages<=25; max_depth 0-4; max_tokens caps output.
        Same-domain, robots.txt respected, strict deadline, partial results allowed.
        Returns {status,u,pages:[{u,status,t?,x}],n,budget,note}."""
        if not url or not isinstance(url, str):
            return {"status": "error", "note": "url must be a non-empty string"}
        try:
            await runtime.ready()
            pages_cap = max(1, min(int(max_pages or 5), 25))
            depth = max(0, min(int(max_depth or 1), 4))
            tokens = max(400, min(int(max_tokens or 4000), 12000))
            raw = await _crawl_website(
                runtime.pool, runtime.cache, cfg, url,
                max_pages=pages_cap, max_depth=depth, map_only=False,
                max_tokens=tokens, deadline=30.0,
            )
            pages: list[CrawlPage] = []
            for page in raw.get("pages", []):
                passage = page.get("x")
                x: list[ExtractedPassage] = []
                if isinstance(passage, str) and passage:
                    x = [ExtractedPassage(span=passage)]
                elif isinstance(passage, list):
                    for item in passage:
                        if isinstance(item, dict) and item.get("span"):
                            x.append(ExtractedPassage(
                                sec=str(item.get("sec") or ""),
                                span=str(item["span"]),
                                kind=item.get("kind"),
                            ))
                pages.append(CrawlPage(
                    u=str(page.get("u") or ""),
                    status=str(page.get("st") or "unknown"),
                    t=page.get("t") or None,
                    x=x,
                ))
            status = raw.get("status")
            mapped = "ok" if status == "ok" else (
                "partial_budget" if str(status).startswith("partial") else "no_content"
            )
            return dump(CrawlPayload(
                status=mapped, u=raw.get("u") or url, pages=pages, n=len(pages),
                budget={"pages": pages_cap, "depth": depth, "tokens": tokens},
                note=str(raw.get("note") or "")[:300],
            ))
        except Exception as exc:
            return {"status": "error", "note": f"{type(exc).__name__}: {exc}"[:200]}

    # --------------------------------------------------------------- research
    @mcp.tool()
    async def deep_research(question: str, mode: str = "mini", max_sources: int = 6,
                            max_tokens: int = 4000,
                            ctx: Context | None = None) -> dict:
        """Grounded multi-hop research with MCP progress. question; mode=mini|pro;
        max_sources<=10; max_tokens caps evidence.
        Returns {status,q,answer?,citations,evidence,gaps,budget,note}. Without a
        Gemini key it returns evidence_only (no invented synthesis)."""
        if not question or not isinstance(question, str):
            return {"status": "error", "note": "question must be a non-empty string"}
        try:
            await runtime.ready()
            sources = max(3, min(int(max_sources or 6), 10))
            tokens = max(800, min(int(max_tokens or 4000), 12000))
            research_mode = "pro" if str(mode).lower() == "pro" else "mini"

            async def progress(pct: float, message: str) -> None:
                await _report(ctx, pct, message)

            payload: ResearchPayload = await runtime.researcher.run(
                question.strip(), mode=research_mode, max_sources=sources,
                max_tokens=tokens, progress=progress,
            )
            return dump(payload)
        except Exception as exc:
            return {"status": "error", "note": f"{type(exc).__name__}: {exc}"[:200]}

    return mcp, cfg


async def serve_stdio() -> None:
    mcp, _cfg = build_app()
    await mcp.run_stdio_async()


def main() -> None:
    started = time.perf_counter()
    try:
        mcp, _cfg = build_app()
        mcp.run("stdio")
    except KeyboardInterrupt:
        sys.stderr.write("webintel: shutdown (KeyboardInterrupt)\n")
    finally:
        sys.stderr.write(f"webintel server runtime {time.perf_counter() - started:.2f}s\n")


if __name__ == "__main__":
    main()
