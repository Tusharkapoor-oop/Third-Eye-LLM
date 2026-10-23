# ADR-004: Dual MCP Content Representation

## Status
Accepted

## Context
The Model Context Protocol specification revision `2026-07-28` standardizes structured tool outputs through `outputSchema`. Modern MCP hosts parse `structured_content` directly as native JSON dictionaries. However, legacy and existing clients (early Cline, Roo Code, Continue) only expect an array of `TextContent` inside `content[0].text`. Emitting only structured content breaks legacy clients, while emitting only text strings ignores the modern 2026-07-28 protocol specification.

## Decision
Register every tool with an explicit, compact `outputSchema`. When returning results:
1. Provide the JSON-serialized payload as a single `TextContent` in the `content` list.
2. Simultaneously attach the Python dictionary to `structured_content`.

## Consequences
- **Positive**: 100% interoperability across both legacy and next-generation MCP clients without duplicate tool calls or client-side parsing failures.
- **Negative**: Marginal memory duplication inside the Python server process for the lifespan of the JSON-RPC response message.
