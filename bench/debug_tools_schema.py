import asyncio
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from weblens.config import Settings
from weblens.mcp_server import build_server
from weblens.service import WebLens
from weblens.tokens import count_json_tokens, count_tokens


async def main() -> None:
    s = Settings()
    s.cache_enabled = False
    service = WebLens(s)
    server = build_server(service)
    tools = await server.list_tools()
    total = 0
    for t in tools:
        dumped = t.model_dump(by_alias=True, exclude_none=True)
        text = json.dumps(dumped, separators=(",", ":"), ensure_ascii=False)
        n = count_tokens(text)
        total += n
        print(t.name, n, "tokens")
        print(text)
    print("TOTAL", total)
    await service.close()


asyncio.run(main())
