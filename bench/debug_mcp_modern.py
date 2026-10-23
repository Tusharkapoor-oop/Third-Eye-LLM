import asyncio
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from weblens.tokens import count_tokens


async def run(mode: str) -> None:
    params = StdioServerParameters(
        command="uv",
        args=["run", "weblens", "serve"],
        cwd=r"C:\Users\ACER\Downloads\Broswer for ai agnets",
    )
    async with Client(params, mode=mode) as client:
        print("MODE", mode, "PROTOCOL", client.protocol_version)
        tools = await client.list_tools()
        dumped = [
            t.model_dump(by_alias=True, exclude_none=True) for t in tools.tools
        ]
        print(
            "TOOLS",
            [t.name for t in tools.tools],
            "schema_tokens",
            count_tokens(json.dumps(dumped, separators=(",", ":"), ensure_ascii=False)),
        )
        res = await client.call_tool(
            "web_search", {"query": "python asyncio timeout", "max_results": 1}
        )
        print("SEARCH isError", res.is_error)
        for c in res.content:
            text = getattr(c, "text", None)
            if text:
                print(text[:400])


async def main() -> None:
    for mode in ("legacy", "auto", "2026-07-28"):
        try:
            await run(mode)
        except Exception as e:
            print("MODE", mode, "FAILED", type(e).__name__, str(e)[:300])


asyncio.run(main())
