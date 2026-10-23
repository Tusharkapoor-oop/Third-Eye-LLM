import asyncio
import inspect

from mcp.server import MCPServer

print(inspect.signature(MCPServer.list_tools))
print(inspect.getsource(MCPServer.list_tools)[:2000])

s = MCPServer(name="t", version="1")


@s.tool(name="x", description="d", structured_output=False)
async def x(a: int = 1) -> str:
    return "ok"


async def main():
    try:
        tools = await s.list_tools()
        print("list_tools ->", tools)
    except Exception as e:
        print("list_tools ERR", type(e).__name__, e)
    print("tool_manager", type(s._tool_manager), [m for m in dir(s._tool_manager) if not m.startswith("_")])


asyncio.run(main())
