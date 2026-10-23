# ADR 0003: Four read-only MCP tools; stateless HTTP default

- Status: Accepted
- Date: 2026-10-21

## Context

Every tool description and schema is paid for on every model turn. A large MCP
surface (dozens of tools, verbose descriptions, structured output schemas) wastes
context and increases selection errors. The service also needs to work with both
modern stateless MCP clients and legacy clients that expect `initialize` and
`Mcp-Session-Id`.

## Decision

Expose exactly four tools:

- `web_search`
- `extract_url`
- `crawl_site` (`mode=map|crawl`)
- `deep_research`

Use compact descriptions, short parameter names only where the caller sees them,
and `structured_output=False`. Return compact JSON text and mark all tools
read-only/non-destructive. Tool schemas are gated at 1,000 `cl100k_base` tokens;
the measured value is 838.

Serve stdio by default. The optional Streamable HTTP transport is stateless by
default; `--stateful` is an explicit compatibility switch. The server supports
the modern `2026-07-28` per-request flow and legacy `2025-11-25` initialize flow
at the message level (see `PROTOCOL.md`).

## Alternatives considered

- **One generic `web` tool with an action enum:** fewer tools, but a larger
  discriminated schema and worse discoverability.
- **Separate map and crawl tools:** clearer, but adds a fifth schema and
  duplicates parameters.
- **Stateful sessions by default:** better for legacy clients, but unnecessary
  server state and a session-fixation/ownership surface.
- **Structured output schemas:** better typing, but token-expensive and not
  needed for compact JSON.

## Consequences

- The caller must read short keys; the README documents them.
- `crawl_site` has a mode switch instead of two tools.
- Modern clients avoid initialization and session IDs; legacy clients still work
  with `initialize`.
- Four tools may be too coarse for a workflow that wants separate sitemap and
  extraction tools; no such requirement was measured.
