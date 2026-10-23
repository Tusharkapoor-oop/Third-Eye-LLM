"""
Robots.txt Parser and Politeness Controller
Caches and evaluates robots.txt permissions and crawl delays per domain.
"""

from __future__ import annotations

import urllib.robotparser
from urllib.parse import urlparse

import httpx

from src.engine.config import CONFIG


class RobotsManager:
    def __init__(self):
        self._parsers: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._sitemaps: dict[str, list[str]] = {}

    async def get_parser(self, domain: str) -> urllib.robotparser.RobotFileParser:
        if domain in self._parsers:
            return self._parsers[domain]

        parser = urllib.robotparser.RobotFileParser()
        robots_url = f"https://{domain}/robots.txt"
        parser.set_url(robots_url)

        try:
            async with httpx.AsyncClient(headers={"User-Agent": CONFIG.user_agent}, timeout=5.0) as client:
                resp = await client.get(robots_url)
                if resp.status_code == 200:
                    lines = resp.text.splitlines()
                    parser.parse(lines)
                    # Extract sitemaps from robots.txt
                    sitemaps = []
                    for line in lines:
                        if line.lower().startswith("sitemap:"):
                            sitemaps.append(line.split(":", 1)[1].strip())
                    self._sitemaps[domain] = sitemaps
                else:
                    # If 404 or other status, default to allow all
                    parser.parse([])
        except Exception:
            # If robots.txt cannot be fetched, default to allow all
            parser.parse([])

        self._parsers[domain] = parser
        return parser

    async def can_fetch(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            parser = await self.get_parser(domain)
            return parser.can_fetch(CONFIG.user_agent, url)
        except Exception:
            return True

    def get_sitemaps_for_domain(self, domain: str) -> list[str]:
        return self._sitemaps.get(domain.lower(), [])
