# Phase 08: Provider and Integration Audit

Every integration discovered on this machine, verified rather than assumed.
Quota evidence pulled live from the official usage API on 2026-10-24.

## Tavily

| Check | Result [tag] |
|---|---|
| Detected | key in git-ignored `.env`; `tvly-` prefix, 57 chars, never printed [MEASURED, redacted count only] |
| Quota | plan **Researcher**, usage **118/1000 credits** at audit start (usage endpoint HTTP 200) [MEASURED] |
| Budget policy | hard cap = 60 % of remaining ≈ 529 credits target; actual spend this audit ≈ **40 search credits** (40 paired queries × 1 provider) [MEASURED, logged per run manifest] |
| Search latency + reliability | paired ddgs-vs-tavily run (80 rows) — see `reports/11-quality-and-factual-accuracy.md` and produce table from `reports/benchmark_runs/run_79ce051b.jsonl` |
| Extract/crawl/map/research endpoints | **NOT RUN** — search-only comparison; spending caps honored (each extra endpoint is separately billed credits) |
| Wired into engine | `TavilySearchProvider` registered in `SearchAggregator.providers` when key present [MEASURED via import test in test suite] |

## DuckDuckGo (`ddgs`, default keyless provider)

| Check | Result |
|---|---|
| Default provider | `DEFAULT_SEARCH_PROVIDER=ddgs` [OFFICIAL config] |
| Long run observed | 160-query ddgs-only run, 160/160 success **[MEASURED]** (`run_c09bb27b.jsonl`) |
| Latency tail | 2/91 timeouts in an earlier expanded run [MEASURED] (`run_4ab70742.jsonl`) |
| Rate-limit resilience | repeated-burst behavior not stress-tested against DDG infrastructure (politeness policy) — declared |

## SearXNG (localhost)

| Check | Result |
|---|---|
| Endpoint alive | `http://localhost:8080` HTTP 200 [MEASURED] |
| JSON API | **HTTP 403** — requires `formats: [html, text, json]` in server settings; audited process did not modify server config [MEASURED + reason] |
| Status | **BLOCKED** (not silent skip) |

## Brave Search / Exa

| Check | Result |
|---|---|
| Keys | empty in `.env` [MEASURED] → **NOT RUN** |
| Code path | providers exist for both (`brave_provider.py`, SearXNGProvider class) [MEASURED via source] |

## Local model runtimes

| Runtime | Result |
|---|---|
| Ollama | not installed [MEASURED] → **NOT RUN** |
| LM Studio `localhost:1234` | connection refused [MEASURED] → **NOT RUN** |
| Cloud models | no cloud-model credentials discoverable in workspace [MEASURED] → **NOT RUN** |

## MCP server stack (the product surface itself)

| Tool | Registered | Schema present |
|---|---|---|
| web_search / extract_url / crawl_website / web_map / deep_research | all 5 [MEASURED, protocol tests] | 680 o200k tokens total [MEASURED] |
| Transport | STDIO (default) and `--transport http --port 8765` [OFFICIAL CLI] |
| Structured errors | parameter validation errors now return structured error results (3 regression cases fixed) [MEASURED] |

## UNIDENTIFIED tooling (owner-supplied names)

"Meta browser", "Spark", "Tavily browser" — no product, extension, config, or
dependency matching any of these names is discoverable here [MEASURED absence].
Recorded as UNIDENTIFIED per protocol; awaiting your clarification; nothing was
substituted.

## Meta/Spark verdict

No fabricated integration. Every unconfigured/unreachable item above is marked
`NOT RUN` or `BLOCKED` with its exact reason rather than skipped silently.
