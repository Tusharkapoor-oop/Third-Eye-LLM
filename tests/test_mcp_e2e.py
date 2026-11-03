"""MCP protocol conformance-lite: boot the real server via stdio with the official
SDK client; validate tools/list schemas and (optionally) one live search call.
"""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LIVE_NET = os.environ.get("WEBINTEL_LIVE_TESTS", "1").lower() in ("1", "true", "yes")
# Set WEBINTEL_LIVE_TESTS=0 to disable network-dependent assertions (offline CI).


async def _client():
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    params = StdioServerParameters(command=sys.executable, args=["-m", "webintel"],
                                   cwd=str(ROOT))
    cm = stdio_client(params)
    read, write = await cm.__aenter__()
    session = ClientSession(read, write)
    await session.__aenter__()
    await session.initialize()
    return cm, session


@pytest.mark.asyncio
@pytest.mark.skipif(not LIVE_NET, reason="needs child process boot (may sandbox net OK)")
async def test_tools_list_and_schema_budget():
    cm, session = await _client()
    try:
        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        assert names == {"web_search", "extract_url", "web_map", "crawl_website", "deep_research"}
        # precise schema+description token overhead (R1 measurement)
        from webintel.limits import count_tokens
        total = 0
        for t in tools.tools:
            total += count_tokens(json.dumps(t.input_schema, separators=(",", ":")))
            total += count_tokens(t.description or "")
        assert total < 1000, f"tool surface too big: {total} tokens (R1 budget 1000)"
    finally:
        await session.__aexit__(None, None, None)
        await cm.__aexit__(None, None, None)


@pytest.mark.asyncio
@pytest.mark.skipif(not LIVE_NET, reason="needs network")
async def test_live_web_search_payload_contract():
    cm, session = await _client()
    try:
        r = await session.call_tool("web_search",
                                    {"query": "python pathlib read_text documentation",
                                     "max_tokens": 500})
        d = json.loads(r.content[0].text)
        assert d["status"] in ("ok", "no_reliable_result")
        assert "q" in d and "r" in d
        for h in d.get("r", [])[:3]:
            assert h["u"].startswith("http")
            # every result must be verifiable: url + title + snippet present
            assert h["t"] is not None and h["s"] is not None
        # R2 invariant: no uncalibrated numbers anywhere
        raw = r.content[0].text
        for forbidden in ('"score":', '"confidence":', '"relevance":', '"similarity":'):
            assert forbidden not in raw
    finally:
        await session.__aexit__(None, None, None)
        await cm.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_extract_url_rejects_private_without_net():
    """SSRF guard through the MCP tool path with the default config."""
    cm, session = await _client()
    try:
        r = await session.call_tool(
            "extract_url", {"url": "http://169.254.169.254/latest/meta-data/"})
        d = json.loads(r.content[0].text)
        assert d["status"] == "blocked", d
    finally:
        await session.__aexit__(None, None, None)
        await cm.__aexit__(None, None, None)
