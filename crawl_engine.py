"""Graph Link Mapping and Deep Crawling Pipeline.

Implements sitemap/robots discovery, BFS link graph traversal, regex path filters,
and in-flight semantic passage pruning.
"""

from __future__ import annotations

import asyncio
import re
import time
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from config import CONFIG
from schemas import FailedItem, MapResponse, SourceItem, UnifiedResponse
from extractor import TieredExtractor
from security import safe_fetch_url, SecurityValidationError


def is_same_site(url_a: str, url_b: str) -> bool:
    """Check if two URLs share the same root domain / origin."""
    try:
        netloc_a = urlparse(url_a).netloc.lower()
        netloc_b = urlparse(url_b).netloc.lower()
        # Strip www.
        netloc_a = netloc_a[4:] if netloc_a.startswith("www.") else netloc_a
        netloc_b = netloc_b[4:] if netloc_b.startswith("www.") else netloc_b
        return netloc_a == netloc_b
    except Exception:
        return False


def matches_path_filters(
    path: str,
    select_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
) -> bool:
    """Filter URL paths based on regex include and exclude rules."""
    if exclude_paths:
        for pattern in exclude_paths:
            if re.search(pattern, path, re.IGNORECASE):
                return False

    if select_paths:
        return any(re.search(pattern, path, re.IGNORECASE) for pattern in select_paths)

    return True


class CrawlEngine:
    """Provides website mapping (/map) and in-depth content crawling (/crawl)."""

    def __init__(self, extractor: TieredExtractor | None = None):
        self.extractor = extractor or TieredExtractor()

    async def _discover_sitemap_urls(self, base_url: str, limit: int = 50) -> list[str]:
        """Attempt discovery of URLs from sitemap.xml."""
        parsed = urlparse(base_url)
        sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
        discovered: list[str] = []

        try:
            status, _, body = await safe_fetch_url(sitemap_url, timeout_s=3.0)
            if status == 200:
                text = body.decode("utf-8", errors="replace")
                urls = re.findall(r"<loc>\s*(https?://[^<\s]+)\s*</loc>", text, re.IGNORECASE)
                for u in urls:
                    if is_same_site(base_url, u):
                        discovered.append(u.strip())
                    if len(discovered) >= limit:
                        break
        except Exception:
            pass

        return discovered

    async def map_website(
        self,
        base_url: str,
        *,
        max_depth: int = 2,
        max_breadth: int = 20,
        limit: int = 50,
        select_paths: list[str] | None = None,
        exclude_paths: list[str] | None = None,
    ) -> MapResponse:
        """Discover URL link graph using sitemap detection and BFS link traversal."""
        t0 = time.perf_counter()
        visited: set[str] = set()
        to_visit: list[tuple[str, int]] = [(base_url, 0)]
        discovered: list[str] = []

        # Try fast sitemap discovery first
        sitemap_urls = await self._discover_sitemap_urls(base_url, limit=limit)
        for u in sitemap_urls:
            p = urlparse(u).path
            if matches_path_filters(p, select_paths, exclude_paths):
                if u not in discovered:
                    discovered.append(u)
            if len(discovered) >= limit:
                elapsed = round(time.perf_counter() - t0, 3)
                return MapResponse(url=base_url, discovered_urls=discovered, count=len(discovered), response_time=elapsed)

        # BFS Link Graph Traversal
        while to_visit and len(discovered) < limit:
            current_url, depth = to_visit.pop(0)
            if current_url in visited or depth > max_depth:
                continue
            visited.add(current_url)

            p = urlparse(current_url).path
            if matches_path_filters(p, select_paths, exclude_paths):
                if current_url not in discovered:
                    discovered.append(current_url)

            if depth >= max_depth:
                continue

            try:
                status, _, body = await safe_fetch_url(current_url, timeout_s=4.0)
                if status != 200:
                    continue

                html = body.decode("utf-8", errors="replace")
                soup = BeautifulSoup(html, "html.parser")
                branch_count = 0

                for a_tag in soup.find_all("a", href=True):
                    raw_href = a_tag["href"].strip()
                    resolved = urljoin(current_url, raw_href)
                    if is_same_site(base_url, resolved) and resolved not in visited:
                        to_visit.append((resolved, depth + 1))
                        branch_count += 1
                        if branch_count >= max_breadth:
                            break
            except Exception:
                continue

        elapsed = round(time.perf_counter() - t0, 3)
        return MapResponse(
            url=base_url,
            discovered_urls=discovered[:limit],
            count=len(discovered[:limit]),
            response_time=elapsed,
        )

    async def crawl_website(
        self,
        base_url: str,
        *,
        max_depth: int = 2,
        max_breadth: int = 20,
        limit: int = 15,
        select_paths: list[str] | None = None,
        exclude_paths: list[str] | None = None,
        instructions: str | None = None,
        chunks_per_source: int = 3,
        extract_depth: str = "basic",
    ) -> UnifiedResponse:
        """Crawl website URLs and extract content with in-flight semantic passage pruning."""
        t0 = time.perf_counter()

        map_res = await self.map_website(
            base_url,
            max_depth=max_depth,
            max_breadth=max_breadth,
            limit=limit,
            select_paths=select_paths,
            exclude_paths=exclude_paths,
        )

        target_urls = map_res.discovered_urls[:limit]
        if not target_urls:
            target_urls = [base_url]

        extract_tasks = [
            self.extractor.extract_url(
                u,
                query=instructions,
                chunks_per_source=chunks_per_source,
                force_tier2=(extract_depth == "advanced"),
            )
            for u in target_urls
        ]

        results = await asyncio.gather(*extract_tasks, return_exceptions=True)

        sources: list[SourceItem] = []
        failed: list[FailedItem] = []

        for r in results:
            if isinstance(r, SourceItem):
                sources.append(r)
            elif isinstance(r, FailedItem):
                failed.append(r)
            elif isinstance(r, Exception):
                failed.append(FailedItem(url="crawl_error", error=str(r), blocked_by_waf=False))

        elapsed = round(time.perf_counter() - t0, 3)
        return UnifiedResponse(
            query=instructions or base_url,
            answer=f"Crawled {len(sources)} pages from {base_url} in {elapsed}s",
            results=sources,
            failed_results=failed,
            response_time=elapsed,
            source_engine="local_live",
        )

