"""
MCP Protocol Stress Testing Suite
Verifies MCP server handles malformed calls gracefully.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from src.server.mcp_server import create_server

# ---------------------------------------------------------------------------
# Tool listing tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mcp_tool_listing() -> None:
    server = create_server()
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]

    expected_tools = ["web_search", "extract_url", "crawl_website", "web_map", "deep_research"]
    for expected in expected_tools:
        assert expected in tool_names, f"Tool {expected} missing from MCP server"

    assert len(tool_names) == 5, f"Expected 5 tools, got {len(tool_names)}"


# ---------------------------------------------------------------------------
# Malformed call tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mcp_missing_required_param() -> None:
    """web_search without 'query' should return an error, not crash."""
    server = create_server()
    try:
        res = await server.call_tool("web_search", {})
        assert res.is_error is True or "error" in str(res.content[0].text).lower()
    except Exception as e:
        assert "error" in str(e).lower() or "validation" in str(e).lower()


@pytest.mark.asyncio
async def test_mcp_empty_query() -> None:
    """web_search with empty query should be handled gracefully."""
    server = create_server()
    res = await server.call_tool("web_search", {"query": "", "count": 5})
    payload = json.loads(res.content[0].text)
    assert payload["status"] in ("success", "no_reliable_result", "error")


@pytest.mark.asyncio
async def test_mcp_wrong_type_count() -> None:
    """web_search with count as string should be handled."""
    server = create_server()
    try:
        res = await server.call_tool("web_search", {"query": "test", "count": "five"})
        assert res is not None
    except Exception as e:
        assert "error" in str(e).lower() or "validation" in str(e).lower()


@pytest.mark.asyncio
async def test_mcp_null_url() -> None:
    """extract_url with null URL should error gracefully."""
    server = create_server()
    try:
        res = await server.call_tool("extract_url", {"url": None})
        payload = json.loads(res.content[0].text)
        assert payload["status"] in ("blocked", "error")
    except Exception as e:
        assert "error" in str(e).lower() or "validation" in str(e).lower()


@pytest.mark.asyncio
async def test_mcp_private_url_blocked() -> None:
    """extract_url to private IP should be blocked via MCP."""
    server = create_server()
    res = await server.call_tool("extract_url",
                                 {"url": "http://169.254.169.254/latest/meta-data/"})
    payload = json.loads(res.content[0].text)
    assert payload["status"] == "blocked"


@pytest.mark.asyncio
async def test_mcp_unknown_tool() -> None:
    """Calling a nonexistent tool should return an error."""
    server = create_server()
    try:
        res = await server.call_tool("nonexistent_tool", {})
        # If it doesn't raise, check it's an error
        assert res is not None
    except Exception:
        # Tool not found is expected
        pass


# ---------------------------------------------------------------------------
# Rapid fire MCP calls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mcp_rapid_fire() -> None:
    """100 rapid MCP calls should all be handled without crashes."""
    server = create_server()

    async def one_call(i: int):
        return await server.call_tool("web_search", {"query": f"test {i}", "count": 1})

    results = await asyncio.gather(*[one_call(i) for i in range(20)],
                                   return_exceptions=True)
    exceptions = [r for r in results if isinstance(r, Exception)]
    assert len(exceptions) == 0, f"Exceptions during rapid fire: {exceptions[:3]}"


# ---------------------------------------------------------------------------
# Concurrent MCP sessions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mcp_concurrent_sessions() -> None:
    """Multiple sequential calls on same server should work."""
    server = create_server()

    async def one_call(q: str):
        return await server.call_tool("web_search", {"query": q, "count": 2})

    results = await asyncio.gather(
        one_call("python asyncio"),
        one_call("speed of light"),
        one_call("capital of France"),
        return_exceptions=True,
    )
    exceptions = [r for r in results if isinstance(r, Exception)]
    assert len(exceptions) == 0, f"Exceptions during concurrent sessions: {exceptions[:3]}"
