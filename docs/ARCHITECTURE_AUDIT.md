# WebLens Architecture Audit

## 1. System Overview

WebLens is an asynchronous, evidence-grounded web intelligence platform developed in Python 3.11+. It operates as both an MCP (Model Context Protocol) server over stdio and HTTP/SSE, and as a Python library.

The platform architecture enforces strict decoupling between retrieval infrastructure and downstream agent reasoning. Untrusted web content is safely ingested, sanitized, cached, and indexed before structured passages with exact character spans are returned to the caller.

---

## 2. Component Architecture

```
                             +----------------------------------------+
                             |    Downstream AI Agent / MCP Client    |
                             +----------------------------------------+
                                                 |
                                     JSON-RPC 2.0 / MCP Stream
                                                 |
                                                 v
                             +----------------------------------------+
                             |          WebLens MCP Server            |
                             |      (FastMCP / starlette / SSE)       |
                             +----------------------------------------+
                                                 |
                  +------------------------------+------------------------------+
                  |                              |                              |
                  v                              v                              v
       +--------------------+         +--------------------+         +--------------------+
       |    SearchRouter    |         | ExtractionService  |         |    SiteCrawler     |
       |  (Consensus Rank)  |         | (Trafilatura/LXML) |         | (Trap-Proof Graph) |
       +--------------------+         +--------------------+         +--------------------+
                  |                              |                              |
                  +------------------------------+------------------------------+
                                                 |
                                                 v
                               +-----------------------------------+
                               |       SafeFetcher / Engine        |
                               +-----------------------------------+
                                        |                 |
                       +----------------+                 +----------------+
                       |                                                   |
                       v                                                   v
         +----------------------------+                      +----------------------------+
         |    DestinationPolicy       |                      |     SQLite Cache Store     |
         | (SSRF & DNS Pinning Guard) |                      | (TTL, SHA-256 Provenance)  |
         +----------------------------+                      +----------------------------+
```

---

## 3. Subsystem Breakdown

### 3.1 Search Router (`weblens.search.router`)
- **Multi-Provider Dispatch:** Coordinates queries across DuckDuckGo, Bing, Wikipedia, Mojeek, and Mwmbl. Commercial providers (Tavily, Brave) are supported via optional configuration.
- **Query Rewriting & Normalization:** Strips conversational prefixes (`who is`, `what is`, `can you tell me`) and normalizes relational expressions (`differences between X and Y` -> `X and Y`).
- **Domain Whitelist & Authority Weighting:** Institutional domains (`.gov`, `.edu`, `.org`, `wikipedia.org`, `un.org`, `worldbank.org`) receive authority score multipliers during ranking.
- **Consensus & De-duplication:** Deduplicates hits across providers using registrable domain and canonicalized URL pathing.

### 3.2 Content Extraction Service (`weblens.extract`)
- **Structural Text Extraction:** Powered by `trafilatura` and `lxml`, isolating article body from navbars, footers, headers, and advertising frames.
- **Table & Code Preservation:** Converts HTML tabular data (`<table>`, `<tr>`, `<td>`) into standard Markdown tables; preserves code fences and preformatted text blocks.
- **Sentence & Passage Chunking:** Splits long articles into overlapping lexical passages (128-token boundary overlap) with exact character start/end offsets.

### 3.3 Site Crawler (`weblens.crawl.crawler`)
- **Trap Defense Engine:** Identifies and aborts calendar loops (`/YYYY/MM/DD/`), infinite query session parameters (`?sid=`, `?session=`), and directory recursion mirrors (`/docs/docs/docs/`).
- **Resource Boundaries:** Hard ceiling of 30 pages, depth <= 3 hops, and minimum 1.0s inter-request rate limiting per target domain.
- **Robots.txt Adherence:** Parses and respects `robots.txt` disallow rules and crawl-delay directives.

### 3.4 Deep Research & Knowledge Applications (`weblens.research`, `weblens.apps`)
- **Query Decomposition:** Breaks broad research queries into 2 to 6 focused sub-searches.
- **Verbatim Evidence Verification:** Extracts verbatim text spans directly from fetched HTML to substantiate claims.
- **Vertical Application Engines:**
  - `CompanyResearcher`: Generates structured profiles (leadership, products, competitors, risks) with detected official domain validation.
  - `MarketResearcher`: Gathers financial metrics, trading statistics, and analyst disclosures with zero-fabrication guard.
  - `Crawl2RAG`: Crawls target documentation sites, chunks content, and builds local SQLite FTS5 / BM25 search indices.
  - `SheetsEnricher`: Asynchronously enriches CSV/XLSX tabular datasets with formula injection sanitization.
  - `MeetingPreparer`: Gathers public executive profiles and background briefs with strict personal data refusal.

### 3.5 Network & Transport Security (`weblens.net`)
- **SSRF Prevention:** `DestinationPolicy` inspects all target IP addresses against RFC 1918, RFC 3927, RFC 4193, RFC 4291, and RFC 6890 private/loopback/link-local ranges.
- **DNS Resolution Pinning:** Resolves target hostnames prior to socket establishment, preventing DNS rebinding time-of-check-time-of-use (TOCTOU) exploits.
- **Redirect Tracking:** Validates each hop in 30x redirect chains against `DestinationPolicy`.

### 3.6 Security Scanner (`weblens.security.injection`)
- **Prompt Injection Defense:** Regex scanner detects prompt injection patterns (`ignore previous instructions`, `system override`, `exfiltrate credentials`, canary token probes).
- **Quarantine Payload:** Identified hostile patterns are flagged and encapsulated into inert JSON data structures, preventing instruction hijacking in the downstream agent.

---

## 4. Architectural Invariants

1. **No External Paid Key Requirement:** Local WebLens must remain 100% functional using keyless search providers and local extraction without requiring paid API keys.
2. **Deterministic Provenance:** Every returned passage must include URL, fetch timestamp, HTTP status, and SHA-256 hash of the retrieved document.
3. **Strict Egress Validation:** No HTTP request may be dispatched to private, loopback, or metadata addresses under any circumstance.
4. **Idempotent Caching:** Identical requests within TTL serve cached content with explicit `cached: true` flags, preventing redundant bandwidth and network egress.

---

## 5. Failure Modes & Mitigations

| Failure Mode | Impact | Mitigation Mechanism |
|---|---|---|
| Provider Rate Limit (e.g. DDG 429) | Search queries fail | Automatic fallback to next provider in configured priority chain (Bing -> Wikipedia -> Mwmbl). |
| Network Timeout / Egress Block | Tool execution hangs | Enforced per-request deadline (default 10s connect/read), returning structured error payload. |
| Malformed HTML / Parser Crash | Extraction fails | Multi-engine fallback: `trafilatura` -> `lxml.html` -> regex strip tags. |
| Infinite Crawl Trap | Memory / CPU exhaustion | Visited URL canonical hash set, max depth=3, max pages=30, trap regex filters. |
| Upstream DNS Rebinding Probe | SSRF exploit attempt | Resolved IP pinning before socket connect; reject if resolved IP is non-public. |

