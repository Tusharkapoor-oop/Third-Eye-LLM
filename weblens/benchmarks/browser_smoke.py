"""Measure the optional Playwright browser path against a local JavaScript shell.

This is intentionally a live smoke test, not part of the default test suite:
it needs ``playwright`` and an installed Chromium build.

    uv sync --extra browser
    uv run playwright install chromium
    uv run python benchmarks/browser_smoke.py
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import platform
import statistics
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from weblens.config import Settings
from weblens.extract.browser import BrowserRenderer
from weblens.service import WebLens

RENDERED = "Rendered by JavaScript. " + (
    "This paragraph exists only after the browser executes the inline script. " * 5
)
HTML = f"""<!doctype html><html><head><title>JS Render Test</title></head>
<body><div id="app">loading</div>
<script>document.getElementById('app').textContent = {RENDERED!r};</script>
</body></html>""".encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib method name
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(HTML)))
        self.end_headers()
        self.wfile.write(HTML)

    def log_message(self, *args: object) -> None:
        pass


async def _local_run(cache_dir: Path, url: str) -> dict[str, Any]:
    service = WebLens(
        Settings(
            cache_dir=cache_dir,
            cache_enabled=False,
            allow_private_networks=True,
            allow_browser=True,
            browser_timeout_s=20,
            total_timeout_s=30,
        )
    )
    started = time.perf_counter()
    try:
        out = await service.extract(url, query="browser", max_tokens=800)
        renderer = getattr(service.extractor, "_renderer", None)
        proxy_requests = renderer.proxy_requests if renderer is not None else 0
    finally:
        await service.close()
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    passages = [str(p.get("x", "")) for p in out.get("ps") or []]
    return {
        "elapsed_ms": elapsed_ms,
        "extract_status": out.get("status"),
        "warnings": out.get("warn") or [],
        "browser_rendered": "browser_rendered" in (out.get("warn") or []),
        "passages": len(passages),
        "tokens": out.get("tok"),
        "contains_rendered_text": any("Rendered by JavaScript" in p for p in passages),
        "proxy_requests": proxy_requests,
    }


async def _https_check(cache_dir: Path) -> dict[str, Any]:
    """Render a public HTTPS page through the proxy, exercising CONNECT + TLS."""
    renderer = BrowserRenderer(
        Settings(
            cache_dir=cache_dir,
            cache_enabled=False,
            allow_private_networks=False,
            allow_browser=True,
            browser_timeout_s=30,
            total_timeout_s=40,
        )
    )
    started = time.perf_counter()
    try:
        html, final = await renderer.render("https://example.com/")
        proxy_requests = renderer.proxy_requests
    except Exception as e:  # noqa: BLE001 - smoke harness reports failures
        return {
            "status": "error",
            "reason": f"{type(e).__name__}: {e}",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    finally:
        await renderer.close()
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return {
        "status": "ok" if "Example Domain" in html and proxy_requests > 0 else "error",
        "elapsed_ms": elapsed_ms,
        "final_url": final,
        "contains_example_domain": "Example Domain" in html,
        "proxy_requests": proxy_requests,
    }


async def measure(cache_dir: Path, runs: int, https_check: bool) -> dict[str, Any]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    try:
        results = [await _local_run(cache_dir, url) for _ in range(max(1, runs))]
        blocked = WebLens(
            Settings(
                cache_dir=cache_dir,
                cache_enabled=False,
                allow_private_networks=False,
                allow_browser=True,
                browser_timeout_s=20,
                total_timeout_s=30,
            )
        )
        try:
            blocked_out = await blocked.extract(url, query="browser", max_tokens=800)
        finally:
            await blocked.close()
    finally:
        server.shutdown()
        server.server_close()

    elapsed = [float(r["elapsed_ms"]) for r in results]
    all_ok = all(
        r.get("extract_status") == "ok" and r.get("contains_rendered_text") and r.get("proxy_requests", 0) > 0
        for r in results
    )
    result: dict[str, Any] = {
        "measured_at": datetime.now(UTC).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "playwright": importlib.metadata.version("playwright"),
        },
        "method": {
            "url": "local HTTP server on 127.0.0.1 (ephemeral port)",
            "page": 'HTML shell with <div id="app"> and an inline script',
            "cache": "disabled",
            "runs": len(results),
            "note": (
                "Each run uses a fresh WebLens instance, so every elapsed_ms includes Chromium launch and navigation."
            ),
        },
        "status": "ok" if all_ok else "error",
        "elapsed_ms": round(statistics.median(elapsed), 1),
        "elapsed_ms_min": min(elapsed),
        "elapsed_ms_max": max(elapsed),
        "runs": results,
        "extract_status": results[0].get("extract_status"),
        "warnings": sorted({str(w) for r in results for w in r.get("warnings") or []}),
        "browser_rendered": all(bool(r.get("browser_rendered")) for r in results),
        "passages": results[0].get("passages"),
        "tokens": results[0].get("tokens"),
        "contains_rendered_text": all(bool(r.get("contains_rendered_text")) for r in results),
        "proxy_requests": [r.get("proxy_requests") for r in results],
        "private_url": {
            "status": blocked_out.get("status"),
            "err": blocked_out.get("err"),
            "msg": blocked_out.get("msg"),
        },
    }
    if not all_ok:
        result["reason"] = "at least one local browser run failed its checks"
    if https_check:
        result["https_check"] = await _https_check(cache_dir)
        if result["https_check"].get("status") != "ok":
            result["status"] = "error"
            result["reason"] = "the public HTTPS proxy check failed"
    return result


def markdown(result: dict[str, Any]) -> str:
    lines = [
        "# WebLens browser smoke test",
        "",
        f"- measured: {result.get('measured_at')}",
        f"- status: **{result.get('status')}**",
    ]
    if result.get("reason"):
        lines.append(f"- reason: {result['reason']}")
    if "environment" not in result:
        return "\n".join([*lines, ""])

    lines.extend(
        [
            f"- python: {result['environment']['python']}",
            f"- platform: {result['environment']['platform']}",
            f"- playwright: {result['environment']['playwright']}",
            f"- method: {result['method']['page']}",
            "",
        ]
    )
    if result.get("runs"):
        lines.extend(
            [
                "| run | elapsed ms | status | browser_rendered | passages | tokens | proxy requests | rendered text |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for index, run in enumerate(result["runs"], 1):
            lines.append(
                f"| {index} | {run['elapsed_ms']} | {run['extract_status']} | "
                f"{run['browser_rendered']} | {run['passages']} | {run['tokens']} | "
                f"{run['proxy_requests']} | {run['contains_rendered_text']} |"
            )
        lines.extend(
            [
                "",
                "| metric | value |",
                "| --- | --- |",
                f"| runs | {result['method']['runs']} |",
                f"| median first extract including launch | {result['elapsed_ms']} ms |",
                f"| min / max | {result['elapsed_ms_min']} / {result['elapsed_ms_max']} ms |",
                f"| warnings | {result['warnings']} |",
                f"| same URL under default policy | {result['private_url']['status']} "
                f"({result['private_url']['err']}) |",
            ]
        )
    if result.get("https_check"):
        https = result["https_check"]
        lines.extend(
            [
                "",
                "Public HTTPS proxy check:",
                "",
                "| metric | value |",
                "| --- | --- |",
                f"| status | {https.get('status')} |",
                f"| elapsed ms | {https.get('elapsed_ms')} |",
                f"| final URL | {https.get('final_url')} |",
                f"| proxy requests | {https.get('proxy_requests')} |",
                f"| Example Domain found | {https.get('contains_example_domain')} |",
            ]
        )
    lines.extend(
        [
            "",
            "The private-URL check uses the default policy and is expected to fail",
            "before the browser can navigate. The browser is launched behind a local",
            "egress proxy that resolves and validates each destination once; see",
            "`docs/THREAT_MODEL.md` for the remaining limits.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="benchmarks/results/browser_smoke.json")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--https-check", action="store_true")
    args = parser.parse_args()
    out_path = Path(args.out)
    cache_dir = Path("benchmarks/.cache_browser_smoke")
    try:
        import playwright  # noqa: F401
    except ImportError:
        result: dict[str, Any] = {
            "measured_at": datetime.now(UTC).isoformat(),
            "status": "skipped",
            "reason": "playwright is not installed; run: uv sync --extra browser",
        }
    else:
        try:
            result = asyncio.run(measure(cache_dir, args.runs, args.https_check))
        except Exception as e:  # noqa: BLE001 - smoke harness reports failures
            result = {
                "measured_at": datetime.now(UTC).isoformat(),
                "status": "error",
                "reason": f"{type(e).__name__}: {e}",
            }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    out_path.with_suffix(".md").write_text(markdown(result), encoding="utf-8")
    print(out_path)
    print(markdown(result))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
