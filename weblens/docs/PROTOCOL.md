# MCP protocol notes

This document separates what was actually exercised from what the SDK merely
supports. No formal conformance suite has been run; see
[Gaps and non-claims](#gaps-and-non-claims).

## Implementation

- SDK: Python `mcp` **2.3.0**, server class `mcp.server.MCPServer`.
- Server name: `weblens`; version comes from `weblens.__version__`.
- Transport: stdio by default; optional Streamable HTTP at `/mcp`.
- Tools: four (`web_search`, `extract_url`, `crawl_site`, `deep_research`).
- No resources, prompts, sampling, elicitation, OAuth, or server-initiated
  requests are implemented.
- All tools are annotated read-only, non-destructive, idempotent, open-world.
- Tool results are MCP `content` text containing compact JSON. Structured
  output is disabled (`structured_output=False`).
- Server `instructions` tell the caller to treat retrieved pages as untrusted
  data and to preserve `no_reliable_result` / `conflicting_sources` /
  `possibly_outdated` states.

## Version and transport matrix

| Protocol version | Transport | What was verified | Status |
| --- | --- | --- | --- |
| `2026-07-28` | Streamable HTTP, stateless | `tools/list` with per-request `_meta` version, no `initialize`, no `Mcp-Session-Id`; four tools returned | Verified by automated test |
| `2025-11-25` | Streamable HTTP, stateless | `initialize` negotiates `2025-11-25`; subsequent `tools/list` succeeds without a session ID | Verified by automated test |
| `2025-06-18` | stdio/HTTP | SDK negotiation path only | Not directly tested |
| `2025-03-26` | stdio/HTTP | SDK default negotiated version constant only | Not directly tested |
| `2024-11-05` | - | - | Not claimed |

The modern request used in the test:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": {
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28"
    }
  }
}
```

The legacy request sequence used `initialize` with
`protocolVersion: "2025-11-25"`, then a normal `tools/list`. Both returned HTTP
200 and an SSE-framed JSON-RPC response. The response carried no
`Mcp-Session-Id`.

## Stateless behavior

HTTP is stateless by default:

```powershell
uv run weblens serve --http --port 8765
```

`--stateful` switches the SDK transport to sessionful mode for legacy clients
that require `Mcp-Session-Id`. Statefulness is a transport compatibility switch,
not an application feature: WebLens has no per-conversation server state beyond
the HTTP cache.

## Error semantics

There are two distinct outcomes:

1. **Transport/input failure** (`status: "error"`): the service payload is
   converted to a `ToolError`. MCP reports `isError: true`. Examples: invalid
   URL, budget below the tool floor, unsupported content type, fetch failure.
2. **Evidence state** (`no_reliable_result`, `conflicting_sources`,
   `possibly_outdated`, `partial`): a successful tool call with `isError:
   false`. The model must see and preserve the state; turning it into a
   transport error would encourage retries that cannot improve the evidence.

The CLI mirrors this: `status=error` exits 1, evidence states exit 0.

## Token/schema accounting

`weblens tokens` builds the server, calls `list_tools`, serializes each tool with
`model_dump(by_alias=True, exclude_none=True)`, and counts the compact JSON with
`tiktoken` `cl100k_base`.

Last measured: **838 tokens** total for the four-tool `tools/list` result (271
`web_search`, 185 `extract_url`, 254 `crawl_site`, 126 `deep_research`). The
benchmark gates this at 1,000 tokens. The count is tokenizer-dependent; it is
not a universal "context cost".

## Operational limits

- Default bind: `127.0.0.1:8765`.
- Non-loopback bind requires `--token` or explicit `--allow-insecure`.
- Bearer middleware compares the full `Authorization: Bearer <token>` header in
  constant time.
- There is no TLS termination in WebLens. Put it behind a TLS reverse proxy if
  it must cross an untrusted network.
- HTTP requests and responses are bounded by the SDK/uvicorn defaults plus the
  service's own fetch limits; no formal load test was run.

## Gaps and non-claims

- **Official conformance suite not run.** The tests assert specific message
  flows, not full spec coverage.
- Only `tools/list` is asserted for the modern stateless flow. Tool calls over
  that exact flow are exercised through the in-memory server and the CLI, but
  not separately over stateless HTTP.
- `2025-06-18`, `2025-03-26`, and `2024-11-05` are not directly tested.
- No OAuth, resource indicators, subscriptions, progress notifications, or
  cancellation behavior is implemented or tested.
- No browser-based MCP client (e.g., a remote web client) was tested. The HTTP
  server has no CORS policy of its own; keep it loopback-only.
- The SDK's negotiation behavior may change in a future `mcp` release; the
  lockfile pins 2.3.0 for reproducibility.

## Reproduce

```powershell
uv run pytest -q tests/test_mcp.py
uv run weblens tokens --pretty
```

For a manual HTTP probe, start the server and send a JSON-RPC POST with
`Accept: application/json, text/event-stream` to `http://127.0.0.1:8765/mcp`.
