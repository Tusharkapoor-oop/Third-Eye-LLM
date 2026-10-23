"""robots.txt handling for bounded crawling."""

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
        entry = RobotsEntry(parser=None, sitemaps=[], expires=now + self.s.robots_cache_ttl_s)
        try:
            resp = await self.fetcher.fetch(
                origin + "/robots.txt",
                headers={"Accept": "text/plain"},
                cache_ttl=self.s.robots_cache_ttl_s,
                max_bytes=512_000,
            )
            if resp.status == 200 and resp.body:
                parser = RobotFileParser()
                parser.parse(resp.text.splitlines())
                sitemaps = [
                    line.split(":", 1)[1].strip()
                    for line in resp.text.splitlines()
                    if line.lower().startswith("sitemap:") and ":" in line
                ]
                entry = RobotsEntry(parser=parser, sitemaps=sitemaps[:5], expires=now + self.s.robots_cache_ttl_s)
        except Exception:
            entry = RobotsEntry(parser=None, sitemaps=[], expires=now + 300)
        self._cache[origin] = entry
        return entry

    async def allowed(self, url: str) -> bool:
        entry = await self._get(url)
        if entry.parser is None:
            return True
        try:
            return entry.parser.can_fetch("*", url)
        except Exception:
            return True

    async def sitemaps(self, url: str) -> list[str]:
        entry = await self._get(url)
        return list(entry.sitemaps)
