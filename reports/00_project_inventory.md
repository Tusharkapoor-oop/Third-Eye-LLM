# Phase Zero: Project Inventory — Baseline

**Date:** 2026-10-23
**Commit:** b531618
**Working directory:** C:\Users\ACER\Downloads\Broswer for ai agnets

## Repository Structure

```
Broswer for ai agnets/          # Project root (Windows 11 target)
├── .github/
│   ├── ci.yml                  # CI pipeline
│   └── weblens-ci.yml          # weblens CI pipeline
├── .gitignore                  # Excludes .env*, .venv/, __pycache__, bench output
├── README.md                   # Project documentation
├── pyproject.toml              # Build config, deps, entry point: src.server.mcp_server:main
├── uv.lock                     # Lockfile
├── .env.example                # Config template (CONTAINS Tavily API key - NEVER COMMIT)
├── modelcontextprotocol-server-2.3.1.tgz  # MCP server package
├── package/                    # Package metadata (package.json)
├── src/                        # ACTIVE ENGINE (53 Python files) - wired into pyproject.toml
│   ├── engine/
│   │   ├── config.py           # EngineConfig dataclass (env vars, defaults)
│   │   ├── security.py         # SSRF protection, prompt injection sanitization
│   │   ├── search/
│   │   │   ├── aggregator.py   # SearchAggregator - provider orchestration, dedup, token budgeting
│   │   │   ├── base.py         # SearchProvider, SearchResult, SearchResponse
│   │   │   ├── bing_provider.py
│   │   │   ├── brave_provider.py
│   │   │   ├── ddg_html_provider.py
│   │   │   ├── ddgs_provider.py
│   │   │   └── wiki_provider.py
│   │   ├── extract/
│   │   │   ├── extractor.py    # DocumentExtractor - HTML/PDF extraction, passages, BM25
│   │   │   ├── chunker.py      # DocumentChunker
│   │   │   ├── passage_scorer.py  # BM25PassageScorer
│   │   │   └── browser_fallback.py  # Headless browser SPA fallback
│   │   ├── crawl/
│   │   │   ├── crawler.py      # WebsiteCrawler - bounded recursive crawl
│   │   │   ├── mapper.py       # WebsiteMapper - sitemap/URL discovery
│   │   │   └── robots.py       # RobotsManager
│   │   └── research/
│   │       └── deep_research.py # DeepResearchEngine - multi-query research
│   └── server/
│       ├── mcp_server.py       # MCP server - 5 tools, STDIO + HTTP transport
│       ├── tools.py            # TOOL_DEFINS - compact JSON schemas
│       └── token_counter.py    # Schema token measurement (tiktoken)
├── weblens/                    # DUPLICATE package (36 files) - version 0.1.0
│   ├── src/weblens/            # Full copy: search, net, extract, crawl, research, security
│   ├── tests/                  # weblens test suite
│   ├── benchmarks/             # weblens benchmarks with historical results
│   ├── docs/                   # weblens architecture docs + ADRs
│   └── pyproject.toml, uv.lock
├── webintel/                   # DUPLICATE package (19 files) - third implementation
│   ├── server.py, security.py, config.py, cache.py, crawl.py, extract.py
│   ├── search/ (base, engine, brave, bing_rss, searxng, tavily)
│   ├── __main__.py, http_client.py, limits.py, ranking.py, research.py, utils.py
├── tests/                      # 237 tests across 16 test modules
├── bench/                      # 22 debug/inspection scripts
├── benchmarks/                 # Benchmark runner + 50-query eval dataset
│   ├── run_benchmarks.py       # 50-query benchmark with regression gates
│   ├── eval_dataset.json       # 50 queries across 5 categories
│   └── benchmark_results.json  # Previous 5-query run (stale)
├── docs/                       # Architecture, threat model, research report, competitor matrix, ADRs
├── examples/                   # MCP client configs (Cline, Continue, Cursor, Roo Code)
├── legacy/                     # Legacy weblens tests
└── reports/                    # THIS MISSION's output directory
```

## Entry Points

| Entry Point | Command | Purpose |
|---|---|---|
| MCP Server (STDIO) | `python -m src.server.mcp_server` | Default MCP transport |
| MCP Server (HTTP) | `python -m src.server.mcp_server --transport http --port 8000` | Streamable HTTP |
| CLI script | `web-intel-mcp` (from pyproject) | Installed console script |
| Benchmark | `python -m benchmarks.run_benchmarks` | 50-query eval suite |

## Configuration (.env.example)

| Variable | Default | Notes |
|---|---|---|
| MCP_SERVER_NAME | personal-web-intelligence | |
| MCP_SERVER_VERSION | 1.0.0 | |
| MCP_HOST | 127.0.0.1 | |
| MCP_PORT | 8765 | |
| DEFAULT_SEARCH_PROVIDER | ddgs | Free, no key needed |
| TAVILY_API_KEY | tvly-dev-* (in .env.example) | **NOT set in environment** |
| BRAVE_SEARCH_API_KEY | false/na | Not configured |
| EXA_API_KEY | (empty) | Not configured |
| SEARXNG_BASE_URL | (empty) | Not configured |
| DEFAULT_SEARCH_TOKEN_BUDGET | 600 | R1 requirement |
| DEFAULT_EXTRACT_TOKEN_BUDGET | 1200 | R1 requirement |
| DEFAULT_DEEP_RESEARCH_TOKEN_BUDGET | 2000 | R1 requirement |
| HTTP_CONNECT_TIMEOUT_SECONDS | 8.0 | |
| HTTP_READ_TIMEOUT_SECONDS | 12.0 | |
| MAX_HTTP_RESPONSE_BYTES | 5242880 | 5 MB cap |
| MAX_CRAWL_PAGES | 15 | |
| MAX_CRAWL_DEPTH | 3 | |
| ENABLE_BROWSER_FALLBACK | true | Headless Edge for SPAs |
| BROWSER_BINARY_PATH | (empty) | |

## Secrets Status

- **TAVILY_API_KEY: NOT SET in environment** — `.env.example` contains a key but it must never be copied or committed
- No `.env` file exists
- Tavily provider (`tavily.py`) exists in both `src/weblens/search/` and `webintel/search/` but is NOT in the active `src/engine/search/`
- Active provider: `ddgs` (DuckDuckGo via ddgs library) — free, no key required

## Dependencies (pyproject.toml)

| Package | Version | Purpose |
|---|---|---|
| mcp | >=2.3.0 | MCP protocol |
| mcp-types | >=2.3.0 | MCP types |
| httpx | >=0.28.1 | HTTP client |
| trafilatura | >=2.3.1 | HTML extraction |
| ddgs | >=9.16.0 | DuckDuckGo search |
| beautifulsoup4 | >=4.15.0 | HTML parsing |
| lxml | >=6.1.3 | XML/HTML parsing |
| pydantic | >=2.13.0 | Data validation |
| tiktoken | >=0.14.0 | Token counting |
| pymupdf | >=1.28.0 | PDF extraction |
| starlette | >=1.9.0 | HTTP framework |
| uvicorn | >=0.54.0 | ASGI server |
| pytest | >=9.1.0 | Testing (dev) |
| pytest-asyncio | >=1.4.0 | Async testing (dev) |
| psutil | >=7.2.0 | Load testing (dev) |

**Missing from venv at baseline:** bs4, psutil, numpy, pip (all installed during this session)

## Tools Exposed (MCP)

| Tool | Parameters | Purpose |
|---|---|---|
| web_search | query, count (1-10), time_filter, domains, max_tokens | Web search |
| extract_url | url, query, mode (passages\|full), max_tokens, render_js | Content extraction |
| crawl_website | url, max_depth (1-3), max_pages (1-20), allowed_paths, max_tokens_per_page | Bounded crawl |
| web_map | url, limit (1-100) | URL structure discovery |
| deep_research | topic, max_depth, max_queries | Multi-step research |

## Test Suite: 237 tests, 16 modules

See `reports/00_existing_test_inventory.md` for full results.

**18 failures at baseline:**
- 11 injection sanitization failures (CRITICAL - prompt injection not detected)
- 1 crawler trap detection failure
- 2 load stress test bugs (undefined variables)
- 3 MCP stress validation failures
- 1 token budget boundary failure

## Benchmark Baseline (50 queries, live network)

| Metric | Value | Gate | Status |
|---|---|---|---|
| Schema tokens (o200k) | 680 | < 1000 | PASSED |
| Schema tokens (cl100k) | 655 | < 1000 | PASSED |
| Search tokens avg/max | 76.5 / 345 | < 600 | PASSED |
| Extract tokens avg/max | 571.0 / 904 | < 1500 | PASSED |
| Search latency p50/p95 | 3.06s / 9.94s | < 15s | PASSED |
| Extract latency p50/p95 | 5.91s / 10.89s | < 15s | PASSED |
| Precision@5 | 0.694 | — | — |
| Answer-support rate | 40.0% (16/40) | > 60% | FAILED |
| Citation correctness | 82.5% (33/40) | — | — |
| False-confidence rate | 20.0% (2/10) | < 15% | FAILED |
| No-result correctness | 80.0% (8/10) | — | — |
| Total elapsed | 405.65s | — | — |

## Known Duplication

Three overlapping packages implement the same engine:
1. `src/` — ACTIVE (53 files, wired to pyproject.toml)
2. `weblens/src/weblens/` — DUPLICATE (36 files)
3. `webintel/` — DUPLICATE (19 files)

Security implementations duplicated across:
- `src/engine/security.py` (SSRF + injection)
- `src/weblens/net/ssrf.py` (SSRF, different implementation)
- `src/weblens/security/injection.py` (injection, different patterns)
