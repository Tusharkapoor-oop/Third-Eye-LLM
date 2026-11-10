"""robots.txt handling for bounded crawling.

The default behaviour is deliberately fail-open: a missing, malformed, or
unreachable robots.txt allows crawling. This keeps WebLens usable on sites
with transient errors and matches the historical de-facto behaviour.

Operators who want fail-closed semantics can set
``WEBLENS_ROBOTS_FAIL_CLOSED=true`` so that any fetch or parse failure is
treated as a deny. In both modes a warning is returned so callers can see
which decision was made.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from ..config import Settings
from ..net import SafeFetcher


@dataclass
class RobotsEntry:
    parser: RobotFileParser | None
    sitemaps: list[str]
    expires: float
    warning: str = ""


class RobotsPolicy:
    def __init__(self, settings: Settings, fetcher: SafeFetcher):
        self.s = settings
        self.fetcher = fetcher
        self._cache: dict[str, RobotsEntry] = {}

    async def _get(self, url: str) -> RobotsEntry:
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        now = time.time()
        hit = self._cache.get(origin)
        if hit and hit.expires > now:
            return hit
        entry = await self._fetch_entry(origin, now)
        self._cache[origin] = entry
        return entry

    async def _fetch_entry(self, origin: str, now: float) -> RobotsEntry:
        """Fetch and parse robots.txt, returning a visible warning on failure."""
        ttl = self.s.robots_cache_ttl_s
        fail_closed = getattr(self.s, "robots_fail_closed", False)
        try:
            resp = await self.fetcher.fetch(
                origin + "/robots.txt",
                headers={"Accept": "text/plain"},
                cache_ttl=ttl,
                max_bytes=512_000,
            )
        except Exception as exc:
            warning = f"robots_fetch_failed:{type(exc).__name__}"
            return RobotsEntry(
                parser=None,
                sitemaps=[],
                expires=now + 300,
                warning=warning,
            )
        if not resp.ok:
            # Missing robots.txt is normal (404). Treat as fail-open
            # unless configured otherwise; still note the status.
            warning = f"robots_http_status:{resp.status}"
            if fail_closed:
                denied = RobotFileParser()
                # A deny-all rule for the "*" user agent.
                denied.parse(["User-agent: *", "Disallow: /"])
                return RobotsEntry(parser=denied, sitemaps=[], expires=now + 300, warning=warning)
            return RobotsEntry(parser=None, sitemaps=[], expires=now + ttl, warning=warning)
        if not resp.body:
            warning = "robots_empty_response"
            if fail_closed:
                denied = RobotFileParser()
                denied.parse(["User-agent: *", "Disallow: /"])
                return RobotsEntry(parser=denied, sitemaps=[], expires=now + 300, warning=warning)
            return RobotsEntry(parser=None, sitemaps=[], expires=now + ttl, warning=warning)
        try:
            lines = resp.text.splitlines()
            parser = RobotFileParser()
            parser.parse(lines)
            sitemaps = [
                line.split(":", 1)[1].strip() for line in lines if line.lower().startswith("sitemap:") and ":" in line
            ]
            return RobotsEntry(
                parser=parser,
                sitemaps=sitemaps[:5],
                expires=now + ttl,
                warning="",
            )
        except Exception as exc:
            warning = f"robots_parse_failed:{type(exc).__name__}"
            if fail_closed:
                denied = RobotFileParser()
                denied.parse(["User-agent: *", "Disallow: /"])
                return RobotsEntry(parser=denied, sitemaps=[], expires=now + 300, warning=warning)
            return RobotsEntry(parser=None, sitemaps=[], expires=now + 300, warning=warning)

    async def allowed(self, url: str) -> tuple[bool, str]:
        """Return (allowed, warning). Warnings propagate to crawl results."""
        entry = await self._get(url)
        if entry.parser is None:
            return True, entry.warning
        try:
            return entry.parser.can_fetch("*", url), entry.warning
        except Exception as exc:
            warning = f"robots_parse_failed:{type(exc).__name__}"
            if getattr(self.s, "robots_fail_closed", False):
                return False, warning
            return True, warning

    async def sitemaps(self, url: str) -> tuple[list[str], str]:
        """Return discovered sitemaps and any fetch warning."""
        entry = await self._get(url)
        return list(entry.sitemaps), entry.warning
