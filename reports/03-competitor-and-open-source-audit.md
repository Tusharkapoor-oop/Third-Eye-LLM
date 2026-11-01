# Phase 03: Competitor and Open-Source Audit

Full discovery research with sources: see `reports/01_competitor_research.md`
(url/docs citations per candidate). This report adds the decision-relevant
dimension table and separates **[MEASURED]** values from **[OFFICIAL]** /
**[THIRD-PARTY]** claims.

## System selection and pinned identity

| # | System | Identity pinned | Access on this machine | Selected as |
|---|---|---|---|---|
| S0 | WebIntel engine (root `src/`) | local commit `b531618`+working tree | **[MEASURED]** | primary subject |
| S1 | WebLens package (`weblens/`) | local v0.1.0 tree | **[MEASURED]** | secondary subject |
| S2 | Tavily Direct API | `tavily-python` SDK semantics, endpoint `api.tavily.com` | **[MEASURED]** (key from `.env`, Researcher plan, 118/1000 credits used at audit time) | commercial reference |
| S3 | DuckDuckGo via `ddgs` lib | active default provider | **[MEASURED]** | keyless reference |
| S4 | Firecrawl MCP | repo inspected, MIT/AGPL duel-license, needs `fc-` key | not configured → **NOT RUN** (no key on machine) | excluded |
| S5 | Brave Search API | provider code exists, key empty | **NOT RUN** (no key) | excluded |
| S6 | Exa | key empty | **NOT RUN** (no key) | excluded |
| S7 | SearXNG (localhost) | `http://localhost:8080` reachable but JSON API answers HTTP 403 (format not enabled) | **BLOCKED** (server config not writable by this audit; documented) | partial |
| S8 | vishalkg/web-search MCP | MIT, 53 commits | **NOT RUN** (standalone server; time-boxed out of this audit phase) | documented |
| S9 | Ollama / LM Studio local models | not installed / port not listening | **BLOCKED** | excluded |

"Meta browser", "Spark", "Tavily browser": **UNIDENTIFIED** [MEASURED absence]. 
No Meta or Spark browser product, extension, config entry, or dependency was found
in this repo, `.env*` files, `pyproject.toml` files, or Windows installed-program
references visible to this audit. Nothing was substituted. If you know the exact
product names, supply them and I will include them.

## Dimension table (measured where marked)

| Dimension | Tavily Direct **[MEASURED] where noted** | ddgs (keyless) **[MEASURED]** | WebIntel S2 (+Tavily) **[MEASURED]** | Notes |
|---|---|---|---|---|
| Quality: precision@5 | see `reports/11-quality-and-factual-accuracy.md` paired subset | same | same | paired 40-label subset; single-tokenizer judging |
| Schema tokens | ~n/a (direct SDK tools not schema-measured here) | n/a | 680 o200k **[MEASURED]** | WebIntel exposes 5 tools |
| Latency distribution | see provider table | see provider table | see provider table | p50/p95 measured |
| Cost | 1 credit/search **[OFFICIAL]**; 118/1000 credits used **[MEASURED]** | free (no quota) **[OFFICIAL]** | +0 free tokens budget | cost per 1000 queries = 1000 credits |
| Reliability | success/timeout taxonomy in provider table | same | adds aggregator fallback | |
| Security | external service (no SSRF surface of ours) | same | SSRF+injection guarded **[MEASURED 56IP+27inj tests]** | |
| License | commercial **[OFFICIAL]** | BSD-3 `ddgs` **[OFFICIAL]** | proprietary to owner | |

## Key findings

1. **Tavily is the strongest keyed frontier service available here** and is the
   commercial reference. Its SDK is MIT and already vendored into the engine as
   `src/engine/search/tavily_provider.py` — the engine can use Tavily *as a
   provider*, which is a legitimate integration, not a competitor imitation.
2. **Firecrawl self-hosted is not runnable in this time budget** (AGPL core, heavy
   services stack), and SearXNG on this host answers HTTP 403 on the JSON API
   (format not enabled), so a live SearXNG comparison is **BLOCKED**, not
   skipped-quietly.
3. **The systems measurable like-for-like are**: Tavily direct, ddgs keyless, and
   the engine over either backend. The TypeScript MCP servers (firecrawl-mcp,
   mrkrsl, galangw) were excluded for stack mismatch, low maintenance, or missing
   keys — documented above, not hidden.
4. **License constraints respected**: no AGPL code was copied. Patterns (pooling,
   caching, fallback order) were used conceptually only [PROPOSAL→RETAIN].

## Open-source components worth adopting later **[PROPOSAL — not implemented here]**

- SQLite FTS5 search-cache with TTL (from `@theosunxyzw/web-search-mcp`, license
  unclear → do not copy code; implement fresh if adopted).
- Connection pooling + `asyncio.gather` parallel fetch (from `vishalkg/web-search`,
  MIT → reimplementable wholesale legally).

## Honest limits

- Stars/release metrics quoted in `01_competitor_research.md` are **[THIRD-PARTY]**
  GitHub data fetched during the earlier session on 2026-10-23; they were not
  re-verified today except where tagged.
- No paid-keyless-blind competitor (Exa/Brave) numbers exist in any report —
  absence declared.
