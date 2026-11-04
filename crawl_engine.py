"""Graph Link Mapping and Deep Crawling Pipeline.

Implements sitemap/robots discovery, BFS link graph traversal, regex path filters,
in-flight semantic passage pruning, and an asynchronous crawl job state machine.
"""

from __future__ import annotations

import asyncio
import re
import time
import urllib.robotparser
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from extractor import TieredExtractor
from schemas import FailedItem, MapResponse, SourceItem, UnifiedResponse
from security import safe_fetch_url


class CrawlJobStatus(StrEnum):
    """Lifecycle states of an asynchronous crawl job."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class CrawlLinkGraph:
    """Directed link graph discovered during mapping or crawling."""

    nodes: list[str] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class CrawlJob:
    """Persistent state record for an asynchronous crawl job."""

    job_id: str
    base_url: str
    status: CrawlJobStatus = CrawlJobStatus.CREATED
    discovered_count: int = 0
    extracted_count: int = 0
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    error: str | None = None
    results: list[SourceItem] = field(default_factory=list)
    failed_results: list[FailedItem] = field(default_factory=list)
    link_graph: CrawlLinkGraph = field(default_factory=CrawlLinkGraph)
    _task: asyncio.Task[None] | None = None


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


class RobotsChecker:
    """Fetches and checks robots.txt rules per domain origin."""

    def __init__(self) -> None:
        self._cache: dict[str, urllib.robotparser.RobotFileParser] = {}

    async def can_fetch(self, url: str, user_agent: str = "*") -> bool:
        """Check whether user-agent is permitted to crawl url."""
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        if origin not in self._cache:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = f"{origin}/robots.txt"
            try:
                status, _, body = await safe_fetch_url(robots_url, timeout_s=3.0)
                if status == 200:
                    text = body.decode("utf-8", errors="replace")
                    rp.parse(text.splitlines())
                else:
                    rp.allow_all = True
            except Exception:
                rp.allow_all = True
            self._cache[origin] = rp

        return self._cache[origin].can_fetch(user_agent, url)


class CrawlEngine:
    """Provides website mapping (/map), deep crawling (/crawl), and managed async crawl jobs."""

    def __init__(self, extractor: TieredExtractor | None = None):
        self.extractor = extractor or TieredExtractor()
        self.robots_checker = RobotsChecker()
        self.jobs: dict[str, CrawlJob] = {}

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
        check_robots: bool = False,
    ) -> MapResponse:
        """Discover URL link graph using sitemap detection and BFS link traversal."""
        t0 = time.perf_counter()
        if not base_url or not base_url.strip():
            return MapResponse(url=base_url or "", discovered_urls=[], count=0, response_time=0.0)

        limit = max(1, min(int(limit or 50), 100))
        max_depth = max(1, min(int(max_depth or 2), 5))
        max_breadth = max(1, min(int(max_breadth or 20), 50))

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

            if check_robots:
                allowed = await self.robots_checker.can_fetch(current_url)
                if not allowed:
                    continue

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
        check_robots: bool = False,
    ) -> UnifiedResponse:
        """Crawl website URLs and extract content with in-flight semantic passage pruning."""
        t0 = time.perf_counter()
        if not base_url or not base_url.strip():
            return UnifiedResponse(query=base_url or "", answer="Empty URL", results=[], failed_results=[], response_time=0.0)

        limit = max(1, min(int(limit or 15), 50))

        map_res = await self.map_website(
            base_url,
            max_depth=max_depth,
            max_breadth=max_breadth,
            limit=limit,
            select_paths=select_paths,
            exclude_paths=exclude_paths,
            check_robots=check_robots,
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

    # ---------------------------------------------------------
    # Asynchronous Crawl Job State Machine
    # ---------------------------------------------------------

    async def _run_crawl_job(
        self,
        job: CrawlJob,
        max_depth: int,
        max_breadth: int,
        limit: int,
        select_paths: list[str] | None,
        exclude_paths: list[str] | None,
        instructions: str | None,
        chunks_per_source: int,
        check_robots: bool,
    ) -> None:
        """Internal worker executing a crawl job with state updates and cancellation checks."""
        job.status = CrawlJobStatus.RUNNING
        try:
            map_res = await self.map_website(
                job.base_url,
                max_depth=max_depth,
                max_breadth=max_breadth,
                limit=limit,
                select_paths=select_paths,
                exclude_paths=exclude_paths,
                check_robots=check_robots,
            )

            job.discovered_count = len(map_res.discovered_urls)
            job.link_graph.nodes = list(map_res.discovered_urls)
            if job.base_url not in job.link_graph.nodes:
                job.link_graph.nodes.insert(0, job.base_url)

            # Build edges from base_url to discovered nodes
            job.link_graph.edges = [(job.base_url, u) for u in map_res.discovered_urls if u != job.base_url]

            target_urls = map_res.discovered_urls[:limit] or [job.base_url]

            for u in target_urls:
                # Check for cancellation before each URL extraction
                if job.status == CrawlJobStatus.CANCELLED:
                    return

                try:
                    res = await self.extractor.extract_url(
                        u,
                        query=instructions,
                        chunks_per_source=chunks_per_source,
                    )
                    if isinstance(res, SourceItem):
                        job.results.append(res)
                        job.extracted_count += 1
                    elif isinstance(res, FailedItem):
                        job.failed_results.append(res)
                except Exception as e:
                    job.failed_results.append(FailedItem(url=u, error=str(e), blocked_by_waf=False))

            job.status = CrawlJobStatus.COMPLETED
            job.completed_at = time.time()

        except asyncio.CancelledError:
            job.status = CrawlJobStatus.CANCELLED
            job.completed_at = time.time()
            raise
        except Exception as e:
            job.status = CrawlJobStatus.FAILED
            job.error = str(e)
            job.completed_at = time.time()

    def start_crawl_job(
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
        check_robots: bool = False,
    ) -> CrawlJob:
        """Create and launch a background managed crawl job."""
        job_id = f"crawl_{uuid.uuid4().hex[:12]}"
        job = CrawlJob(job_id=job_id, base_url=base_url)
        self.jobs[job_id] = job

        task = asyncio.create_task(
            self._run_crawl_job(
                job,
                max_depth=max_depth,
                max_breadth=max_breadth,
                limit=limit,
                select_paths=select_paths,
                exclude_paths=exclude_paths,
                instructions=instructions,
                chunks_per_source=chunks_per_source,
                check_robots=check_robots,
            )
        )
        job._task = task
        return job

    def get_crawl_status(self, job_id: str) -> CrawlJob | None:
        """Retrieve state for a managed crawl job."""
        return self.jobs.get(job_id)

    def cancel_crawl_job(self, job_id: str) -> bool:
        """Cancel an ongoing crawl job."""
        job = self.jobs.get(job_id)
        if not job:
            return False

        if job.status in (CrawlJobStatus.CREATED, CrawlJobStatus.RUNNING):
            job.status = CrawlJobStatus.CANCELLED
            if job._task and not job._task.done():
                job._task.cancel()
            job.completed_at = time.time()
            return True
        return False
