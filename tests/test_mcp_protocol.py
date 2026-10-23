import json

import pytest

from src.server.mcp_server import create_server


@pytest.mark.asyncio
async def test_mcp_tool_listing():
    server = create_server()
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]

    expected_tools = ["web_search", "extract_url", "crawl_website", "web_map", "deep_research"]
    for expected in expected_tools:
        assert expected in tool_names, f"Tool {expected} missing from MCP server"

@pytest.mark.asyncio
async def test_mcp_call_web_search():
    server = create_server()
    res = await server.call_tool("web_search", {"query": "python asyncio", "count": 2})
    assert res.is_error is False
    assert len(res.content) > 0
    # Parse returned text JSON
    payload = json.loads(res.content[0].text)
    assert payload["status"] in ("success", "no_reliable_result")
    assert "results" in payload
    # Check structured_content field
    assert res.structured_content is not None
    assert res.structured_content["status"] == payload["status"]

@pytest.mark.asyncio
async def test_mcp_call_extract_url():
    server = create_server()
    res = await server.call_tool("extract_url", {"url": "https://www.python.org/about/", "max_tokens": 500})
    assert res.is_error is False
    payload = json.loads(res.content[0].text)
    assert payload["status"] == "success"
    assert "passages" in payload
    assert len(payload["passages"]) > 0

@pytest.mark.asyncio
async def test_mcp_call_web_map():
    server = create_server()
    res = await server.call_tool("web_map", {"url": "https://www.python.org", "limit": 5})
    assert res.is_error is False
    payload = json.loads(res.content[0].text)
    assert "urls" in payload
    assert payload["total_discovered"] <= 5
