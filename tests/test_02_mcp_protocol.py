"""Layer 2: MCP Protocol Conformance & Token Tax Audit.

Verifies:
- In-memory MCP Client connection and clean registration of all 5 tools.
- Flat deterministic JSON schema without confusing anyOf/oneOf discriminators.
- MCP Token Tax Gate: combined tool schema token length strictly < 800 tokens.
- Stdout Contamination Gate: zero non-JSON-RPC stdout leaks on stdio transport.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

import pytest
import tiktoken
from mcp import Client

from server import mcp

EXPECTED_TOOLS = ["web_search", "extract_url", "web_map", "crawl_website", "deep_research"]


@pytest.mark.asyncio
async def test_mcp_tools_registration_and_naming():
    """Verify all 5 tools register with valid names matching ^[a-z0-9_]+$ and no prefix."""
    async with Client(mcp) as client:
        res = await client.list_tools()
        registered_names = [t.name for t in res.tools]

        for expected in EXPECTED_TOOLS:
            assert expected in registered_names, f"Missing tool: {expected}"

        for name in registered_names:
            assert re.match(r"^[a-z0-9_]+$", name), f"Invalid tool name format: {name}"
            assert not name.startswith("mywebengine_"), f"Redundant prefix in tool name: {name}"
            assert not name.startswith("weblens_"), f"Redundant prefix in tool name: {name}"


@pytest.mark.asyncio
async def test_mcp_tools_flat_schemas():
    """Verify tool input schemas use flat types without confusing anyOf/oneOf discriminators."""
    async with Client(mcp) as client:
        res = await client.list_tools()
        for tool in res.tools:
            schema_json = json.dumps(tool.input_schema)
            assert "anyOf" not in schema_json, f"Tool '{tool.name}' contains ambiguous anyOf discriminator"
            assert "oneOf" not in schema_json, f"Tool '{tool.name}' contains ambiguous oneOf discriminator"


@pytest.mark.asyncio
async def test_mcp_token_tax_gate():
    """Verify serialized JSON tool schemas are strictly under the 800-token budget."""
    async with Client(mcp) as client:
        res = await client.list_tools()
        tools_dict = [
            {"name": t.name, "description": t.description, "inputSchema": t.input_schema}
            for t in res.tools
        ]
        schema_json = json.dumps(tools_dict)
        enc = tiktoken.get_encoding("cl100k_base")
        token_count = len(enc.encode(schema_json))

        assert token_count < 800, (
            f"MCP schema token tax exceeded: {token_count} tokens (target < 800 tokens)"
        )


def test_stdio_stdout_contamination_gate():
    """Verify that starting server over stdio emits zero stray prints to stdout."""
    # Spawn server with a short stdin timeout to verify zero stdout garbage
    proc = subprocess.Popen(
        [sys.executable, "server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    init_request = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        }
    }) + "\n"

    try:
        stdout_data, stderr_data = proc.communicate(input=init_request, timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout_data, stderr_data = proc.communicate()

    # Every non-empty line on stdout must be valid JSON-RPC
    lines = [line.strip() for line in stdout_data.splitlines() if line.strip()]
    for line in lines:
        try:
            parsed = json.loads(line)
            assert "jsonrpc" in parsed or "id" in parsed or "result" in parsed, (
                f"Non-JSON-RPC output on stdout: {line}"
            )
        except json.JSONDecodeError:
            pytest.fail(f"Stray print contamination on stdout: {line}")
