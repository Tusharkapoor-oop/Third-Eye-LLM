"""Coverage tests for the optional browser path.

These tests avoid launching Chromium; they cover the no-Playwright path,
launch failures, and renderer/proxy accounting using stubs.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from weblens.config import Settings
from weblens.extract.browser import BrowserRenderer


def test_proxy_requests_zero_without_proxy():
    renderer = BrowserRenderer(Settings(allow_browser=True))
    assert renderer.proxy_requests == 0


def test_proxy_requests_delegates():
    renderer = BrowserRenderer(Settings(allow_browser=True))
    proxy = MagicMock()
    proxy.requests = 7
    renderer._proxy = proxy
    assert renderer.proxy_requests == 7


@pytest.mark.asyncio
async def test_ensure_uses_existing_browser():
    renderer = BrowserRenderer(Settings(allow_browser=True))
    fake = MagicMock()
    renderer._browser = fake
    assert await renderer._ensure() is fake


@pytest.mark.asyncio
async def test_ensure_no_playwright_raises(monkeypatch):
    renderer = BrowserRenderer(Settings(allow_browser=True))
    monkeypatch.setitem(sys.modules, "playwright.async_api", None)
    with pytest.raises(ModuleNotFoundError):
        await renderer._ensure()


class _FakeProxy:
    def __init__(self):
        self.closed = False

    async def start(self) -> str:
        return "http://127.0.0.1:1"

    async def close(self) -> None:
        self.closed = True


class _FakePlaywright:
    def __init__(self, browser):
        self._browser = browser

    async def start(self):
        return self._browser


@pytest.mark.asyncio
async def test_ensure_launch_failure_cleans_up(monkeypatch):
    renderer = BrowserRenderer(Settings(allow_browser=True))
    pw = MagicMock()
    pw.chromium.launch = AsyncMock(side_effect=RuntimeError("no chromium"))
    pw.stop = AsyncMock()
    proxy = _FakeProxy()

    fake_api = types.ModuleType("playwright.async_api")
    fake_api.async_playwright = lambda: _FakePlaywright(pw)
    fake_pkg = types.ModuleType("playwright")
    fake_pkg.async_api = fake_api
    monkeypatch.setitem(sys.modules, "playwright", fake_pkg)
    monkeypatch.setitem(sys.modules, "playwright.async_api", fake_api)
    monkeypatch.setattr("weblens.extract.browser.BrowserEgressProxy", lambda *a, **k: proxy)

    with pytest.raises(RuntimeError, match="no chromium"):
        await renderer._ensure()
    assert renderer._browser is None
    assert renderer._pw is None
    assert renderer._proxy is None
    assert proxy.closed is True
    pw.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_render_without_browser_launches_and_routes(monkeypatch):
    renderer = BrowserRenderer(Settings(allow_browser=True))
    fake_page = AsyncMock()
    fake_page.url = "https://example.com/final"
    fake_page.content = AsyncMock(return_value="<html></html>")
    fake_page.set_default_timeout = MagicMock()
    fake_ctx = AsyncMock()
    fake_ctx.new_page = AsyncMock(return_value=fake_page)
    fake_browser = AsyncMock()
    fake_browser.new_context = AsyncMock(return_value=fake_ctx)

    async def fake_ensure():
        renderer._browser = fake_browser
        return fake_browser

    renderer._ensure = fake_ensure
    html, final = await renderer.render("https://example.com/page")
    assert html == "<html></html>"
    assert final == "https://example.com/final"
    fake_ctx.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_route_handler_aborts_bad_schemes():
    renderer = BrowserRenderer(Settings(allow_browser=True))
    renderer.policy = MagicMock()
    fake_page = AsyncMock()
    fake_page.url = "https://example.com/final"
    fake_page.content = AsyncMock(return_value="<html></html>")
    fake_page.set_default_timeout = MagicMock()
    handlers = []
    fake_page.route = AsyncMock(side_effect=lambda pattern, handler: handlers.append(handler))
    fake_ctx = AsyncMock()
    fake_ctx.new_page = AsyncMock(return_value=fake_page)
    fake_browser = AsyncMock()
    fake_browser.new_context = AsyncMock(return_value=fake_ctx)

    async def fake_ensure():
        return fake_browser

    renderer._ensure = fake_ensure
    html, final = await renderer.render("https://example.com")
    assert html == "<html></html>"
    assert final == "https://example.com/final"
    handler = handlers[0]

    route = AsyncMock()
    route.request.url = "mailto:a@b.com"
    route.request.resource_type = "document"
    await handler(route)
    route.abort.assert_awaited_once()
    route.continue_.assert_not_awaited()

    route = AsyncMock()
    route.request.url = "https://example.com/img.png"
    route.request.resource_type = "image"
    await handler(route)
    route.abort.assert_awaited_once()

    route = AsyncMock()
    route.request.url = "https://example.com/ok"
    route.request.resource_type = "document"
    await handler(route)
    route.continue_.assert_awaited_once()
    route.abort.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_closes_browser_and_playwright():
    renderer = BrowserRenderer(Settings(allow_browser=True))
    fake_browser = AsyncMock()
    fake_pw = AsyncMock()
    fake_proxy = MagicMock()
    fake_proxy.close = AsyncMock()
    renderer._browser = fake_browser
    renderer._pw = fake_pw
    renderer._proxy = fake_proxy
    await renderer.close()
    assert renderer._browser is None
    assert renderer._pw is None
    assert renderer._proxy is None
    fake_browser.close.assert_awaited_once()
    fake_pw.stop.assert_awaited_once()
    fake_proxy.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_is_idempotent():
    renderer = BrowserRenderer(Settings(allow_browser=True))
    await renderer.close()
    assert renderer._browser is None
