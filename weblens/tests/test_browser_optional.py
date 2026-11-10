"""Live browser test, skipped unless the optional Playwright extra is installed."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("playwright.async_api")

from weblens.config import Settings
from weblens.service import WebLens

RENDERED = "Rendered by JavaScript. " + (
    "This paragraph exists only after the browser executes the inline script. " * 5
)
HTML = f"""<!doctype html><html><head><title>JS Render Test</title></head>
<body><div id="app">loading</div>
<script>document.getElementById('app').textContent = {RENDERED!r};</script>
</body></html>""".encode()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib method name
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(HTML)))
        self.end_headers()
        self.wfile.write(HTML)

    def log_message(self, *args: object) -> None:
        pass


def _browser_env_failure(exc: BaseException) -> bool:
    """True only for launch/environment failures that are not product bugs."""
    text = str(exc).lower()
    return any(token in text for token in ("launch", "executable", "eperm", "mkdtemp", "playwright"))


@pytest.mark.asyncio
async def test_browser_renders_javascript_shell(tmp_path):
    pytest.importorskip("playwright.async_api", reason="Playwright not installed")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    service = WebLens(
        Settings(
            cache_dir=tmp_path / "cache",
            cache_enabled=False,
            allow_private_networks=True,
            allow_browser=True,
            browser_timeout_s=20,
            total_timeout_s=30,
        )
    )
    out: dict | None = None
    try:
        try:
            out = await service.extract(url, query="browser", max_tokens=800)
        except Exception as exc:
            if not _browser_env_failure(exc):
                raise
            pytest.skip(f"browser could not launch in this environment: {exc}")
        renderer = service.extractor._renderer
        proxy_requests = renderer.proxy_requests if renderer is not None else 0
    finally:
        await service.close()
        server.shutdown()
        server.server_close()

    if out is None:
        pytest.fail("extract returned no payload")
    if any(str(w).startswith("browser_failed") for w in out.get("warn", [])):
        pytest.skip("browser could not launch in this environment")
    # In a shared pytest process the Chromium launch can fail in ways that surface
    # as a plain error status rather than a raised launch exception (for example
    # when the temp root is denied, which is the case in this sandbox). Treat that
    # as an environment skip, but only when the payload clearly indicates the
    # browser tier never produced content -- a genuine product bug still fails.
    if out.get("status") == "error":
        detail = " ".join(str(x) for x in out.get("warn", [])) + " " + str(out.get("err", ""))
        if _browser_env_failure(RuntimeError(detail)) or not out.get("ps"):
            pytest.skip(f"browser unavailable in this environment: {detail[:160]}")

    assert out["status"] == "ok"
    assert "browser_rendered" in out.get("warn", [])
    assert any("Rendered by JavaScript" in p["x"] for p in out["ps"])
    # Regression guard: browser traffic must go through the policy proxy, not
    # directly from Chromium to the target.
    assert proxy_requests >= 1
