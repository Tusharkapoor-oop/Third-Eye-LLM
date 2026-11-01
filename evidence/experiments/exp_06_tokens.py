"""EXP-06: measure the advertised MCP tool schema with the real server object.

If the installed MCP API cannot enumerate tools in-process, the metric is recorded
as NOT RUN rather than estimated from source code.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from _common import emit

from weblens.config import Settings
from weblens.mcp_server import build_server
from weblens.service import WebLens
from weblens.tokens import TOKENIZER_NAME, count_json_tokens


def tool_dict(tool) -> dict:
    if isinstance(tool, dict):
        return tool
    for attr in ("inputSchema", "input_schema", "schema"):
        if hasattr(tool, attr):
            return {
                "name": getattr(tool, "name", "?"),
                "description": getattr(tool, "description", ""),
                "inputSchema": getattr(tool, attr),
            }
    return {"name": getattr(tool, "name", "?"), "description": getattr(tool, "description", ""), "inputSchema": {}}


async def discover(server) -> tuple[list[dict], str]:
    for attr in ("list_tools", "get_tools"):
        fn = getattr(server, attr, None)
        if callable(fn):
            result = fn()
            if asyncio.iscoroutine(result):
                result = await result
            return [tool_dict(t) for t in result], f"server.{attr}()"
    for path in ("_tool_manager", "_mcp_server"):
        holder = getattr(server, path, None)
        if holder is None:
            continue
        fn = getattr(holder, "list_tools", None)
        if callable(fn):
            result = fn()
            if asyncio.iscoroutine(result):
                result = await result
            return [tool_dict(t) for t in result], f"server.{path}.list_tools()"
    return [], "no in-process tool enumeration API found"


async def main() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(cache_dir=Path(tmp) / "cache", cache_enabled=False, search_providers="ddg")
        svc = object.__new__(WebLens)
        svc.s = settings
        server = build_server(svc)
        tools, source = await discover(server)

    rows = []
    total = 0
    for tool in tools:
        payload = {"name": tool.get("name"), "description": tool.get("description", ""), "inputSchema": tool.get("inputSchema", {})}
        tokens = count_json_tokens(payload)
        total += tokens
        rows.append({"tool": tool.get("name", "?"), "schema_tokens": tokens})
    return {"rows": rows, "total": total, "source": source, "count": len(tools)}


result = asyncio.run(main())
total = result["total"]
emit(
    {
        "experiment": "EXP-06",
        "kind": "mcp-schema-tokens",
        "class": "REAL" if result["count"] else "MOCK",
        "rows": result["rows"],
        "summary": {
            "tools": result["count"],
            "schema_tokens_total": total,
            "tokenizer": TOKENIZER_NAME,
            "source": result["source"],
            "status": "measured" if result["count"] else "not_run",
        },
        "limitations": [
            "Competitor MCP schema sizes were NOT measured; no competitor schema claim is made.",
            "Schema tokens are tokenizer-dependent and comparable only within this tokenizer.",
        ],
    }
)
