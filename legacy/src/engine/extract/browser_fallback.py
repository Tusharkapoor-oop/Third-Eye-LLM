"""
Headless Browser Fallback for JavaScript-Rendered SPAs.
Executes native Microsoft Edge or Google Chrome in headless DOM-dump mode
only when fast HTTP extraction yields insufficient or blank content.
"""

from __future__ import annotations

import asyncio
import os
import subprocess

from src.engine.config import CONFIG
from src.engine.security import validate_url_security

KNOWN_BROWSER_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

def find_browser_executable() -> str | None:
    if CONFIG.browser_binary_path and os.path.exists(CONFIG.browser_binary_path):
        return CONFIG.browser_binary_path
    for p in KNOWN_BROWSER_PATHS:
        if os.path.exists(p):
            return p
    return None

async def fetch_rendered_dom(url: str, timeout_sec: float = 12.0) -> tuple[bool, str]:
    """
    Launches headless Edge or Chrome to render client-side JavaScript and dump the DOM.
    Returns: (success: bool, rendered_html_or_error: str)
    """
    is_safe, reason, _ = validate_url_security(url)
    if not is_safe:
        return False, f"Security block: {reason}"

    browser_exe = find_browser_executable()
    if not browser_exe:
        return False, "No compatible browser (Edge/Chrome) found on host system."

    proxy = None
    proxy_flags: list[str] = []
    try:
        try:
            from weblens.config import Settings
            from weblens.net.browser_proxy import BrowserEgressProxy
        except ImportError:
            from src.weblens.config import Settings
            from src.weblens.net.browser_proxy import BrowserEgressProxy

        proxy = BrowserEgressProxy(Settings(search_providers="ddg", allow_private_networks=False))
        proxy_url = await proxy.start()
        proxy_flags = [
            f"--proxy-server={proxy_url}",
            "--proxy-bypass-list=<-loopback>",
            "--disable-extensions",
            "--disable-sync",
            "--disable-quic",
            "--dns-prefetch-disable",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        ]
    except Exception:
        proxy = None
        proxy_flags = []

    cmd = [
        browser_exe,
        "--headless=new",
        "--disable-gpu",
        "--dump-dom",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        *proxy_flags,
        f"--timeout={int(timeout_sec * 1000)}",
        url
    ]

    def _run():
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec,
                shell=False
            )
            if res.returncode == 0 and res.stdout:
                return True, res.stdout
            return False, res.stderr or "Empty DOM returned by headless browser"
        except subprocess.TimeoutExpired:
            return False, f"Headless browser timed out after {timeout_sec} seconds"
        except Exception as e:
            return False, f"Browser execution error: {e}"

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _run)
    finally:
        if proxy is not None:
            await proxy.close()

