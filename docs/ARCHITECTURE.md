# WebLens — Architecture Overview

This is the 5-minute version. Deeper references live alongside it in this
directory: [THREE_SYSTEM_ARCHITECTURE.md](THREE_SYSTEM_ARCHITECTURE.md),
[ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md),
[SECURITY_THREAT_MODEL.md](SECURITY_THREAT_MODEL.md).

## Shape of the system

```
MCP client (Claude Desktop / Cursor / Cline / any MCP host)
        │  JSON-RPC over stdio or Streamable HTTP
        ▼
┌──────────────────────────────────────────────────────────┐
│ weblens.cli  — profiles (core / research / full), auth,  │
│                rate limiting, security headers           │
├──────────────────────────────────────────────────────────┤
│ weblens.mcp_server — tool schemas + annotations,         │
│                      compact JSON payloads, budgets      │
├──────────────────────────────────────────────────────────┤
│ weblens.service.WebLens — orchestration facade           │
│   ├── search/    provider chain, ranking, dedupe         │
│   ├── net/       SafeFetcher + SSRF policy + proxy       │
│   ├── extract/   trafilatura / PyMuPDF / browser         │
│   ├── crawl/     robots, budgets, link discovery         │
│   ├── research/  multi-hop evidence + synthesis          │
│   └── apps/      deep research, company, market, sheets, │
│                  meeting, crawl2rag, research chat,      │
│                  tutorial                                │
├──────────────────────────────────────────────────────────┤
│ weblens.cache / redis_cache — TTL + stale-while-error    │
│ weblens.tenancy / ratelimit  — identity + token buckets  │
└──────────────────────────────────────────────────────────┘
```

## Design invariants

1. **Evidence, not prose.** Tools return URLs, fetch timestamps, exact
   character spans, gaps and conflicts. No component invents an answer.
2. **Every byte is budgeted.** `tokens.py` accounts for the whole serialized
   payload (envelope, `ms`, `tok`, warnings) with `cl100k_base`, and reports
   explicit `cut` / `budget_exhausted` states instead of silently truncating.
3. **Untrusted web content.** Fetched pages are data. Inline instructions are
   flagged, never followed; injection scanning runs on passages and HTML
   comments.
4. **Bounded work.** Crawl depth, page counts, concurrency, redirects, response
   sizes and provider timeouts all have hard limits from `config.Settings`.
5. **Failures are explicit.** `status` is a first-class field:
   `ok`, `no_reliable_result`, `conflicting_sources`, `possibly_outdated`,
   `error` with a machine code. An empty result is a finding, not an exception.
6. **Two trees, one source of truth.** `weblens/src/weblens` is canonical and
   mirrored byte-for-byte into `src/weblens` (guard test + CI step).

## Request lifecycle (HTTP MCP)

1. `cli.py` resolves the profile and builds the ASGI app: auth middleware →
   rate-limit middleware → security headers → StreamableHTTP session manager.
2. Non-loopback binds require `WEBLENS_HTTP_TOKEN`/`WEBLENS_API_KEYS`; the
   process exits with status 2 rather than serving unauthenticated.
3. `mcp_server.build_server` registers tools per profile and refuses to register
   stateful tools when `allow_stateful=False` (public listener).
4. A tool call delegates to `service.WebLens`, which enforces budgets, caches
   where allowed, and maps failures through `errors.py` into stable codes.

## Extension points

- **New search provider:** implement `search.base.SearchProvider`
  (`name`, `async search(...) -> list[Hit]`) and register it in
  `search/router.py::_build`.
- **New tool:** add a `@server.tool` in `mcp_server.py`, keep the compact-JSON
  contract, annotate read-only vs mutating, and document it in
  `MCP_API_REFERENCE.md`.
- **New cache backend:** mirror the async surface of `cache.Cache`
  (`get_json`/`set`/`close`) as `redis_cache.py` does.

## Known limits (deliberate)

- No LLM synthesis: research output is extractive by design.
- Cross-tenant isolation is per-token, not per-user (see `SECURITY.md`).
- Prompt-injection detection is advisory; it is not a security boundary.
- Browser rendering requires Playwright and is optional (`browser` extra).
