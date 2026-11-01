"""
Bounded Asynchronous Website Crawler
Performs depth-controlled, robots-compliant, cycle-safe website crawling.
"""

from __future__ import annotations

import asyncio
from collections import deque
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.engine.config import CONFIG
from src.engine.crawl.robots import RobotsManager
from src.engine.extract.extractor import DocumentExtractor
from src.engine.search.aggregator import get_domain, normalize_url
from src.engine.security import safe_fetch_url, validate_url_security


def is_trap_url(url: str) -> bool:
    """Detects common crawler traps like cyclic directories and infinite calendars."""
    parsed = urlparse(url)
    segments = [s.lower() for s in parsed.path.split("/") if s]
    if len(segments) > 7:
        return True
    # Check for consecutive identical segments (e.g. /tag/tag/)
    for i in range(len(segments) - 1):
        if segments[i] == segments[i + 1]:
            return True

    # Repeating segment check (e.g. /a/b/c/a/b/c or any segment appearing 3+ times)
    if len(segments) >= 4:
        for s in segments:
            if segments.count(s) >= 2 and len(set(segments)) < len(segments):
                # If duplicates make up a significant portion of the path
                if len(set(segments)) <= (len(segments) + 1) // 2:
                    return True
    # Infinite calendar/filter patterns
    lower_q = parsed.query.lower()
    for trap_param in ("calendar", "month=", "year=", "date=", "filter=", "sort="):
        if trap_param in lower_q:
            return True
    return False

class WebsiteCrawler:
    def __init__(self):
        self.robots_manager = RobotsManager()
        self.extractor = DocumentExtractor()

    async def crawl(
        self,
        seed_url: str,
        max_depth: int = 1,
        max_pages: int = 5,
        allowed_paths: list[str] | None = None,
        max_tokens_per_page: int = 800
    ) -> dict:
        is_safe, reason, _ = validate_url_security(seed_url)
        if not is_safe:
            return {"status": "blocked", "error": f"Security block: {reason}", "pages": []}

        max_depth = min(max(max_depth, 0), CONFIG.max_crawl_depth)
        max_pages = min(max(max_pages, 1), CONFIG.max_crawl_pages)

        seed_domain = get_domain(seed_url)
        normalized_seed = normalize_url(seed_url)
        queue: deque[tuple[str, int]] = deque([(normalized_seed, 0)])
        visited: set[str] = set()
        queued: set[str] = {normalized_seed}
        crawled_pages: list[dict] = []
        skipped_count = 0

        semaphore = asyncio.Semaphore(2)  # Polite concurrency limit

        async def process_page(current_url: str, depth: int) -> tuple[dict | None, list[str], int]:
            """Fetch one page and return its result plus undiscovered links."""
            if current_url in visited:
                return None, [], 0
            visited.add(current_url)

            if get_domain(current_url) != seed_domain:
                return None, [], 1
            if allowed_paths:
                parsed_path = urlparse(current_url).path
                if not any(parsed_path.startswith(p) for p in allowed_paths):
                    return None, [], 1
            if is_trap_url(current_url):
                return None, [], 1
            if not await self.robots_manager.can_fetch(current_url):
                return None, [], 1

            async with semaphore:
                doc = await self.extractor.extract_url(
                    current_url,
                    query=None,
                    mode="passages",
                    max_tokens=max_tokens_per_page,
                )

            if doc.status != "success":
                return None, [], 1

            page = {
                "url": doc.url,
                "title": doc.title,
                "depth": depth,
                "passages_count": len(doc.passages),
                "summary_snippet": " ".join(p.text for p in doc.passages[:2])[:300],
                "tokens_used": doc.tokens_used,
            }
            links: list[str] = []
            if depth < max_depth:
                try:
                    code, html_bytes, _, _ = await safe_fetch_url(current_url)
                    if code == 200 and html_bytes:
                        soup = BeautifulSoup(html_bytes, "html.parser")
                        for a in soup.find_all("a", href=True):
                            val = a.get("href")
                            href = val.strip() if isinstance(val, str) else (
                                val[0].strip() if isinstance(val, list) and val else ""
                            )
                            if href:
                                next_url = normalize_url(urljoin(current_url, href))
                                if next_url not in visited and get_domain(next_url) == seed_domain:
                                    links.append(next_url)
                except Exception:
                    pass
            return page, links, 0

        # Process each breadth level concurrently. The previous loop awaited
        # every page before starting the next one, leaving the semaphore idle.
        while queue and len(crawled_pages) < max_pages:
            batch: list[tuple[str, int]] = []
            remaining = max_pages - len(crawled_pages)
            while queue and len(batch) < remaining:
                batch.append(queue.popleft())
            results = await asyncio.gather(*(process_page(*node) for node in batch))
            for index, (page, links, skipped) in enumerate(results):
                skipped_count += skipped
                if page is not None and len(crawled_pages) < max_pages:
                    crawled_pages.append(page)
                for next_url in links:
                    if next_url not in visited and next_url not in queued:
                        queued.add(next_url)
                        queue.append((next_url, batch[index][1] + 1))

        return {
            "status": "completed",
            "seed_url": seed_url,
            "total_pages_crawled": len(crawled_pages),
            "skipped_urls": skipped_count,
            "pages": crawled_pages
        }
