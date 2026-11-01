# Phase One: Competitor Discovery and Repository Research

**Date:** 2026-10-23
**Research method:** Web search + GitHub repository inspection
**License verification:** All licenses checked before noting reuse potential

---

## Commercial Competitors

### 1. Tavily (tavily-ai/tavily-mcp)

| Dimension | Detail |
|---|---|
| Repository URL | https://github.com/tavily-ai/tavily-mcp |
| License | MIT |
| Created | 2025-01-27 |
| Commits | 239 |
| Last activity | Active (2026) |
| API endpoints | /search, /extract, /crawl, /map, /research |
| Python SDK | tavily-python (tavily-ai/tavily-python, MIT, v0.8.2) |
| API key required | Yes (tvly-...), keyless mode available but rate-limited |
| Windows compatible | Yes (Python) |
| Cost | API credits: basic/fast/ultra-fast = 1 credit, advanced = 2 credits per search; extract basic = 1 credit/5 URLs, advanced = 2 credits/5 URLs |
| Search quality | AI-powered with citations, answer generation |
| Extraction | Native extraction with raw_content, images, favicon |
| MCP support | Official MCP server |
| Reuse potential | High — official Python SDK, MIT licensed, can integrate Tavily as a provider |

**Notes:** Tavily is the primary commercial benchmark. The project's `.env.example` references `TAVILY_API_KEY` but the key is NOT set in the environment. Tavily's search_depth parameter (basic/advanced) controls latency vs relevance tradeoff.

---

### 2. Firecrawl (firecrawl/firecrawl-mcp-server)

| Dimension | Detail |
|---|---|
| Repository URL | https://github.com/firecrawl/firecrawl-mcp-server |
| License | MIT (MCP server), AGPL-3.0 (core Firecrawl) |
| Stars | 6,639 |
| Forks | 770 |
| Commits | 317 |
| Created | 2024-12-06 |
| Last publish | v3.17.0, 2 days ago (npm) |
| API key required | Yes (fc-...) |
| Windows compatible | Yes (npx) |
| Cost | Cloud credits; self-hosted open source available |
| Search quality | Search indexes for dev sources, gov sources, scientific papers |
| Extraction | Clean markdown, structured JSON, screenshots, PDF/DOCX parsing |
| MCP support | Official MCP server (stdio + Streamable HTTP) |
| Reuse potential | Medium — AGPL-3.0 core may not be suitable for all projects; MCP server is MIT |

**Notes:** Firecrawl handles rotating proxies, rate limits, JS-blocked content. Has "interact" capability (click, scroll, write, wait). MCP server exposes scrape, crawl, search, extract, deep research, batch scrape.

---

### 3. Brave Search API

| Dimension | Detail |
|---|---|
| Type | Commercial search API |
| API key required | Yes |
| Windows compatible | Yes (REST API) |
| Cost | Paid API |
| Reuse potential | Medium — can be added as a search provider |

**Notes:** Project already references `BRAVE_SEARCH_API_KEY` in config but it's not set. Brave provider exists in `src/weblens/search/brave.py` and `webintel/search/brave.py` but NOT in active `src/engine/search/`.

---

### 4. Exa

| Dimension | Detail |
|---|---|
| Type | Commercial AI search API |
| API key required | Yes |
| Cost | Paid API |
| Reuse potential | Medium |

**Notes:** Project references `EXA_API_KEY` in config but not set.

---

### 5. SearXNG

| Dimension | Detail |
|---|---|
| Type | Open source metasearch engine |
| License | AGPL-3.0 |
| Self-hostable | Yes |
| Windows compatible | Yes (Docker or bare metal) |
| API key required | No (self-hosted) |
| Reuse potential | Medium — can be used as a search backend via `SEARXNG_BASE_URL` |

**Notes:** Project references `SEARXNG_BASE_URL` in config but not set. SearXNG providers exist in `src/weblens/search/searxng.py` and `webintel/search/searxng.py` but NOT in active `src/engine/search/`.

---

## Open-Source Competitors

### 6. vishalkg/web-search (Python MCP server)

| Dimension | Detail |
|---|---|
| Repository URL | https://github.com/vishalkg/web-search |
| License | MIT |
| Created | 2025-09-12 |
| Commits | 53 |
| Language | Python 3.12+ |
| Windows compatible | Yes |
| Providers | Google, Bing, DuckDuckGo, Startpage, Brave Search |
| Key features | Connection pooling (30-50% faster), asyncio.gather parallel execution, LRU cache with compression, auto-rotation logs/metrics, intelligent fallbacks (Google→Startpage, Bing→DuckDuckGo) |
| MCP support | Yes |
| Reuse potential | High — MIT licensed, Python, connection pooling and caching patterns directly applicable |
| Install | `uvx --from git+https://github.com/vishalkg/web-search websearch-server` |

**Notes:** Strong candidate for borrowing connection pooling, LRU caching, and fallback patterns. Installation via `uvx` works on Windows.

---

### 7. mrkrsl-web-search-mcp (TypeScript MCP server)

| Dimension | Detail |
|---|---|
| Repository URL | https://github.com/iflow-mcp/mrkrsl-web-search-mcp |
| License | MIT |
| Created | 2026-02-27 |
| Commits | 46 |
| Language | TypeScript |
| Windows compatible | Yes (Node.js) |
| Providers | Bing (primary, Chromium), Brave (secondary, Firefox), DuckDuckGo (fallback, Axios) |
| Key features | Multi-engine with browser isolation, full page content extraction, 3 specialized tools |
| MCP support | Yes |
| Reuse potential | Low — TypeScript/Node.js, different stack than project |

**Notes:** Good reference for multi-engine fallback strategy but different technology stack.

---

### 8. @theosunxyzw/web-search-mcp (npm)

| Dimension | Detail |
|---|---|
| Repository URL | npm package |
| License | Not specified in search results |
| Language | Bun/TypeScript |
| Windows compatible | Yes |
| Key features | SQLite cache with FTS5 fuzzy search (30-day TTL), Mozilla Readability extraction, parallel fetching (5 pages), technical site prioritization (GitHub, StackOverflow, MDN, npm, PyPI, etc.) |
| MCP support | Yes |
| Reuse potential | Medium — SQLite FTS5 caching pattern and Readability extraction are valuable |
| Install | `bunx @theosunxyzw/web-search-mcp` |

**Notes:** SQLite FTS5 cache and Mozilla Readability are patterns worth considering for the token efficiency work.

---

### 9. Taka499/mcp-web-search (Python)

| Dimension | Detail |
|---|---|
| Repository URL | https://github.com/Taka499/mcp-web-search |
| License | Not specified |
| Created | 2025-07-21 |
| Commits | 20 |
| Stars | 0 |
| Providers | SerpAPI, Perplexity, DuckDuckGo, Tavily, Claude |
| Key features | Multi-provider with automatic fallback, multi-provider comparison |
| Reuse potential | Low — minimal activity, 0 stars, unclear license |

---

### 10. galangw/mcp-websearch (Node.js)

| Dimension | Detail |
|---|---|
| Repository URL | https://github.com/galangw/mcp-websearch |
| License | MIT |
| Created | 2025-12-16 |
| Commits | 7 |
| Language | Node.js |
| API | SearchAPI.io (Google Search + AI Mode) |
| Transport | Streamable HTTP (MCP spec 2025-03-26) |
| Reuse potential | Low — different stack, SearchAPI.io dependency |

---

## Comparative Summary

| Project | Language | License | Stars | Commits | Last Activity | MCP | Free tier | Windows |
|---|---|---|---|---|---|---|---|---|
| WebIntel (this project) | Python | — | — | 0 (baseline) | 2026-10-23 | Yes | Yes (ddgs) | Yes |
| Tavily MCP | Python | MIT | — | 239 | Active | Yes | Keyless (rate-limited) | Yes |
| Firecrawl MCP | TypeScript | MIT | 6,639 | 317 | 2 days ago | Yes | No (credits) | Yes |
| vishalkg/web-search | Python | MIT | — | 53 | 2025-09 | Yes | Yes (scraping fallback) | Yes |
| mrkrsl-web-search-mcp | TypeScript | MIT | — | 46 | 2026-02 | Yes | Yes (no API key) | Yes |
| @theosunxyzw/web-search-mcp | Bun/TS | — | — | — | — | Yes | Yes | Yes |
| Taka499/mcp-web-search | Python | ? | 0 | 20 | 2025-07 | Yes | Yes (DDG) | Yes |
| galangw/mcp-websearch | Node.js | MIT | — | 7 | 2025-12 | Yes | No (SearchAPI.io) | Yes |
| SearXNG | Python | AGPL-3.0 | — | — | Active | No | Self-hosted | Yes |

---

## Components Worth Reusing (License permitting)

| Component | Source | Pattern | License |
|---|---|---|---|
| Connection pooling + asyncio.gather | vishalkg/web-search | HTTP reuse, parallel batch ops | MIT |
| LRU cache with compression | vishalkg/web-search | Cached normalized results | MIT |
| SQLite FTS5 cache | @theosunxyzw/web-search-mcp | 30-day TTL, fuzzy search | Unknown |
| Mozilla Readability extraction | @theosunxyzw/web-search-mcp | Main article content → Markdown | Unknown |
| Multi-engine fallback | mrkrsl-web-search-mcp | Bing → Brave → DDG | MIT |
| Tavily Python SDK | tavily-ai/tavily-python | Search/extract/crawl/map/research client | MIT |
| Search depth tradeoff | Tavily API | basic vs advanced latency/relevance | Commercial |

---

## Shortlist for Benchmark Track B

1. **Tavily** (commercial baseline) — using existing Tavily API key if available, otherwise keyless mode
2. **vishalkg/web-search** — MIT licensed Python MCP server, installable via uvx
3. **Firecrawl** — only if API key available (not expected)

**Not shortlisted:** TypeScript/Node.js projects (different stack), low-activity projects (Taka499, galangw), SearXNG (requires self-hosting infrastructure).

---

## Research Sources

- Tavily docs: https://docs.tavily.com/documentation/api-reference/introduction
- Tavily SDK: https://github.com/tavily-ai/tavily-python
- Tavily MCP: https://github.com/tavily-ai/tavily-mcp
- Firecrawl MCP: https://github.com/firecrawl/firecrawl-mcp-server
- vishalkg/web-search: https://github.com/vishalkg/web-search
- mrkrsl-web-search-mcp: https://github.com/iflow-mcp/mrkrsl-web-search-mcp
- @theosunxyzw/web-search-mcp: https://www.npmjs.com/package/@theosunxyzw/web-search-mcp
- Taka499/mcp-web-search: https://github.com/Taka499/mcp-web-search
- galangw/mcp-websearch: https://github.com/galangw/mcp-websearch
