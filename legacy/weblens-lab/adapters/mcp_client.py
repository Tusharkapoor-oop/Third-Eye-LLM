"""Minimal, instrumented MCP Streamable-HTTP client used by the evaluation lab.

This is deliberately independent of the high-level MCP SDK so that every
JSON-RPC exchange (initialize, tools/list, tools/call) is visible and can be
measured. It implements the transport subset the WebLens server exposes:

* POST JSON-RPC to a single /mcp endpoint
* Accept both ``application/json`` and ``text/event-stream`` responses
* Send notifications/initialized after initialize
* Reuse ``Mcp-Session-Id`` when the server issues one
* Retry only idempotent, transport-level failures (429/502/503/504)

No credentials are logged. Authorization headers are redacted from metadata.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


class MCPTransportError(RuntimeError):
    """Transport or protocol failure (not a tool-level error)."""


class MCPAuthError(MCPTransportError):
    """The endpoint rejected the supplied credentials."""


@dataclass
class CallMeta:
    http_status: int = 0
    response_bytes: int = 0
    attempts: int = 0
    session_id: str | None = None
    retry_after_s: float | None = None
    content_type: str | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolInfo:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


def _parse_sse(text: str, request_id: int | str) -> dict[str, Any] | None:
    """Return the JSON-RPC message matching request_id from an SSE body."""
    for block in text.replace("\r\n", "\n").split("\n\n"):
        data_lines = [ln[5:].strip() for ln in block.split("\n") if ln.startswith("data:")]
        if not data_lines:
            continue
        payload = "\n".join(data_lines)
        try:
            msg = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(msg, dict) and msg.get("id") == request_id:
            return msg
    return None


class MCPHttpClient:
    """Instrumented JSON-RPC client for one MCP endpoint."""

    def __init__(
        self,
        endpoint: str,
        *,
        token: str | None = None,
        timeout_s: float = 45.0,
        max_retries: int = 2,
        client_name: str = "weblens-lab",
        client_version: str = "10.0.0",
    ) -> None:
        self.endpoint = endpoint
        self._token = token
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._client_name = client_name
        self._client_version = client_version
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            follow_redirects=False,
        )
        self._id = 0
        self._session_id: str | None = None
        self.server_info: dict[str, Any] = {}
        self.protocol_version: str | None = None
        self.tools: list[ToolInfo] = []
        self.last_meta = CallMeta()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": f"{self._client_name}/{self._client_version}",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def close(self) -> None:
        await self._client.aclose()

    async def _post(
        self,
        payload: dict[str, Any],
        *,
        expect_response: bool = True,
    ) -> tuple[dict[str, Any] | None, CallMeta]:
        meta = CallMeta()
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 2):
            meta.attempts = attempt
            try:
                resp = await self._client.post(self.endpoint, json=payload, headers=self._headers())
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                meta.error = type(exc).__name__
                if attempt <= self.max_retries:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                raise MCPTransportError(f"transport failure: {type(exc).__name__}") from exc

            meta.http_status = resp.status_code
            meta.response_bytes = len(resp.content)
            meta.content_type = resp.headers.get("content-type")
            session = resp.headers.get("mcp-session-id")
            if session:
                self._session_id = session
                meta.session_id = session
            if resp.status_code in (401, 403):
                raise MCPAuthError(f"authentication rejected (HTTP {resp.status_code})")
            if resp.status_code in (429, 502, 503, 504) and attempt <= self.max_retries:
                retry_after = resp.headers.get("retry-after")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 0.75 * attempt
                meta.retry_after_s = delay
                await asyncio.sleep(min(delay, 5.0))
                continue
            if resp.status_code >= 400:
                meta.error = f"HTTP {resp.status_code}"
                raise MCPTransportError(
                    f"HTTP {resp.status_code}: {resp.text[:300]}"
                )
            if not expect_response:
                return None, meta

            # Prefer SSE when the server streams; fall back to JSON.
            msg: dict[str, Any] | None = None
            if "text/event-stream" in (meta.content_type or ""):
                msg = _parse_sse(resp.text, payload.get("id"))
            if msg is None:
                try:
                    candidate = resp.json()
                except json.JSONDecodeError as exc:
                    raise MCPTransportError(
                        f"non-JSON response: {resp.text[:200]!r}"
                    ) from exc
                # A JSON-RPC batch is not expected from this server, but handle it.
                if isinstance(candidate, list):
                    candidate = next(
                        (m for m in candidate if m.get("id") == payload.get("id")),
                        None,
                    )
                msg = candidate
            if not isinstance(msg, dict):
                raise MCPTransportError("JSON-RPC response missing")
            if "error" in msg:
                meta.error = json.dumps(msg["error"])[:300]
                raise MCPTransportError(f"JSON-RPC error: {meta.error}")
            return msg, meta

        raise MCPTransportError(f"request failed after retries: {last_error}")

    async def initialize(self) -> dict[str, Any]:
        request_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"roots": {"listChanged": False}},
                "clientInfo": {"name": self._client_name, "version": self._client_version},
            },
        }
        msg, meta = await self._post(payload)
        assert msg is not None
        result = msg.get("result") or {}
        self.server_info = result.get("serverInfo") or {}
        self.protocol_version = result.get("protocolVersion")
        meta.extra["server_info"] = self.server_info
        meta.extra["protocol_version"] = self.protocol_version
        self.last_meta = meta
        # Required by the spec; some servers tolerate its absence, but a real
        # client must send it, and testing without it would not exercise the
        # same session path real clients use.
        await self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            expect_response=False,
        )
        return result

    async def list_tools(self) -> list[ToolInfo]:
        request_id = self._next_id()
        msg, meta = await self._post(
            {"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": {}}
        )
        assert msg is not None
        self.last_meta = meta
        raw = (msg.get("result") or {}).get("tools") or []
        self.tools = [
            ToolInfo(
                name=t.get("name", ""),
                description=t.get("description", ""),
                input_schema=t.get("inputSchema") or {},
            )
            for t in raw
        ]
        return self.tools

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, CallMeta]:
        request_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        msg, meta = await self._post(payload)
        assert msg is not None
        self.last_meta = meta
        result = msg.get("result") or {}
        text = ""
        content = result.get("content") or []
        if content and isinstance(content[0], dict):
            text = content[0].get("text", "")
        if not text:
            return result, meta
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"status": "unparsed", "text": text}
        if result.get("isError"):
            data = {
                "status": "error",
                "msg": str(data.get("msg") or data)[:500],
                "raw": data if isinstance(data, dict) else None,
            }
        return data, meta

    async def timed_call(
        self, name: str, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, float, CallMeta]:
        started = time.perf_counter()
        data, meta = await self.call_tool(name, arguments)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return data, elapsed_ms, meta
