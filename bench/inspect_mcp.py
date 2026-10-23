import inspect

from mcp.server import MCPServer

print([m for m in dir(MCPServer) if not m.startswith("_")])
for name in ["run", "run_stdio_async", "run_streamable_http_async", "streamable_http_app", "sse_app"]:
    fn = getattr(MCPServer, name, None)
    if fn:
        try:
            print(name, inspect.signature(fn))
        except Exception as e:
            print(name, e)
print(inspect.signature(MCPServer.__init__))
