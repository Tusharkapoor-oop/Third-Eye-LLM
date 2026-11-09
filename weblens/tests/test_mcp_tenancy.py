from __future__ import annotations

import json
import sqlite3

import httpx
from httpx import ASGITransport
from mcp.server import MCPServer

from weblens.cli import _ApiKeyAuth
from weblens.config import Settings
from weblens.mcp_server import build_server
from weblens.tenancy import ApiKeyRegistry, current_tenant


def _sse_payload(text: str) -> dict:
    for line in text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    raise AssertionError(f"no SSE data line in {text[:200]!r}")


class FakeService:
    def __init__(self, settings: Settings):
        self.s = settings


def _insert_passage(db_path, text: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO kb_passages(url, title, passage_index, span_start, span_end, text) VALUES (?, ?, ?, ?, ?, ?)",
            ("https://tenant.example/doc", "Tenant doc", 0, 0, len(text), text),
        )
        conn.commit()


async def test_stateful_tools_use_per_tenant_database(tmp_path):
    settings = Settings(
        cache_dir=tmp_path,
        cache_enabled=False,
        embedding_enabled=False,
    )
    server = build_server(FakeService(settings), profile="full", allow_stateful=True)

    token = current_tenant.set("acme")
    try:
        first = await server.call_tool("crawl2rag_query", {"question": "widget", "top_k": 3})
    finally:
        current_tenant.reset(token)
    assert first.is_error is False
    acme_db = tmp_path / "tenants" / "acme" / "crawl2rag.db"
    assert acme_db.exists()

    _insert_passage(acme_db, "acme secret widget")

    token = current_tenant.set("acme")
    try:
        acme = await server.call_tool("crawl2rag_query", {"question": "widget", "top_k": 3})
    finally:
        current_tenant.reset(token)
    assert "acme secret widget" in acme.content[0].text

    token = current_tenant.set("beta")
    try:
        beta = await server.call_tool("crawl2rag_query", {"question": "widget", "top_k": 3})
    finally:
        current_tenant.reset(token)
    assert "acme secret widget" not in beta.content[0].text
    assert (tmp_path / "tenants" / "beta" / "crawl2rag.db").exists()

    default = await server.call_tool("crawl2rag_query", {"question": "widget", "top_k": 3})
    assert "acme secret widget" not in default.content[0].text
    assert (tmp_path / "crawl2rag.db").exists()


async def test_http_api_key_tenant_reaches_mcp_tool():
    server = MCPServer(name="tenant-context-test")
    seen: list[str] = []

    @server.tool(
        name="whoami",
        description="Return the authenticated tenant.",
        structured_output=False,
    )
    async def whoami() -> str:
        tenant = current_tenant.get()
        seen.append(tenant)
        return tenant

    app = server.streamable_http_app(stateless_http=True)
    auth_app = _ApiKeyAuth(app, ApiKeyRegistry({"acme": "12345678", "beta": "abcdefgh"}))
    headers = {"accept": "application/json, text/event-stream"}
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://127.0.0.1:8765") as client,
    ):
        for key, expected in (("12345678", "acme"), ("abcdefgh", "beta")):
            r = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "whoami", "arguments": {}},
                },
                headers={**headers, "authorization": f"Bearer {key}"},
            )
            assert r.status_code == 200
            payload = _sse_payload(r.text)
            assert payload["result"]["content"][0]["text"] == expected
    assert seen == ["acme", "beta"]
    assert current_tenant.get() == "default"
