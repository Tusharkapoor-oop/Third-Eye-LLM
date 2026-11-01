# Phase Zero: Architecture Map — Baseline

**Date:** 2026-10-23
**Commit:** b531618

## High-Level Architecture

```
MCP Client (Cline/Roo/Continue/Ollama)
         │ JSON-RPC (STDIO / HTTP)
         ▼
┌─────────────────────────────────────────┐
│   WebIntel MCP Server (src/server/)     │
│   - mcp_server.py: 5 tool handlers      │
│   - tools.py: compact JSON schemas      │
│   - token_counter.py: schema token meas.│
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│   Engine Layer (src/engine/)            │
│   ┌──────────┐ ┌──────────┐ ┌────────┐  │
│   │ Search   │ │ Extract  │ │ Crawl  │  │
│   │ Aggreg.  │ │ Extractor│ │ Crawler│  │
│   └──────────┘ └──────────┘ └────────┘  │
│   ┌──────────┐ ┌──────────┐              │
│   │ Mapper   │ │ Research │              │
│   └──────────┘ └──────────┘              │
│   ┌──────────────────────────────┐       │
│   │ Security (SSRF + injection)  │       │
│   │ Config (env vars)            │       │
│   └──────────────────────────────┘       │
└─────────────────────────────────────────┘
         │
         ▼
External: DuckDuckGo (ddgs), Bing, Wikipedia, Brave (if key), Trafilatura,
          PyMuPDF, headless Edge (SPA fallback)
```

## Component Responsibilities

### src/server/mcp_server.py
- Creates MCPServer with 5 tools: web_search, extract_url, crawl_website, web_map, deep_research
- Lazy-loaded engine singletons (global _aggregator, _extractor, _crawler, _mapper, _researcher)
- `format_result()` — dual output: TextContent + structured_content for MCP 2.x
- `format_error()` — wraps exceptions as structured error results
- `main()` — CLI with --transport (stdio|http), --host, --port args

### src/server/tools.py
- TOOL_DEFINS: 5 compact JSON Schema tool definitions
- Each with name, description, inputSchema (type, properties, required, defaults, enums)
- Designed for minimal token footprint (680 o200k / 655 cl100k total)

### src/engine/config.py
- EngineConfig frozen dataclass
- All values from environment variables with defaults
- Single global CONFIG instance

### src/engine/search/aggregator.py
- SearchAggregator class — orchestrates 5 providers (bing, wikipedia, ddgs, ddg_html, brave/searxng if configured)
- URL normalization (strip tracking params, fragments, lowercase scheme/netloc)
- Domain diversity (max 2 per domain unless explicitly restricted)
- Token budget enforcement with snippet truncation
- Query relevance checking (stopword filtering)
- Fallback provider chain on timeout/zero results/weak relevance
- 1-hour cache with TTL
- "Zero fake accuracy" gating: blocks results when distinctive numbers/words from query are absent
- 260 lines — God object candidate (violates SRP)

### src/engine/search/base.py
- SearchProvider abstract base class
- SearchResult, SearchResponse dataclasses

### src/engine/search/*_provider.py
- bing_provider.py, brave_provider.py, ddg_html_provider.py, ddgs_provider.py, wiki_provider.py
- Each implements async search() method
- brave_provider.py also defines SearXNGProvider class

### src/engine/extract/extractor.py
- DocumentExtractor class — 233 lines
- ExtractedDocument dataclass with passages, metadata, tokens_used, latency
- Pipeline: security check → HTTP fetch → PDF/HTML extraction → sanitize → chunk → BM25 score
- HTML: Trafilatura primary, BeautifulSoup fallback, headless browser SPA fallback
- PDF: PyMuPDF (fitz)
- Token-aware full-text mode with truncation

### src/engine/extract/chunker.py
- DocumentChunker — target_tokens=180, overlap_tokens=30

### src/engine/extract/passage_scorer.py
- BM25PassageScorer — query-aware passage ranking
- ScoredPassage dataclass with text, token_count, char_start, char_end

### src/engine/extract/browser_fallback.py
- fetch_rendered_dom() — headless browser for JavaScript SPAs

### src/engine/crawl/crawler.py
- WebsiteCrawler — depth-controlled, robots-compliant, cycle-safe crawl
- Semaphore(2) for polite concurrency
- **BUG:** Double-fetches pages — extract_url fetches content, then safe_fetch_url again just for link extraction
- is_trap_url() — detects cyclic directories, infinite calendars

### src/engine/crawl/mapper.py
- WebsiteMapper — sitemap XML parsing + seed link extraction
- Domain confinement, limit enforcement

### src/engine/crawl/robots.py
- RobotsManager — robots.txt compliance, sitemap discovery

### src/engine/research/deep_research.py
- DeepResearchEngine — multi-query research loop
- generate_sub_queries() — creates up to 3 sub-queries from question
- Cross-source evidence gathering, contradiction detection (year divergence)
- SourcedFact, ResearchReport dataclasses

### src/engine/security.py
- SSRF protection: BLOCKED_NETWORKS (RFC 1918, loopback, link-local, metadata, multicast, reserved)
- validate_url_security() — scheme check, hostname check, DNS resolution, IP blocking
- sanitize_untrusted_content() — zero-width char removal, control char removal, prompt injection flagging
- **BUG:** Missing many injection patterns (see test failures)
- safe_fetch_url() — streaming fetch with byte limits, redirect revalidation, per-request SSRF checks
- get_user_agent_for_url() — domain-appropriate User-Agent (Wikipedia gets custom UA)

## Duplicated Implementations

### Package duplication
| Package | Files | Status |
|---|---|---|
| src/ | 53 | ACTIVE (pyproject entry point) |
| weblens/src/weblens/ | 36 | DUPLICATE (standalone, v0.1.0) |
| webintel/ | 19 | DUPLICATE (standalone) |

### Security duplication
| Module | Implementation | Status |
|---|---|---|
| src/engine/security.py | httpx + socket.getaddrinfo + BLOCKED_NETWORKS list | ACTIVE |
| src/weblens/net/ssrf.py | httpcore AnyIOBackend + DestinationPolicy + anyio | DUPLICATE |
| src/weblens/security/injection.py | scan_injection() + has_instruction_smuggling() | DUPLICATE (different patterns) |

## Known Issues (from baseline testing)

1. **Prompt injection sanitization incomplete** — 10 patterns not detected (exfiltration, concealment, role hijack, encoded payload)
2. **Crawler double-fetch** — wasteful second HTTP request per page
3. **SearchAggregator God object** — 260 lines, multiple responsibilities
4. **No lint/format/type config** — no ruff, black, mypy, flake8
5. **MCP parameter validation errors** — surface as unhandled ToolError exceptions
6. **Crawler trap detection** — misses consecutive identical path segments
7. **Token budget boundary** — "capital of France" exceeds search token budget
8. **Answer support rate 40%** — below 60% target
9. **False confidence rate 20%** — above 15% target
