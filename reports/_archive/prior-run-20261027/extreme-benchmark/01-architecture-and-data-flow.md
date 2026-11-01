# 01 — Architecture, Component Boundaries, and Data Flow

**Document ID:** `reports/extreme-benchmark/01-architecture-and-data-flow.md`  
**Execution Date:** 2026-10-27  
**Auditor Mode:** Principal Systems Architect & Distributed-Systems Reliability Engineer  
**Classification:** STRICT AUDIT EVIDENCE — TECHNICAL ARCHITECTURE  

---

## 1. System Architectures Under Test

The repository contains two distinct architectural stacks sharing design philosophy but maintaining independent codebases:

### 1.1 WebIntel Engine (`src/engine/` + `src/server/`)
- **Design Philosophy:** Local-first, token-budgeted intelligence engine specifically tuned for MCP agent tool use.
- **Entry Points:**
  - `web-intel-mcp` (`src.server.mcp_server:main`): Streamable HTTP and stdio MCP server exposing 5 tools (`web_search`, `extract_url`, `crawl_website`, `web_map`, `deep_research`).
  - `web-intel-bench` (`benchmarks.run_benchmarks:main`): High-precision benchmarking CLI.
- **Search Layer (`src/engine/search/`):**
  - `SearchAggregator`: Fuses results from DuckDuckGo (`ddgs` / HTML scraper), Wikipedia REST API, and Bing HTML fallback. Enforces exact serialized token budgets using `o200k_base` tiktoken encoding.
  - `TavilySearchProvider`: Optional commercial search adapter enabled when `TAVILY_API_KEY` is present.
- **Extraction Layer (`src/engine/extract/`):**
  - `DocumentExtractor`: Trafilatura-backed content extraction, BM25 passage scoring (`BM25PassageScorer`), and chunking (`DocumentChunker`).
  - `browser_fallback.py`: Native Windows CLI fallback executing `msedge.exe` or `chrome.exe` with `--headless=new --dump-dom`.
- **Defensive Layer (`src/engine/security.py`):**
  - Pre-connect DNS resolution and IP verification against `BLOCKED_NETWORKS` (RFC 1918, loopback, CGNAT, cloud metadata `169.254.169.254`).
  - `sanitize_untrusted_content()`: Strips instruction overrides, role hijacks, and prompt exfiltration vectors.

### 1.2 WebLens Core Package (`weblens/src/weblens/`)
- **Design Philosophy:** Modular, policy-driven web intelligence library with strict network security controls.
- **Entry Points:**
  - `weblens` CLI (`weblens.cli:main`): CLI supporting `search`, `extract`, `crawl`, `research`, `serve`, `cache`.
  - `weblens.mcp_server`: Fast tools-only MCP server exposing 4 compact tools (`web_search`, `extract_url`, `crawl_site`, `deep_research`).
- **Network & Egress Layer (`weblens/src/weblens/net/`):**
  - `DestinationPolicy`: Connection-time destination resolution and allowlist/denylist verification.
  - `SafeNetworkBackend`: Custom `httpcore` backend pinning outbound TCP connections to validated IPs.
  - `BrowserEgressProxy`: Ephemeral HTTP loopback proxy launched alongside Playwright to enforce destination policies on all browser traffic and subresources.
- **Cache Subsystem (`weblens/src/weblens/cache.py`):**
  - SQLite database in WAL mode with TTL expiration, gzip compression, and logical size cap enforcement (`cache_max_bytes`).

### 1.3 Tavily Direct API Architecture
- **Endpoint:** `https://api.tavily.com/search`
- **Model:** Commercial SaaS search index with proprietary query expansion, scraping, and raw snippet extraction.
- **Response Shape:** Full unstructured text snippets (mean ~1,302 tokens per 5 results) with URL, title, and optional AI answer.

---

## 2. End-to-End Data Flow

### 2.1 Search Execution Flow
```
User / Agent Query
        │
        ▼
[MCP Server: web_search]
        │ Validate schema: query (str), count (int), max_tokens (int)
        ▼
[Search Router / Aggregator]
        │
        ├────────────────────────┬────────────────────────┐
        ▼                        ▼                        ▼
 [DuckDuckGo / DDGS]     [Wikipedia REST]        [Bing Scraper]
        │                        │                        │
        └────────────────────────┼────────────────────────┘
                                 ▼
                    [Result Deduplication & Ranking]
                                 │ Domain diversity filter & authoritative boost
                                 ▼
                    [Token Budget Truncation]
                                 │ Real JSON measurement via tiktoken o200k_base
                                 ▼
                    [Structured SearchResponse]
                                 │ Compact JSON with passages & source citations
                                 ▼
                          Caller / Agent
```

### 2.2 Extraction & Browser Routing Flow
```
URL to Extract
        │
        ▼
[Destination Security Check] ──(Disallowed IP/Scheme)──► Return Blocked Status
        │ Safe Public Host
        ▼
[Cache Lookup] ────────────────(Cache Hit & Valid TTL)──► Return Cached Content
        │ Cache Miss
        ▼
[Direct HTTP Request via SafeFetcher]
        │
        ├─► Success & Content > 200 chars ──► [Trafilatura / LXML Parse]
        │                                             │
        │                                             ▼
        │                                     [BM25 Passage Slicing]
        │                                             │
        │                                             ▼
        │                                     [Injection Sanitization]
        │                                             │
        │                                             ▼
        │                                     [Store in SQLite Cache]
        │                                             │
        │                                             ▼
        │                                     Return Extracted Passages
        │
        └─► Blank / Incomplete Content (SPA)
                    │
                    ▼
         [Adaptive Browser Routing]
                    │
                    ├─► [weblens: Playwright + BrowserEgressProxy] (Pinned DNS Proxy)
                    │
                    └─► [engine: msedge.exe --dump-dom] (Unproxied Subprocess)
```

---

## 3. Boundary Comparison: WebLens vs Tavily

| Architectural Dimension | Tavily Direct API | WebLens Keyless | WebLens (Tavily-Backed) |
|---|---|---|---|
| **Execution Model** | Remote SaaS | Localhost / Embedded | Localhost with Remote Upstream |
| **API Cost** | $8.00 / 1k tasks | **$0.00** | $8.00 / 1k tasks |
| **Search Latency (p50)** | **1.06s - 1.82s** | 1.28s - 2.87s | 1.35s - 2.10s |
| **Snippet Payload Size** | 1,048 - 1,600 tokens | **41 - 407 tokens (18x reduction)** | 71 tokens (Filtered) |
| **Privacy & Egress Control** | Third-party proxy | Strict local DestinationPolicy | Local egress + API payload |
| **JavaScript Rendering** | Server-side proprietary | Playwright + Local Egress Proxy | Playwright / CLI fallback |
| **Offline / Airgap Capable** | No | **Yes (Wikipedia/Local mirrors)** | No |
| **MCP Conformance** | Proprietary wrapper | **Streamable HTTP + stdio native** | Streamable HTTP + stdio native |
