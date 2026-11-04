"""One-off probe: print raw MCP responses for ambiguous deployed checks.

Not part of the audit suite. Run manually:
    python weblens-lab/security_lab/probe_deployed_raw.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "weblens-lab"))

ENDPOINT = "https://weblens-16131012091.us-central1.run.app/mcp"
INIT = {
    "jsonrpc": "2.0",
    "id": "probe-init",
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "probe", "version": "1"},
    },
}


async def main() -> None:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as c:
        r = await c.post(ENDPOINT, json=INIT, headers={"Accept": "application/json, text/event-stream"})
        print("INIT", r.status_code, r.headers.get("mcp-session-id"), r.text[:500])
        sid = r.headers.get("mcp-session-id")
        headers = {"Accept": "application/json, text/event-stream"}
        if sid:
            headers["Mcp-Session-Id"] = sid

        async def call(name, args):
            payload = {
                "jsonrpc": "2.0",
                "id": f"probe-{name}",
                "method": "tools/call",
                "params": {"name": name, "arguments": args},
            }
            resp = await c.post(ENDPOINT, json=payload, headers=headers)
            print(f"\n== {name} {args} -> {resp.status_code}")
            print(resp.text[:1500])

        await call("extract_url", {"url": "http://169.254.169.254/latest/meta-data/"})
        await call("extract_url", {"url": "https://example.com/", "max_tokens": 300})
        await call("does_not_exist", {})
        await call("web_search", {})

        root = await c.get(ENDPOINT.replace("/mcp", "/"))
        print("\nROOT GET", root.status_code, root.text[:300])
        print("HSTS", root.headers.get("strict-transport-security"))


asyncio.run(main())
