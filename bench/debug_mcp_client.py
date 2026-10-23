import asyncio
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from weblens.tokens import count_tokens


async def main() -> None:
    params = StdioServerParameters(
        command="uv",
        args=["run", "weblens", "serve"],
        cwd=r"C:\Users\ACER\Downloads\Broswer for ai agnets",
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print("SERVER", init.server_info.name, init.server_info.version)
            print("PROTOCOL", init.protocol_version)
            tools = await session.list_tools()
            dumped = [
                t.model_dump(by_alias=True, exclude_none=True) for t in tools.tools
            ]
            print(
                "TOOLS",
                [t.name for t in tools.tools],
                "schema_tokens",
                count_tokens(json.dumps(dumped, separators=(",", ":"), ensure_ascii=False)),
            )
            res = await session.call_tool(
                "web_search",
                {"query": "python asyncio timeout", "max_results": 2},
            )
            print("SEARCH isError", res.is_error)
            for c in res.content:
                text = getattr(c, "text", None)
                if text:
                    print(text)
            res2 = await session.call_tool(
                "extract_url",
                {
                    "url": "https://docs.python.org/3/library/asyncio-task.html",
                    "query": "asyncio timeout",
                    "max_tokens": 400,
                },
            )
            print("EXTRACT isError", res2.is_error)
            for c in res2.content:
                text = getattr(c, "text", None)
                if text:
                    print(text[:700])


asyncio.run(main())
