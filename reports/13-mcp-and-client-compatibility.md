# Phase 13: MCP and Client Compatibility

## What was actually executed [MEASURED]

| Area | Test | Result |
|---|---|---|
| Tool listing | 5 tools registered with compact schemas | PASS (`test_mcp_protocol=test_mcp_tool_listing`, `test_mcp_stress=test_mcp_tool_listing`) |
| Schema token budget | 680 o200k / 655 cl100k | PASS `< 1000` (`test_mcp_e2e_test_tools_list_and_schema_budget`) |
| Live roundtrip via server interface | live `web_search` call (4.7 s) | PASS (`test_mcp_e2e_test_live_web_search_payload_contract`) |
| Live `extract_url` on SSRF-attempting URL | rejected without network | PASS (`test_mcp_e2e_test_extract_url_rejects_private_without_net`) |
| Malformed requests | missing param / wrong type / null URL / unknown tool / rapid-fire / concurrent sessions | PASS (post-fix structured errors, `test_mcp_stress`) |
| MCP package version pinned | `mcp >= 2.3.0`; vendored tarball `modelcontextprotocol-server-2.3.1.tgz` at repo root | present [MEASURED artifact] |

## Client compatibility — executed matrix

| Client | Executed? | Evidence |
|---|---|---|
| Built-in python MCP client session (STDIO) | YES | full protocol + stress suites |
| HTTP transport (Streamable HTTP, port 8765) | rendered part (CLI offers it); live HTTP roundtrip **NOT RUN** in this audit pass — declared |
| Cline / Roo Code / Continue / VS Code | configs exist in `examples/` but those clients are not installed on this machine → **NOT RUN** (declared honestly) |
| Ollama / LM Studio local models | not installed / port closed → **NOT RUN** |

## Honest verdict

The engine's MCP surface is validated at the protocol/tooling layer
(definitions, schemas, error taxonomy, malformed input handling, live
roundtrips). Claims about specific GUI clients (Cline/Roo/Continue/VS Code)
would require executable evidence that this audit does not have; none is made.
Model-context behavior with local cloud models (3rd-party examples/repository
docs in `examples/`) counts as **[OFFICIAL config samples]**, not measured
compatibility.
