"""Optional JavaScript rendering with Playwright, isolated per request."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any
from urllib.parse import urlsplit

from ..config import Settings
from ..net.browser_proxy import BrowserEgressProxy
from ..net.ssrf import DestinationPolicy
from ..urls import host_of


class BrowserRenderer:
    def __init__(self, settings: Settings):
        self.s = settings
        self.policy = DestinationPolicy(settings)
        self._pw: Any = None
        self._browser: Any = None
        self._proxy: BrowserEgressProxy | None = None
        self._lock = asyncio.Lock()

    async def _ensure(self):
        if self._browser is not None:
            return self._browser
        async with self._lock:
            if self._browser is not None:
                return self._browser
            from playwright.async_api import async_playwright

            proxy = BrowserEgressProxy(self.s, self.policy)
            proxy_url = await proxy.start()
            self._proxy = proxy
            try:
                self._pw = await async_playwright().start()
                self._browser = await self._pw.chromium.launch(
                    headless=True,
                    proxy={"server": proxy_url},
                    args=[
                        "--disable-dev-shm-usage",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-background-networking",
                        "--disable-extensions",
                        "--disable-sync",
                        "--disable-quic",
                        "--dns-prefetch-disable",
                        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                        # Chromium normally bypasses proxies for loopback; the
                        # test path and explicitly enabled private networks need
                        # those requests to go through the policy proxy too.
                        "--proxy-bypass-list=<-loopback>",
                    ],
                )
            except Exception:
                self._browser = None
                if self._pw is not None:
                    with contextlib.suppress(Exception):
                        await self._pw.stop()
                    self._pw = None
                with contextlib.suppress(Exception):
                    await proxy.close()
                self._proxy = None
                raise
            return self._browser

    @property
    def proxy_requests(self) -> int:
        """Diagnostics: requests handled by the egress proxy in this renderer."""
        return self._proxy.requests if self._proxy is not None else 0

    async def render(self, url: str) -> tuple[str, str]:
        """Return (html, final_url). Raises on launch/navigation failure."""
        browser = await self._ensure()
        ctx = await browser.new_context(
            user_agent=self.s.user_agent,
            locale="en-US",
            java_script_enabled=True,
            service_workers="block",
            accept_downloads=False,
            ignore_https_errors=False,
        )
        page = await ctx.new_page()
        page.set_default_timeout(self.s.browser_timeout_s * 1000)

        async def route_handler(route) -> None:
            try:
                req_url = route.request.url
                p = urlsplit(req_url)
                if p.scheme not in {"http", "https"}:
                    await route.abort()
                    return
                self.policy.check_hostname(p.hostname or "")
                self.policy.check_port(p.port or (443 if p.scheme == "https" else 80))
                rtype = route.request.resource_type
                if rtype in {"image", "media", "font", "stylesheet"}:
                    await route.abort()
                    return
                await route.continue_()
            except Exception:
                await route.abort()

        await page.route("**/*", route_handler)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=self.s.browser_timeout_s * 1000)
            await page.wait_for_timeout(900)
            final = page.url
            self.policy.check_hostname(host_of(final))
            html = await page.content()
            return html, final
        finally:
            await ctx.close()

    async def close(self) -> None:
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None
        if self._proxy is not None:
            with contextlib.suppress(Exception):
                await self._proxy.close()
            self._proxy = None
