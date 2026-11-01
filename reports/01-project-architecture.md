# 01 — Project Architecture & Component Map

**Document ID:** `reports/01-project-architecture.md`  
**Date:** 2026-10-24  
**Auditor:** Independent Benchmark Scientist & Evaluation Lead  
**Commit:** `b531618`  
**Operating System:** Windows 11 Home Single Language (Build 26300)

---

## 1. System Overview & Dual-Stack Architecture

The repository contains two parallel, mature implementations of a local-first, token-efficient web intelligence engine for AI agents via the Model Context Protocol (MCP):

1. **Stack A: WebIntel (`src/engine/` + `src/server/`)**
   - Pure Python / Starlette implementation.
   - MCP Server registered via `mcp.server.mcpserver.MCPServer` exposing 5 tools (`web_search`, `extract_url`, `crawl_website`, `web_map`, `deep_research`).
   - Token budgeting calculated using `tiktoken` with `o200k_base` and `cl100k_base`.
   - Dual output serialization (`content` for legacy LLM clients + `structured_content` for modern MCP clients).
   - Headless Edge/Chrome CLI DOM dump fallback for single-page applications.

2. **Stack B: WebLens (`weblens/` & `src/weblens/`)**
   - High-assurance, strict-boundary implementation with Pydantic Settings.
   - MCP Server registered via `mcp.server.fastmcp.FastMCP` exposing 4 tools (`web_search`, `extract_url`, `crawl_site`, `deep_research`).
   - SQLite content caching with TTL management.
   - Optional Playwright browser proxy for dynamic JavaScript rendering.
   - Dedicated CLI diagnostic and token measurement subcommands (`weblens doctor`, `weblens tokens`).

---

## 2. High-Level Architecture Diagram

```
                 MCP Client (Claude Desktop / Roo Code / Cline / Continue / VS Code)
                                              │
                         ┌────────────────────┴────────────────────┐
                         │   JSON-RPC over STDIO or HTTP/Stream    │
                         ▼                                         ▼
         ┌───────────────────────────────┐         ┌───────────────────────────────┐
         │     Stack A: WebIntel MCP     │         │      Stack B: WebLens MCP     │
         │     `src.server.mcp_server`   │         │    `weblens.mcp_server`       │
         │  (5 Tools: search, extract,   │         │ (4 Tools: search, extract,    │
         │   crawl, map, deep_research)  │         │  crawl_site, deep_research)   │
         └───────────────┬───────────────┘         └───────────────┬───────────────┘
                         │                                         │
        ┌────────────────┴─────────────────────────────────────────┴────────────────┐
        │                                                                           │
        ▼                                                                           ▼
┌─────────────────────────────────┐                       ┌─────────────────────────────────┐
│     Search Routing Pipeline     │                       │   Content Extraction Pipeline   │
│ - DDGS (DuckDuckGo API)         │                       │ - Trafilatura (91.3% F1 Recall) │
│ - Wikipedia REST API (v1)       │                       │ - BeautifulSoup4 Boilerplate    │
│ - Bing HTML + Redirect Decoder  │                       │ - PyMuPDF (PDF Parser)          │
│ - Tavily Provider (Optional)    │                       │ - Browser Fallback (Edge/Chrome)│
│ - Brave / SearXNG (Optional)    │                       │ - BM25 Lexical Passage Scorer   │
└────────────────┬────────────────┘                       └────────────────┬────────────────┘
                 │                                                         │
                 ▼                                                         ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                           Security & Grounding Gateway                            │
│ - SSRF IP Resolution & CIDR Blacklisting (Private RFC1918, Loopback, Cloud Meta) │
│ - Prompt Injection Scanner (Hidden Delimiters, Role Hijacking, Invisible Unicode) │
│ - Token Budget Enforcer (Exact JSON Token Counting with Snippet Truncation)       │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Deep Dive

### 3.1 Search Routing & Fallback Chain
- **Location:** `src/engine/search/aggregator.py` & `src/weblens/search/router.py`
- **Execution Flow:**
  1. Input query is normalized; punctuation and tracking query parameters (`utm_*`, `gclid`, `fbclid`) are stripped.
  2. Queries primary engine (default: DuckDuckGo).
  3. If primary fails, times out (<3.5s), or returns empty/low relevance, automatically queries fallback engines (Bing HTML or Wikipedia REST).
  4. Deduplicates results by normalized URL and canonical title.
  5. Enforces domain diversity (maximum 2 results per domain).
  6. Calculates exact JSON serialized token count; dynamic backpressure trims snippet lengths to guarantee `response_tokens <= default_search_tokens` (600 tokens).

### 3.2 Document Extraction & Grounding
- **Location:** `src/engine/extract/extractor.py` & `src/weblens/extract/service.py`
- **Execution Flow:**
  1. Validates destination safety against SSRF rules before opening socket connection.
  2. Issues HTTP GET request with HTTP/2 and 5MB streaming byte cap.
  3. Detects content type:
     - PDF: Passes raw stream to `PyMuPDF` (`fitz`) for text layer extraction.
     - HTML: Passes raw HTML to `trafilatura` for primary article text extraction.
  4. SPA Detection: If extracted text is under 200 characters and contains SPA indicators (`<div id="root">`, `<div id="app">`), activates headless browser fallback (`msedge.exe --headless --dump-dom`).
  5. Passage Chunker: Splits document into 180-token chunks with 30-token overlapping strides.
  6. BM25 Scorer: Okapi BM25 (`k1=1.5`, `b=0.75`) scores passages against the query, assigning verifiable exact character offsets (`char_start`, `char_end`).

### 3.3 Autonomous Deep Research Engine
- **Location:** `src/engine/research/deep_research.py` & `src/weblens/research/engine.py`
- **Execution Flow:**
  1. Decomposes the user's research query into 3 distinct investigative sub-queries (factual, technical, comparative).
  2. Executes parallel searches across providers, accumulating candidate URLs.
  3. Concurrently extracts top candidate pages.
  4. Allocates a strict 70% token budget for extracted evidence facts (`facts_token_budget`).
  5. Detects chronological divergence across sources (tracking disparate publication years).
  6. Generates structured synthesis and enforces total JSON serialization bounds before returning.

### 3.4 Security & SSRF Defense Layer
- **Location:** `src/engine/security.py` & `src/weblens/net/ssrf.py`
- **Defenses:**
  - Connect-time DNS resolution verifying all resolved IPv4 and IPv6 addresses against private/loopback/cloud-metadata CIDRs.
  - Port whitelisting: restricted strictly to ports 80, 443, 8080, and 8443.
  - Null byte (`\x00`) and URI userinfo (`user:pass@`) rejection.
  - Redirect loop protection (max 5 redirects) with per-hop IP validation.
  - Indirect prompt injection detection targeting delimiters, system override commands, and zero-width invisible unicode.

---

## 4. Configuration Matrix

Configuration is fully decoupled from code and controlled via environment variables:

| Variable | Default Value | Description |
|---|---|---|
| `DEFAULT_SEARCH_PROVIDER` | `ddgs` | Primary provider (`ddgs`, `brave`, `searxng`, `tavily`, `wikipedia`) |
| `DEFAULT_SEARCH_TOKEN_BUDGET` | `600` | Hard token ceiling for search results |
| `DEFAULT_EXTRACT_TOKEN_BUDGET` | `1200` | Hard token ceiling for extracted page passages |
| `DEFAULT_DEEP_RESEARCH_TOKEN_BUDGET` | `2000` | Hard token ceiling for deep research reports |
| `HTTP_CONNECT_TIMEOUT_SECONDS` | `8.0` | Socket connection timeout |
| `HTTP_READ_TIMEOUT_SECONDS` | `12.0` | Streaming HTTP read timeout |
| `MAX_HTTP_RESPONSE_BYTES` | `5242880` | Maximum allowable payload size (5 MB) |
| `ENABLE_BROWSER_FALLBACK` | `true` | Headless browser execution for SPA pages |
