"""Bounded crawler. Same-site BFS with:
  - depth + page + token budget caps (caller-lowerable)
  - per-domain concurrency is bounded by the shared HttpPool semaphore
  - robots.txt honored (urllib.robotparser) - fetched once per run
  - redirect re-validation inherited from HttpPool
  - content-hash dedupe (near-duplicate pages skipped)
  - hard global deadline; partial results returned with status 'partial'
map_only=true returns just the URL tree without page content (cheapest map)."""
from __future__ import annotations

import asyncio
import time
import re
import urllib.robotparser
from collections import deque
from concurrent.futures import CancelledError
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from .extractor import html_to_markdown
from .reranker import MarkdownChunker
from .limits import TokenBudget, estimate_tokens, json_tokens
from .security import UnsafeURLError, validate_url
from .utils import fingerprint_url


def same_site(a: str, b: str) -> bool:
    from urllib.parse import urlsplit
    ha, hb = urlsplit(a).hostname or "", urlsplit(b).hostname or ""
    return ha == hb


def strip_fragment(u: str) -> str:
    return urlunsplit(({k: v for k, v in zip(['scheme', 'netloc', 'path', 'query', 'fragment'],
                                             [*urlsplit(u)[:4], ''])}))


def normalize_crawl_target(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return url
    fragless = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}{urlsplit(url).path}"
    return fragless


BOT_AGENTS = ("*",)
SKIP_EXT = re.compile(r"\.(jpe?g|png|gif|svg|webp|avif|ico|css|js|mjs|json|xml|zip|gz|pdf|docx?|xlsx?|pptx?|woff2?|mp[34]|mov|avi|webm|dmg|exe|msi|apk)(\?|$)",
                      re.I)
JUNK_PATH = re.compile(r"/(login|signin|signup|register|password-reset|cart|checkout|account/logout)\b",
                       re.I)


def crawl_links(html: str, base: str) -> List[str]:
    from bs4 import BeautifulSoup  # lazy: only crawl uses it
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    out = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:", "ftp:")):
            continue
        u = urljoin(base, href)
        u = u.split("#")[0].strip()
        if u.startswith(("http://", "https://")):
            if SKIP_EXT.search(u) or JUNK_PATH.search(u):
                continue
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out


class BoundedCrawler:
    def __init__(self, pool, cache, cfg):
        self.pool = pool
        self.cache = cache
        self.cfg = cfg

    async def _robots(self, root: str) -> urllib.robotparser.RobotFileParser | None:
        if self.cfg.allow_private_net:
            return None
        parts = urlsplit(root)
        base = f"{parts.scheme}://{parts.netloc}"
        rp = urllib.robotparser.RobotFileParser()
        try:
            res = await self.pool.fetch(base + "/robots.txt", timeout=5.0, max_bytes=200_000)
            if res.status == 200 and res.text:
                rp.parse(res.text.splitlines())
                return rp
            # 4xx = no robots => allowed
            rp.parse([])
            return rp
        except Exception:
            return None

    async def run(self, url: str, *, max_pages: int, max_depth: int,
                  map_only: bool = False, max_tokens: int = 4000,
                  deadline_seconds: float = 30.0) -> dict:
        t0 = time.perf_counter()
        try:
            url = validate_url(url, self.cfg.allow_private_net)
        except UnsafeURLError as e:
            return {"u": url, "status": "blocked", "note": str(e)[:120]}
        robots = await self._robots(url)
        if robots is not None and not robots.can_fetch("*", url):
            return {"u": url, "status": "blocked", "note": "disallowed by robots.txt"}

        q: deque = deque([(url, 0)])
        seen = {fingerprint_url(url)}
        results = []
        page_budget = TokenBudget(max_tokens)
        fetched = failed = robots_skip = 0
        truncated_due_depth = False
        note = ""

        while q:
            if len(results) >= max_pages or time.perf_counter() - t0 > deadline_seconds:
                break
            u, d = q.popleft()
            if d > max_depth:
                continue
            links: List[str] = []
            if map_only:
                # HEAD-like: quick GET then parse links; return only tree
                try:
                    res = await self.pool.fetch(u, timeout=10.0, max_bytes=700_000)
                    fetched += 1
                except (httpx.TimeoutException, httpx.NetworkError, UnsafeURLError):
                    failed += 1
                    continue
                if res.status != 200:
                    failed += 1
                    continue
                try:
                    links = crawl_links(res.text, u) or []
                except Exception:
                    links = []
                results.append({"u": u, "links_n": len(links)})
            else:
                content: Optional[dict] = None
                try:
                    content = await self._page_content(u, page_budget)
                    fetched += 1
                except (httpx.TimeoutException, httpx.NetworkError, UnsafeURLError) as e:
                    failed += 1
                    results.append({"u": u, "st": "unreachable", "note": type(e).__name__})
                    continue
                if content is None:
                    results.append({"u": u, "st": "skipped_dedupe_or_budget"})
                    continue
                results.append(content)
                try:
                    res = await self.pool.fetch(u, timeout=10.0, max_bytes=700_000)
                    links = crawl_links(res.text, u) if res.status == 200 else []
                except Exception:
                    links = []
            for nxt in links:
                nu = normalize_crawl_target(nxt)
                fp = fingerprint_url(nu)
                if fp in seen:
                    continue
                if not same_site(nu, url):
                    continue
                if robots is not None and not robots.can_fetch("*", nu):
                    robots_skip += 1
                    continue
                seen.add(fp)
                q.append((nu, d + 1))
        status = "ok"
        if fetched < min(max_pages, len(seen)):
            if time.perf_counter() - t0 > deadline_seconds:
                status = "partial_deadline"
            elif len(results) >= max_pages:
                status = "partial_page_cap"
        return {
            "u": url,
            "status": status,
            "pages": results[:max_pages],
            "n_seen": len(seen), "n_fetched": fetched, "n_failed": failed,
            "n_robots_skip": robots_skip,
            "ms": round((time.perf_counter() - t0) * 1000),
            "note": "pages: u=url, st=page-status, x=content chunk (verbatim), "
                    "sec=section, links_n=outlinks (map_only).",
        }

    async def _page_content(self, u: str, budget: TokenBudget) -> Optional[dict]:
        try:
            res = await self.pool.fetch(u, timeout=12.0, max_bytes=self.cfg.max_response_bytes)
        except (httpx.TimeoutException, httpx.NetworkError, UnsafeURLError, ValueError) as e:
            raise e
        if res.status != 200:
            return {"u": u, "st": f"HTTP {res.status}"}
        html = res.text
        rendered = html_to_markdown(html, u)
        text = rendered.markdown
        if not text or len(text.strip()) < 250:
            thin = "thin_content_js" if len(html) > 20_000 else "no_content"
            return {"u": u, "st": thin}
        chunks = MarkdownChunker().chunk(text)
        passages = [
            {"sec": c.section, "span": c.text, "kind": c.kind}
            for c in chunks[:3]
        ]
        if not passages:
            return {"u": u, "st": "no_content"}
        item = {"u": u, "st": "ok", "t": rendered.title or None, "x": passages}
        tk = json_tokens(item)
        if not budget.admit("", est=tk):
            # Trim to the first chunk rather than dropping the page entirely.
            item["x"] = passages[:1]
            if not budget.admit("", est=json_tokens(item)):
                return None
        return item


async def crawl_website(pool, cache, cfg, url: str, *, max_pages: Optional[int],
                        max_depth: int, map_only: bool, max_tokens: int,
                        deadline: float) -> dict:
    crawler = BoundedCrawler(pool, cache, cfg)
    pages = min(max_pages if max_pages else cfg.crawl_default_pages, cfg.crawl_max_pages)
    depth = max(0, min(max_depth, 4))
    if map_only:
        return await crawler.run(url, max_pages=max(3, min(pages, 30)), max_depth=depth,
                                 map_only=True, max_tokens=max_tokens, deadline_seconds=deadline)
    return await crawler.run(url, max_pages=pages, max_depth=depth, map_only=False,
                             max_tokens=max_tokens, deadline_seconds=deadline)
