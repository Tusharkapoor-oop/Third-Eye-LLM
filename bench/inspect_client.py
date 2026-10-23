import inspect

from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession

print("stdio_client", inspect.signature(stdio_client))
print("ClientSession", inspect.signature(ClientSession))
for name in ["initialize", "list_tools", "call_tool"]:
    fn = getattr(ClientSession, name, None)
    if fn:
        print(name, inspect.signature(fn))
