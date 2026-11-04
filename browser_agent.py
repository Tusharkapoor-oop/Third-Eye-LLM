"""Controlled AI Browser Infrastructure for External AI Agents.

Provides:
- Sandboxed Playwright browser sessions with lifecycle management (create, list, close)
- Strict 4-Tier Permission Model (0: Read-Only, 1: Reversible, 2: Form Prep, 3: Requires Approval, 4: Prohibited)
- Structured observation (accessibility snapshot, visible elements, forms, links)
- Controlled interaction (click, fill, type, select, scroll, press key)
- Pre-navigation SSRF boundary validation preventing access to loopback and private networks
"""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from config import CONFIG
from security import SecurityValidationError, resolve_and_verify_host, validate_public_url

PermissionLevel = Literal[0, 1, 2, 3, 4]


@dataclass
class BrowserSession:
    """Active controlled browser session state."""

    session_id: str
    created_at: float
    last_activity: float
    permission_level: PermissionLevel
    current_url: str = "about:blank"
    page_title: str = ""
    is_active: bool = True
    history: list[str] = field(default_factory=list)
    approved_actions: set[str] = field(default_factory=set)
    _page: Any = None
    _context: Any = None


class ControlledBrowserAgent:
    """Controlled browser automation service tailored for external AI agents."""

    def __init__(self, session_timeout_s: float = 300.0):
        self.session_timeout_s = session_timeout_s
        self.sessions: dict[str, BrowserSession] = {}
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self):
        """Lazy-initialize warm Chromium instance."""
        if self._browser is None:
            async with self._lock:
                if self._browser is None:
                    from playwright.async_api import async_playwright

                    self._playwright = await async_playwright().start()
                    self._browser = await self._playwright.chromium.launch(
                        headless=CONFIG.headless,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-gpu",
                            "--disable-dev-shm-usage",
                            "--no-sandbox",
                        ],
                    )
        return self._browser

    async def create_session(
        self,
        permission_level: PermissionLevel = 1,
        session_id: str | None = None,
    ) -> BrowserSession:
        """Create a new isolated browser session."""
        if permission_level not in (0, 1, 2, 3, 4):
            raise ValueError("permission_level must be one of 0, 1, 2, 3, or 4")
        browser = await self._ensure_browser()
        sid = session_id or str(uuid.uuid4())[:12]

        context = await browser.new_context(
            user_agent=CONFIG.user_agent,
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=False,
        )
        page = await context.new_page()

        # Abort heavy media and revalidate every browser request at egress.
        async def guard_request(route: Any) -> None:
            request_url = route.request.url
            if request_url.startswith(("about:", "data:", "blob:")):
                await route.continue_()
                return
            try:
                host, port = validate_public_url(request_url)
                resolve_and_verify_host(host, port)
            except (SecurityValidationError, ValueError):
                await route.abort("blockedbyclient")
                return
            if route.request.resource_type in ("image", "media", "font"):
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", guard_request)

        session = BrowserSession(
            session_id=sid,
            created_at=time.time(),
            last_activity=time.time(),
            permission_level=permission_level,
            _page=page,
            _context=context,
        )
        self.sessions[sid] = session
        return session

    def get_session(self, session_id: str) -> BrowserSession:
        """Retrieve active session, verifying timeout."""
        session = self.sessions.get(session_id)
        if not session or not session.is_active:
            raise KeyError(f"Session '{session_id}' not found or inactive")

        if time.time() - session.last_activity > self.session_timeout_s:
            session.is_active = False
            raise TimeoutError(f"Session '{session_id}' timed out due to inactivity")

        session.last_activity = time.time()
        return session

    async def navigate(self, session_id: str, url: str) -> dict[str, Any]:
        """Navigate session to target URL after validating network security boundaries."""
        session = self.get_session(session_id)

        # Level 4 is a hard prohibition boundary, not an elevated capability.
        if session.permission_level == 4:
            raise PermissionError("Permission level 4 prohibits browser actions")
        if session.permission_level < 1:
            raise PermissionError("Session permission level 0 (Read-Only) does not permit navigation")

        # SSRF socket IP and forbidden scheme check
        validate_public_url(url)

        page = session._page
        response = await page.goto(url, wait_until="domcontentloaded", timeout=CONFIG.page_timeout_ms)

        # Re-validate destination URL after any HTTP redirects
        current = page.url
        validate_public_url(current)

        session.current_url = current
        session.page_title = await page.title()
        session.history.append(current)

        return {
            "session_id": session_id,
            "url": current,
            "title": session.page_title,
            "status_code": response.status if response else 200,
            "success": True,
        }

    async def back(self, session_id: str) -> dict[str, Any]:
        """Navigate backward in the isolated session history."""
        session = self.get_session(session_id)
        if session.permission_level in (0, 4):
            raise PermissionError("This permission level does not permit navigation")
        response = await session._page.go_back(timeout=CONFIG.page_timeout_ms)
        session.current_url = session._page.url
        session.page_title = await session._page.title()
        return {
            "session_id": session_id,
            "url": session.current_url,
            "title": session.page_title,
            "status_code": response.status if response else 200,
            "success": True,
        }

    async def forward(self, session_id: str) -> dict[str, Any]:
        """Navigate forward in the isolated session history."""
        session = self.get_session(session_id)
        if session.permission_level in (0, 4):
            raise PermissionError("This permission level does not permit navigation")
        response = await session._page.go_forward(timeout=CONFIG.page_timeout_ms)
        session.current_url = session._page.url
        session.page_title = await session._page.title()
        return {
            "session_id": session_id,
            "url": session.current_url,
            "title": session.page_title,
            "status_code": response.status if response else 200,
            "success": True,
        }

    async def refresh(self, session_id: str) -> dict[str, Any]:
        """Reload the current public page in the isolated session."""
        session = self.get_session(session_id)
        if session.permission_level in (0, 4):
            raise PermissionError("This permission level does not permit navigation")
        validate_public_url(session.current_url)
        response = await session._page.reload(timeout=CONFIG.page_timeout_ms)
        session.current_url = session._page.url
        session.page_title = await session._page.title()
        return {
            "session_id": session_id,
            "url": session.current_url,
            "title": session.page_title,
            "status_code": response.status if response else 200,
            "success": True,
        }

    async def observe(self, session_id: str) -> dict[str, Any]:
        """Produce structured accessibility and DOM snapshot for AI decision making."""
        session = self.get_session(session_id)
        page = session._page

        title = await page.title()
        url = page.url

        # Extract structured visible elements
        elements_info = await page.evaluate(
            """() => {
                const results = [];
                // Collect headings
                document.querySelectorAll('h1, h2, h3').forEach((el, idx) => {
                    if (el.innerText.trim()) {
                        results.push({type: 'heading', tag: el.tagName.toLowerCase(), text: el.innerText.trim().slice(0, 100)});
                    }
                });
                // Collect interactive links
                document.querySelectorAll('a[href]').forEach((el, idx) => {
                    if (idx < 25 && el.innerText.trim()) {
                        results.push({type: 'link', text: el.innerText.trim().slice(0, 80), href: el.href});
                    }
                });
                // Collect form controls
                document.querySelectorAll('input, button, select, textarea').forEach((el, idx) => {
                    results.push({
                        type: 'control',
                        tag: el.tagName.toLowerCase(),
                        id: el.id || '',
                        name: el.name || '',
                        role: el.type || el.getAttribute('role') || '',
                        placeholder: el.placeholder || '',
                        text: el.innerText ? el.innerText.trim().slice(0, 50) : (el.value || '')
                    });
                });
                return results;
            }"""
        )

        visible_text = await page.evaluate("() => document.body.innerText.slice(0, 3000)")

        return {
            "session_id": session_id,
            "url": url,
            "title": title,
            "interactive_elements_count": len(elements_info),
            "elements": elements_info[:40],
            "text_preview": visible_text[:1500],
            "permission_level": session.permission_level,
        }

    async def interact(
        self,
        session_id: str,
        action: Literal["click", "fill", "type", "select", "press_key", "scroll"],
        target: str,
        value: str = "",
        approval_token: str | None = None,
    ) -> dict[str, Any]:
        """Execute controlled interaction adhering to permission policies."""
        session = self.get_session(session_id)
        page = session._page

        # Enforcement of Permission Tiers
        if session.permission_level == 4:
            raise PermissionError("Permission level 4 prohibits browser actions")
        if action in ("click", "press_key", "scroll") and session.permission_level < 1:
            raise PermissionError("Action requires permission level >= 1 (Reversible Interaction)")

        if action in ("fill", "type", "select") and session.permission_level < 2:
            raise PermissionError("Form input requires permission level >= 2 (Form Preparation)")

        # Level 3 irreversible actions require explicit approval token
        is_submitting_action = action == "click" and any(
            sub in target.lower() for sub in ("submit", "buy", "purchase", "delete", "checkout", "transfer")
        )
        if is_submitting_action:
            if session.permission_level < 3:
                raise PermissionError(
                    f"Irreversible action '{target}' blocked: requires permission Level 3 and explicit human approval."
                )
            if not approval_token or approval_token not in session.approved_actions:
                raise PermissionError(
                    f"Action '{target}' requires valid action-specific approval_token."
                )

        # Execute safe DOM interaction
        if action == "click":
            await page.click(target, timeout=5000)
        elif action == "fill":
            await page.fill(target, value, timeout=5000)
        elif action == "type":
            await page.type(target, value, timeout=5000)
        elif action == "select":
            await page.select_option(target, value, timeout=5000)
        elif action == "press_key":
            await page.keyboard.press(target)
        elif action == "scroll":
            delta_y = int(value or "500") if target == "down" else -int(value or "500")
            await page.mouse.wheel(0, delta_y)

        session.last_activity = time.time()
        return {
            "session_id": session_id,
            "action": action,
            "target": target,
            "success": True,
            "current_url": page.url,
        }

    async def take_screenshot(self, session_id: str) -> str:
        """Capture viewport screenshot as base64-encoded string."""
        session = self.get_session(session_id)
        page = session._page
        img_bytes = await page.screenshot(type="jpeg", quality=60)
        return base64.b64encode(img_bytes).decode("utf-8")

    async def close_session(self, session_id: str) -> None:
        """Cleanly close session context and page."""
        session = self.sessions.pop(session_id, None)
        if session:
            session.is_active = False
            try:
                if session._page:
                    await session._page.close()
            except Exception:
                pass
            try:
                if session._context:
                    await session._context.close()
            except Exception:
                pass

    async def close(self) -> None:
        """Cleanly close all browser sessions and Chromium process."""
        for sid in list(self.sessions.keys()):
            await self.close_session(sid)

        async with self._lock:
            if self._browser is not None:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._playwright is not None:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

            try:
                import psutil
                killed = []
                for child in psutil.Process().children(recursive=True):
                    if any(b in child.name().lower() for b in ("chrome", "chromium", "playwright")):
                        try:
                            child.kill()
                            killed.append(child)
                        except Exception:
                            pass
                if killed:
                    psutil.wait_procs(killed, timeout=3.0)
            except Exception:
                pass


# Singleton browser agent
browser_agent = ControlledBrowserAgent()
