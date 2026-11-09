from __future__ import annotations

import json
import tempfile
from pathlib import Path

from weblens.config import Settings
from weblens.mcp_server import build_server
from weblens.service import WebLens
from weblens.tokens import count_tokens


class FakeSettings:
    log_level = "INFO"


class FakeService:
    def __init__(self):
        self.s = FakeSettings()
        self.calls: list[tuple[str, dict]] = []

    async def search(self, query, **kwargs):
        self.calls.append(("search", {"query": query, **kwargs}))
        return {"status": "ok", "q": query, "n": 1, "res": [{"t": "T", "u": "https://e.com", "s": "S"}], "tok": 20}

    async def extract(self, url, **kwargs):
        self.calls.append(("extract", {"url": url, **kwargs}))
        return {"status": "ok", "u": url, "tok": 20}

    async def crawl_site(self, url, **kwargs):
        self.calls.append(("crawl", {"url": url, **kwargs}))
        return {"status": "ok", "u": url, "mode": kwargs.get("mode"), "tok": 20}

    async def deep_research(self, query, **kwargs):
        self.calls.append(("research", {"query": query, **kwargs}))
        return {"status": "ok", "q": query, "n": 0, "f": [], "tok": 20}

    async def synthesize(self, query, **kwargs):
        self.calls.append(("synthesize", {"query": query, **kwargs}))
        return {"status": "ok", "q": query, "hyp": [], "tok": 20}


async def test_tool_surface_is_four_compact_readonly_tools():
    server = build_server(FakeService())
    tools = await server.list_tools()
    assert [t.name for t in tools] == ["web_search", "extract_url", "crawl_site", "deep_research"]
    for t in tools:
        assert t.annotations is not None
        assert t.annotations.read_only_hint is True
        assert t.annotations.destructive_hint is False
        assert t.output_schema is None
        assert t.input_schema["type"] == "object"


async def test_tool_schema_stays_within_budget():
    server = build_server(FakeService())
    tools = await server.list_tools()
    dumped = [t.model_dump(by_alias=True, exclude_none=True) for t in tools]
    tokens = count_tokens(json.dumps(dumped, separators=(",", ":"), ensure_ascii=False))
    assert tokens <= 1000, tokens


async def test_research_profile_exposes_evidence_synthesis_and_forwards_arguments():
    svc = FakeService()
    server = build_server(svc, profile="research")
    tools = await server.list_tools()
    assert "evidence_synthesis" in [t.name for t in tools]

    result = await server.call_tool(
        "evidence_synthesis",
        {"query": "does X cause Y", "max_tokens": 500, "max_hops": 3},
    )
    assert result.is_error is False
    call = svc.calls[-1]
    assert call[0] == "synthesize"
    assert call[1]["query"] == "does X cause Y"
    assert call[1]["max_tokens"] == 500
    assert call[1]["max_hops"] == 3


async def test_full_profile_tool_annotations_match_mutability():
    """Read-only tools stay read-only; stateful tools are marked mutating."""
    cache_dir = Path(tempfile.mkdtemp())
    service = WebLens(Settings(cache_dir=cache_dir, cache_enabled=False, search_providers="ddg", allow_browser=False))
    try:
        server = build_server(service, profile="full")
        tools = await server.list_tools()
        by_name = {t.name: t.annotations for t in tools}

        for name in (
            "web_search",
            "extract_url",
            "crawl_site",
            "deep_research",
            "evidence_synthesis",
            "company_research",
            "market_research",
            "crawl2rag_query",
            "tutorial_101",
        ):
            assert by_name[name].read_only_hint is True, f"{name} should be read-only"
            assert by_name[name].destructive_hint is False, f"{name} should not claim destructive"

        for name in ("crawl2rag_index", "research_chat"):
            assert by_name[name].read_only_hint is False, f"{name} must not claim read-only"
            assert by_name[name].destructive_hint is False
    finally:
        await service.close()


async def test_web_search_forwards_arguments_and_returns_compact_json():
    svc = FakeService()
    server = build_server(svc)
    result = await server.call_tool(
        "web_search",
        {
            "query": "python asyncio",
            "max_results": 3,
            "freshness": "month",
            "domains": ["docs.python.org"],
            "max_tokens": 250,
        },
    )
    assert result.is_error is False
    text = result.content[0].text
    assert json.loads(text)["status"] == "ok"
    assert "\n" not in text
    call = svc.calls[-1]
    assert call[0] == "search"
    assert call[1]["max_results"] == 3
    assert call[1]["freshness"] == "month"
    assert call[1]["domains"] == ["docs.python.org"]
    assert call[1]["max_tokens"] == 250


async def test_extract_and_crawl_and_research_forward_arguments():
    svc = FakeService()
    server = build_server(svc)
    r1 = await server.call_tool(
        "extract_url", {"url": "https://e.com/a", "query": "q", "max_tokens": 300, "full": True}
    )
    assert r1.is_error is False
    assert svc.calls[-1][0] == "extract"
    assert svc.calls[-1][1]["full"] is True

    r2 = await server.call_tool(
        "crawl_site",
        {"url": "https://e.com", "mode": "crawl", "max_pages": 4, "max_depth": 1, "query": "q"},
    )
    assert r2.is_error is False
    assert svc.calls[-1][0] == "crawl"
    assert svc.calls[-1][1]["mode"] == "crawl"
    assert svc.calls[-1][1]["max_depth"] == 1

    r3 = await server.call_tool("deep_research", {"query": "q", "max_tokens": 500})
    assert r3.is_error is False
    assert svc.calls[-1][0] == "research"
    assert svc.calls[-1][1]["max_tokens"] == 500


async def test_invalid_tool_arguments_are_rejected_before_the_service():
    import pytest
    from mcp.server.mcpserver.exceptions import ToolError

    svc = FakeService()
    server = build_server(svc)
    with pytest.raises(ToolError):
        await server.call_tool("crawl_site", {"url": "https://e.com", "mode": "bad"})
    assert not svc.calls


async def test_service_error_payload_is_an_mcp_error():
    import pytest
    from mcp.server.mcpserver.exceptions import ToolError

    class ErrorService(FakeService):
        async def search(self, query, **kwargs):
            return {"status": "error", "err": "bad_input", "msg": "query must not be empty"}

    server = build_server(ErrorService())
    with pytest.raises(ToolError) as err:
        await server.call_tool("web_search", {"query": ""})
    assert '"status":"error"' in str(err.value)
    assert '"err":"bad_input"' in str(err.value)


def _sse_payload(text: str) -> dict:
    for line in text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    raise AssertionError(f"no SSE data line in {text[:200]!r}")


async def test_stateless_http_accepts_modern_and_legacy_requests(tmp_path):
    import httpx
    from httpx import ASGITransport

    server = build_server(FakeService())
    app = server.streamable_http_app(stateless_http=True)
    headers = {"accept": "application/json, text/event-stream"}
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client,
    ):
        modern = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {
                "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"},
            },
        }
        r = await client.post("/mcp", json=modern, headers=headers)
        assert r.status_code == 200
        assert not r.headers.get("mcp-session-id")
        payload = _sse_payload(r.text)
        assert [t["name"] for t in payload["result"]["tools"]] == [
            "web_search",
            "extract_url",
            "crawl_site",
            "deep_research",
        ]

        init = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        }
        r = await client.post("/mcp", json=init, headers=headers)
        assert r.status_code == 200
        payload = _sse_payload(r.text)
        assert payload["result"]["protocolVersion"] == "2025-11-25"
        caps = payload["result"]["capabilities"]
        assert "tools" in caps
        # The SDK exposes empty prompt/resource collections; no items are
        # populated, and no logging/completion capability is advertised.
        assert caps["prompts"] == {"listChanged": False}
        assert caps["resources"] == {"subscribe": False, "listChanged": False}
        for absent in ("logging", "completions"):
            assert absent not in caps

        legacy_list = {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}
        r = await client.post("/mcp", json=legacy_list, headers=headers)
        assert r.status_code == 200
        assert len(_sse_payload(r.text)["result"]["tools"]) == 4
