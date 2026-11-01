# WebLens Architecture Audit

## 1. System Overview
WebLens is a local-first, evidence-first web intelligence and research platform designed for AI agents via the Model Context Protocol (MCP) and Python API. Unlike traditional web retrieval wrappers that pass unverified, truncated snippets to an LLM, WebLens enforces strict data/instruction separation, cryptographic source provenance, lexical passage scoring, local SQLite caching, and defensive egress control.

The codebase comprises two stacks:
1. **Primary Subject (`weblens/src/weblens` / `src/weblens`):** The clean, hardened, modular package powering the MCP server, search router, extraction service, site crawler, deep research engine, and browser proxy.
2. **Secondary Subject (`src/engine` / WebIntel):** The legacy root retrieval engine containing multi-provider aggregators, BM25 chunkers, and exploratory search providers.

---

## 2. Core Subsystems

```
                               +-------------------------------------+
                               |         AI Agent Client / CLI       |
                               +-------------------------------------+
                                                  |
                                                  v
                               +-------------------------------------+
                               |          MCP Server / API           |
                               |  Profiles: core, research, full     |
                               +-------------------------------------+
                                                  |
                   +------------------------------+------------------------------+
                   |                              |                              |
                   v                              v                              v
        +--------------------+         +--------------------+         +--------------------+
        |    SearchRouter    |         | ExtractionService  |         |    SiteCrawler     |
        +--------------------+         +--------------------+         +--------------------+
                   |                              |                              |
                   +------------------------------+------------------------------+
                                                  |
                                                  v
                               +-------------------------------------+
                               |             SafeFetcher             |
                               +-------------------------------------+
                                        |                   |
                                        v                   v
                             +--------------------+  +--------------------+
                             | DestinationPolicy  |  |   SQLite Cache     |
                             |  (SSRF / Egress)   |  |   (TTL / SHA-256)  |
                             +--------------------+  +--------------------+
```

### 2.1 Networking & SSRF Security (`weblens.net`)
- **`DestinationPolicy` (`weblens.net.ssrf`):** Enforces strict IP classification against IPv4 and IPv6 address spaces. Disallows loopback (`127.0.0.0/8`, `::1`), private ranges (RFC 1918 `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, RFC 4193 `fc00::/7`), link-local (`169.254.0.0/16`, `fe80::/10`), cloud metadata (`169.254.169.254`), broadcast, and multicast.
- **DNS Pinning:** Resolves target hostnames at socket connection time before issuing requests, preventing DNS rebinding TOCTOU attacks.
- **Redirect Validation:** Inspects every hop in an HTTP redirect chain through `DestinationPolicy`, blocking redirect-based SSRF.
- **Safe Transport (`SafeFetcher`):** Wraps `httpx.AsyncClient` with pooled connections, explicit connect/read/write deadlines (default 10s), user-agent rotation, and automatic caching.

### 2.2 Search Router & Multi-Provider Aggregation (`weblens.search`)
- **Provider Registry:**
  - `DuckDuckGoProvider`: Keyless HTML scraping with zero external credentials required.
  - `WikipediaProvider`: Keyless MediaWiki REST API querying encyclopedic ground truth.
  - `BraveSearchProvider`: API-key backed commercial index via Brave Search Data API.
  - `TavilySearchProvider`: API-key backed commercial retrieval and extraction API.
  - `SearXNGProvider`: Self-hosted meta-search engine proxying multiple engines (currently `http://localhost:8080`).
  - `BingProvider`: Keyless fallback scraping.
- **Ranking & Normalization:** Normalized result deduplication across URL canonicalization rules; reciprocal rank fusion (RRF) and lexical token overlap scoring.
- **Token Budgeting:** Strictly trims results to fit within caller-specified token limits (120 to 2,000 tokens) using `tiktoken` (`cl100k_base`).

### 2.3 Extraction & Passage Scoring (`weblens.extract`)
- **HTML Parsing & Normalization:** `lxml` and `trafilatura` extract main article text, headers, and code blocks while stripping navigation, advertisements, boilerplate, and scripts.
- **Passage Chunking:** Breaks documents into semantic sentences and paragraph chunks (100–300 tokens) with 20% overlap.
- **Lexical Passage Scoring (`select_passages`):** Computes BM25/TF-IDF token affinity between user queries and extracted chunks, prioritizing exact keyword matches and structural headings.
- **PDF Extraction:** Built-in `pymupdf` (fitz) integration parses text from local and remote PDF documents without calling external microservices.
- **Browser Fallback (`browser.py`):** Optional Playwright headless Chromium integration with egress proxy routing for single-page applications (SPAs) requiring JavaScript execution.

### 2.4 Bounded Site Crawler (`weblens.crawl`)
- **Polite Crawling (`crawler.py`, `robots.py`):** Parses and strictly obeys `robots.txt` per host; respects `Crawl-Delay` and rate limits requests to max 1 req/sec per domain.
- **Trap Avoidance:** Rejects calendar loops, infinite query strings, deep directory recursion (>3 hops), and non-text binary extensions.
- **Site Mapping:** High-speed URL tree discovery mode returning hierarchical endpoint maps without full payload downloads.

### 2.5 Deterministic Deep Research Engine (`weblens.research`)
- **Query Decomposition:** Dissects complex, ambiguous user research queries into 2 to 4 orthogonal sub-queries.
- **Verbatim Evidence Extraction:** Collects exact text spans with URL, retrieval timestamp, and character offset spans.
- **Safety & Refusal Guard (`evidence_guard`):** Rejects fictional entity queries, ungrounded speculation, proprietary source code queries, and leaks of private credentials.
- **Contradiction Detection:** Evaluates competing claims across independent domains and flags numerical or chronological disputes instead of picking a winner arbitrarily.

### 2.6 Persistence & Cache Architecture (`weblens.cache`)
- **Local SQLite Store:** Key-value store indexed by SHA-256 of canonical HTTP request parameters and normalized URLs.
- **TTL Expiration:** Configurable cache lifetime (default 3600 seconds) preventing stale retrieval while minimizing redundant provider spend.

### 2.7 Model Context Protocol (MCP) Surface (`weblens.mcp_server`)
- Exposes clean tools with JSON schema annotations: `web_search`, `extract_url`, `crawl_site`, `deep_research`.
- Measured schema size: 732 `cl100k_base` tokens (comfortably below the 1,000 token pre-registered budget).

---

## 3. Technology Stack & Runtime Dependencies
- **Runtime:** Python 3.11+ (verified on Python 3.14.0 Windows AMD64).
- **Core Libraries:** `mcp>=2.3.0`, `httpx>=0.28.1`, `pydantic>=2.13.0`, `trafilatura>=2.3.0`, `lxml>=6.1.0`, `pymupdf>=1.28.0`, `tiktoken>=0.14.0`.
- **Optional Components:** Playwright Chromium (browser rendering), SearXNG (local Docker instance).
