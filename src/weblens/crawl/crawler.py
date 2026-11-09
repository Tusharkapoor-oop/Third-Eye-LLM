"""Bounded site mapping and crawling."""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from lxml import html as lxml_html

from ..config import Settings
from ..errors import ErrCode, WebLensError, resolve_budget
from ..extract.passages import select_passages
from ..extract.service import ExtractionService
from ..net import SafeFetcher
from ..tokens import count_json_tokens, count_tokens, truncate_tokens
from ..urls import is_same_site, normalize_url
from .robots import RobotsPolicy

SKIP_EXT = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".bmp",
    ".tiff",
    ".mp4",
    ".webm",
    ".avi",
    ".mov",
    ".mkv",
    ".mp3",
    ".wav",
    ".ogg",
    ".flac",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".exe",
    ".msi",
    ".dmg",
    ".iso",
    ".css",
    ".js",
    ".mjs",
    ".map",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
}
SKIP_PARTS = {
    "/login",
    "/logout",
    "/signin",
    "/signup",
    "/register",
    "/cart",
    "/checkout",
    "/wp-admin",
    "/wp-login",
    "/admin",
    "/feed",
    "/rss",
    "/print/",
}
CALENDAR = re.compile(r"/(?:19|20)\d{2}/(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])/?$")


def path_affinity(root: str, link: str) -> int:
    """Prefer pages near the root URL (sibling stem, same directory, prefix)."""
    try:
        pr = [p for p in urlsplit(root).path.split("/") if p]
        pl = [p for p in urlsplit(link).path.split("/") if p]
    except ValueError:
        return 0
    if pr and pl:
        root_stem = pr[-1].rsplit(".", 1)[0]
        link_stem = pl[-1].rsplit(".", 1)[0]
        prefix = root_stem.split("-")[0]
        if prefix and prefix != root_stem and (link_stem == prefix or link_stem.startswith(prefix + "-")):
            return 4
    if pr[:-1] == pl[:-1] and pr[:-1]:
        return 3
    common = 0
    for a, b in zip(pr, pl, strict=False):
        if a == b:
            common += 1
        else:
            break
    if common >= 2:
        return 2
    if common >= 1:
        return 1
    return 0


def follow_threshold(root: str) -> int:
    """Minimum path affinity for crawling links from this root."""
    try:
        path = urlsplit(root).path
    except ValueError:
        return 2
    if path in ("", "/"):
        return 0
    name = path.rstrip("/").rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    prefix = stem.split("-")[0]
    if prefix and prefix != stem:
        return 4
    return 3


def crawlable(url: str, root: str, *, min_affinity: int = 0) -> bool:
    if not is_same_site(url, root):
        return False
    try:
        p = urlsplit(url)
    except ValueError:
        return False
    path = p.path.lower()
    if any(path.endswith(ext) for ext in SKIP_EXT):
        return False
    if any(part in path for part in SKIP_PARTS):
        return False
    if len(p.query) > 160 or p.query.count("&") > 4:
        return False
    if CALENDAR.search(path):
        return False
    if len(url) > 500:
        return False
    if path_affinity(root, url) < min_affinity:
        return False
    return True


def _norm_text(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower())[:4000].strip()


def content_fingerprint(text: str) -> tuple[str, set[int]]:
    norm = _norm_text(text)
    exact = hashlib.blake2b(norm.encode(), digest_size=16).hexdigest()
    words = norm.split()
    shingles = {
        int.from_bytes(hashlib.blake2b(" ".join(words[i : i + 5]).encode(), digest_size=8).digest(), "big")
        for i in range(max(0, len(words) - 4))
    }
    return exact, shingles


def near_duplicate(a: set[int], b: set[int]) -> bool:
    if not a or not b:
        return False
    inter = len(a & b)
    return inter / max(1, len(a | b)) >= 0.9


@dataclass
class CrawledPage:
    url: str
    title: str
    fetched_at: str
    status: str
    published: str | None = None
    passages: list[dict] = field(default_factory=list)
    excerpt: str = ""
    warnings: list[str] = field(default_factory=list)
    # Full cleaned text and token count, kept in memory only. Crawl2RAG needs
    # the complete document to build accurate passages and source spans; the
    # serialized crawl payload still uses the budgeted `passages`/`excerpt`.
    text: str = ""
    tokens: int = 0


@dataclass
class MapOutcome:
    status: str
    url: str
    urls: list[dict]
    elapsed_ms: int
    tokens: int
    warnings: list[str] = field(default_factory=list)
    sitemap_used: bool = False
    cut: bool = False
    budget: int = 4000


@dataclass
class CrawlOutcome:
    status: str
    url: str
    pages: list[CrawledPage]
    elapsed_ms: int
    tokens: int
    warnings: list[str] = field(default_factory=list)
    cut: bool = False
    budget: int = 4000


class SiteCrawler:
    def __init__(self, settings: Settings, fetcher: SafeFetcher, extractor: ExtractionService):
        self.s = settings
        self.fetcher = fetcher
        self.extractor = extractor
        self.robots = RobotsPolicy(settings, fetcher)

    async def _sitemap_urls(self, root: str, cap: int, warnings: list[str]) -> tuple[list[dict], bool]:
        p = urlsplit(root)
        origin = f"{p.scheme}://{p.netloc}"
        seeds, robots_warn = await self.robots.sitemaps(root)
        if robots_warn:
            warnings.append(robots_warn)
        if not seeds:
            seeds = [origin + "/sitemap.xml"]
        found: list[dict] = []
        seen: set[str] = set()
        queue = deque(seeds[:4])
        fetched = 0
        while queue and len(found) < cap and fetched < 8:
            sm = queue.popleft()
            fetched += 1
            try:
                resp = await self.fetcher.fetch(sm, cache_ttl=3600, max_bytes=2_000_000)
                if not resp.ok:
                    continue
                text = resp.text
                if "<sitemapindex" in text:
                    try:
                        doc = lxml_html.fromstring(text)
                        for loc in doc.xpath("//*[local-name()='loc']/text()")[:4]:
                            queue.append(loc.strip())
                    except (ValueError, TypeError):
                        pass
                    continue
                try:
                    doc = lxml_html.fromstring(text)
                    locs = doc.xpath("//*[local-name()='loc']/text()")
                except (ValueError, TypeError):
                    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)
                for loc in locs:
                    u = normalize_url(loc.strip())
                    if not u or u in seen:
                        continue
                    if not is_same_site(u, root):
                        continue
                    seen.add(u)
                    found.append({"u": u, "t": ""})
                    if len(found) >= cap:
                        break
            except Exception:  # noqa: S112 - one bad sitemap must not abort the map
                continue
        return found, bool(found)

    async def site_map(self, url: str, *, max_urls: int = 50, max_tokens: int | None = None) -> MapOutcome:
        started = time.perf_counter()
        cap = max(1, min(200, max_urls))
        budget = resolve_budget(max_tokens, self.s.max_search_tokens, minimum=200, maximum=4000)
        root = normalize_url(url)
        if not root:
            raise WebLensError("invalid URL", code=ErrCode.BAD_INPUT)
        doc = await self.extractor.fetch_doc(root, allow_browser=False)
        entries: list[dict] = [{"u": root, "t": doc.title[:100]}]
        seen: set[str] = {root.rstrip("/")}
        for link, text in doc.links:
            if not crawlable(link, root):
                continue
            key = link.rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            entries.append({"u": link, "t": text[:100]})
            if len(entries) >= 400:
                break
        entries.sort(key=lambda e: (-path_affinity(root, str(e["u"])), len(str(e["u"]))))
        # Keep the start URL first; it is the anchor for the map.
        root_entry = next(
            (e for e in entries if str(e["u"]).rstrip("/") == root.rstrip("/")),
            {"u": root, "t": doc.title[:100]},
        )
        rest = [e for e in entries if str(e["u"]).rstrip("/") != root.rstrip("/")]
        entries = ([root_entry] + rest)[:cap]
        warnings: list[str] = []
        sitemap_used = False
        if len(entries) < cap:
            sm, used = await self._sitemap_urls(root, cap - len(entries), warnings)
            sitemap_used = used
            for e in sm:
                key = e["u"].rstrip("/")
                if key in seen:
                    continue
                seen.add(key)
                entries.append(e)
                if len(entries) >= cap:
                    break
        if len(entries) <= 1:
            warnings.append("no_links_found")
        payload: dict[str, object] = {
            "status": "ok" if entries else "no_reliable_result",
            "u": root,
            "n": len(entries),
            "urls": entries,
            "tok": 0,
        }
        if warnings:
            payload["warn"] = warnings
        if sitemap_used:
            payload["sitemap"] = True
        tokens = count_json_tokens({**payload, "tok": 0})
        payload["tok"] = tokens
        return MapOutcome(
            status=str(payload["status"]),
            url=root,
            urls=entries,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            tokens=tokens,
            warnings=warnings,
            sitemap_used=sitemap_used,
            budget=budget,
        )

    async def crawl(
        self,
        url: str,
        *,
        max_pages: int = 10,
        max_depth: int = 2,
        query: str | None = None,
        max_tokens: int | None = None,
    ) -> CrawlOutcome:
        started = time.perf_counter()
        root = normalize_url(url)
        if not root:
            raise WebLensError("invalid URL", code=ErrCode.BAD_INPUT)
        pages_cap = max(1, min(30, max_pages))
        depth_cap = max(0, min(3, max_depth))
        follow_min = follow_threshold(root)
        budget = resolve_budget(max_tokens, self.s.max_extract_tokens, minimum=300, maximum=8000)
        queue: deque[tuple[str, int]] = deque([(root, 0)])
        seen: set[str] = {root.rstrip("/")}
        pages: list[CrawledPage] = []
        warnings: list[str] = []
        fingerprints: list[set[int]] = []
        denied = 0
        duplicates = 0
        sem = asyncio.Semaphore(4)

        async def process(node: tuple[str, int]) -> CrawledPage | None:
            nonlocal denied, duplicates
            u, depth = node
            try:
                allowed, robots_warn = await self.robots.allowed(u)
                if robots_warn:
                    warnings.append(robots_warn)
                if not allowed:
                    denied += 1
                    return None
                async with sem:
                    doc = await self.extractor.fetch_doc(u, allow_browser=False)
            except Exception as e:
                return CrawledPage(
                    url=u,
                    title="",
                    fetched_at="",
                    status="error",
                    warnings=[type(e).__name__],
                )
            if not doc.text.strip():
                return CrawledPage(url=u, title=doc.title, fetched_at=doc.fetched_at, status="empty")
            exact, sig = content_fingerprint(doc.text)
            if any(near_duplicate(sig, prev) for prev in fingerprints):
                duplicates += 1
                return None
            fingerprints.append(sig)
            page = CrawledPage(
                url=doc.final_url or u,
                title=doc.title,
                fetched_at=doc.fetched_at,
                status="ok",
                published=doc.date_iso(),
                warnings=list(doc.warnings),
                text=doc.text,
                tokens=count_tokens(doc.text),
            )
            if query and query.strip():
                passages, cov = select_passages(doc.text, query, title=doc.title, max_passages=2, max_chars=2600)
                page.passages = [
                    {
                        "u": page.url,
                        "at": page.fetched_at,
                        "x": p.text,
                        "s": [p.start, p.end],
                        **({"h": p.heading} if p.heading else {}),
                        **({"inj": p.injection} if p.injection else {}),
                    }
                    for p in passages
                ]
                if cov == 0:
                    page.passages = []
                    page.warnings.append("no_query_match")
            else:
                page.excerpt = doc.text[:280].replace("\n", " ")
            if depth < depth_cap:
                links: list[tuple[int, str]] = []
                for link, _ in doc.links:
                    if not crawlable(link, root, min_affinity=follow_min):
                        continue
                    key = link.rstrip("/")
                    if key in seen:
                        continue
                    seen.add(key)
                    links.append((path_affinity(root, link), link))
                links.sort(key=lambda t: (-t[0], len(t[1])))
                queue.extend((link, depth + 1) for _, link in links)
            return page

        # Level-order processing keeps depth meaningful and bounds fan-out.
        try:
            async with asyncio.timeout(self.s.total_timeout_s * 2):
                while queue and len(pages) < pages_cap:
                    level = [queue.popleft() for _ in range(min(len(queue), pages_cap - len(pages)))]
                    results = await asyncio.gather(*(process(n) for n in level), return_exceptions=True)
                    for r in results:
                        if isinstance(r, CrawledPage) and r is not None:
                            pages.append(r)
                        elif isinstance(r, BaseException) and not isinstance(r, asyncio.CancelledError):
                            warnings.append(f"page_failed:{type(r).__name__}")
        except TimeoutError:
            warnings.append("crawl_deadline")

        if denied:
            warnings.append(f"robots_denied:{denied}")
        if duplicates:
            warnings.append(f"duplicates_removed:{duplicates}")
        warnings = list(dict.fromkeys(warnings))
        if not pages:
            status = "no_reliable_result"
        elif any(p.status != "ok" for p in pages):
            status = "partial"
        else:
            status = "ok"

        # Budget the page payload.
        kept: list[CrawledPage] = []
        for page in pages:
            trial = kept + [page]
            payload = self._crawl_payload(root, trial, status, warnings)
            if count_json_tokens({**payload, "tok": 0}) <= budget:
                kept = trial
                continue
            if not kept:
                # Truncate the first page's evidence rather than returning nothing.
                if page.passages:
                    page.passages = page.passages[:1]
                    p = page.passages[0]
                    remaining = max(80, budget // 2)
                    short, cut = truncate_tokens(str(p["x"]), remaining)
                    p["x"] = short
                    p["s"] = [p["s"][0], p["s"][0] + len(short)]
                    if cut:
                        page.warnings.append("passage_truncated")
                    kept = [page]
            break
        tokens = count_json_tokens({**self._crawl_payload(root, kept, status, warnings), "tok": 0})
        return CrawlOutcome(
            status=status,
            url=root,
            pages=kept,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            tokens=tokens,
            warnings=list(dict.fromkeys(warnings)),
            budget=budget,
        )

    def _crawl_payload(self, root: str, pages: list[CrawledPage], status: str, warnings: list[str]) -> dict:
        out_pages: list[dict] = []
        for p in pages:
            item: dict[str, object] = {"u": p.url, "t": p.title, "at": p.fetched_at, "s": p.status}
            if p.published:
                item["d"] = p.published
            if p.passages:
                item["ps"] = p.passages
            elif p.excerpt:
                item["x"] = p.excerpt
            if p.warnings:
                item["warn"] = list(dict.fromkeys(p.warnings))
            out_pages.append(item)
        body: dict[str, object] = {
            "status": status,
            "u": root,
            "n": len(out_pages),
            "pages": out_pages,
            "tok": 0,
        }
        if warnings:
            body["warn"] = list(dict.fromkeys(warnings))
        return body

    def payload(self, out: CrawlOutcome) -> dict:
        budget = max(200, out.budget)
        target = max(120, budget - 6)
        pages = list(out.pages)
        status = out.status
        for _ in range(120):
            body = self._crawl_payload(out.url, pages, status, out.warnings)
            body["ms"] = out.elapsed_ms
            body["tok"] = 0
            n = count_json_tokens(body)
            if n <= target:
                break
            if not pages:
                break
            page = pages[-1]
            if len(page.passages) > 1:
                page.passages.pop()
                out.cut = True
                continue
            item = page.passages[0] if page.passages else None
            text = str(item.get("x", "")) if item is not None else page.excerpt
            if text:
                over = n - target
                keep = count_tokens(text) - over - 4
                if keep >= 50:
                    short, _ = truncate_tokens(text, keep)
                    if short and len(short) < len(text):
                        if item is not None:
                            item["x"] = short
                            span = item.get("s")
                            if isinstance(span, list) and len(span) == 2:
                                item["s"] = [span[0], span[0] + len(short)]
                        else:
                            page.excerpt = short
                        out.cut = True
                        continue
                if item is not None:
                    page.passages = []
                else:
                    page.excerpt = ""
                out.cut = True
                continue
            pages.pop()
            out.cut = True
        body = self._crawl_payload(out.url, pages, status, out.warnings)
        body["ms"] = out.elapsed_ms
        if out.cut:
            body["cut"] = True
        if not pages and out.pages:
            status = "partial"
            body["status"] = status
            body["warn"] = list(dict.fromkeys([*(body.get("warn") or []), "budget_exhausted"]))
        body["tok"] = count_json_tokens({**body, "tok": 0})
        if count_json_tokens(body) > budget:
            body["warn"] = list(dict.fromkeys([*(body.get("warn") or []), "budget_exhausted"]))
            body["tok"] = count_json_tokens({**body, "tok": 0})
        out.pages = pages
        out.status = status
        out.tokens = body["tok"]  # type: ignore[assignment]
        return body

    def map_payload(self, out: MapOutcome) -> dict:
        budget = max(200, out.budget)
        target = max(120, budget - 6)
        urls = list(out.urls)
        for _ in range(120):
            candidate: dict[str, Any] = {
                "status": out.status,
                "u": out.url,
                "n": len(urls),
                "urls": urls,
                "ms": out.elapsed_ms,
                "tok": 0,
            }
            if out.warnings:
                candidate["warn"] = out.warnings
            if out.sitemap_used:
                candidate["sitemap"] = True
            if count_json_tokens(candidate) <= target:
                break
            if not urls:
                break
            urls.pop()
            out.cut = True
        body: dict[str, Any] = {
            "status": out.status,
            "u": out.url,
            "n": len(urls),
            "urls": urls,
            "ms": out.elapsed_ms,
            "tok": 0,
        }
        if out.warnings:
            body["warn"] = out.warnings
        if out.sitemap_used:
            body["sitemap"] = True
        if out.cut:
            body["cut"] = True
        if not urls and out.urls:
            body["status"] = "partial"
            existing_warn: list[str] = [str(w) for w in (body.get("warn") or [])]
            body["warn"] = list(dict.fromkeys([*existing_warn, "budget_exhausted"]))
        body["tok"] = count_json_tokens({**body, "tok": 0})
        if count_json_tokens(body) > budget:
            existing_warn = [str(w) for w in (body.get("warn") or [])]
            body["warn"] = list(dict.fromkeys([*existing_warn, "budget_exhausted"]))
            body["tok"] = count_json_tokens({**body, "tok": 0})
        out.urls = urls
        out.tokens = body["tok"]  # type: ignore[assignment]
        return body
