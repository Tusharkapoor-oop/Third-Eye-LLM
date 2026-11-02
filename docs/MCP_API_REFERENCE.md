# WebLens Model Context Protocol (MCP) & API Reference

## 1. Protocol Architecture & Transports

WebLens exposes its capabilities to downstream AI agents through the Model Context Protocol (MCP) using two standard transports:
1. **Stdio Transport:** Standard input/output pipe for direct integration into local desktop agents, Claude Desktop, Cursor, Cline, and Roo Code.
2. **HTTP/SSE Transport:** Server-Sent Events over HTTP for networked, containerized, and cloud deployments (e.g. Google Cloud Run).

### Endpoint Specifications
- **Local MCP Endpoint:** `http://127.0.0.1:50301/mcp`
- **Cloud Run Remote Endpoint:** `https://weblens-16131012091.us-central1.run.app/mcp`
- **Profiles:**
  - `core`: Exposes essential retrieval tools (`web_search`, `extract_url`, `crawl_site`, `deep_research`).
  - `full`: Exposes all 13 core and specialized application tools.

---

## 2. Core Retrieval Tools

### 2.1 `web_search`
Dispatches multi-provider web discovery with consensus ranking and domain authority scoring.
- **Inputs:**
  - `query` (string, required): Clean search query.
  - `max_results` (integer, default: 5): Maximum candidate URLs to return (1-20).
  - `engines` (string, optional): Comma-separated search engines (e.g. `"ddg,bing,wikipedia"`).
- **Response Format:**
  ```json
  {
    "status": "ok",
    "query": "PostgreSQL vs MySQL",
    "results_count": 5,
    "res": [
      {
        "t": "PostgreSQL vs MySQL: 2026 Comparison",
        "u": "https://example.org/db-comparison",
        "s": "Key architectural differences between Postgres and MySQL...",
        "e": "bing",
        "r": 1
      }
    ],
    "ms": 482
  }
  ```

### 2.2 `extract_url`
Fetches and declutters a target URL, stripping boilerplate and extracting clean text and markdown tables.
- **Inputs:**
  - `url` (string, required): Target public URL (must pass SSRF DestinationPolicy).
  - `max_chars` (integer, default: 12000): Maximum character cutoff.
  - `enable_images` (boolean, default: false): Extract image metadata.
- **Response Format:**
  ```json
  {
    "status": "ok",
    "url": "https://example.org/article",
    "title": "Article Title",
    "text": "Extracted main article body markdown...",
    "sha256": "8a3b5c...",
    "char_count": 3420,
    "ms": 310
  }
  ```

### 2.3 `crawl_site`
Bouded domain graph traversal resistant to infinite calendar and recursion traps.
- **Inputs:**
  - `url` (string, required): Seed URL.
  - `max_pages` (integer, default: 10, max: 30): Page limit.
  - `max_depth` (integer, default: 2, max: 3): Link hop depth.
  - `extract` (boolean, default: true): Extract text from visited pages.
- **Response Format:**
  ```json
  {
    "status": "ok",
    "seed_url": "https://example.org",
    "pages_visited": 8,
    "pages": [
      {
        "url": "https://example.org/about",
        "title": "About Us",
        "char_count": 1820
      }
    ],
    "ms": 1420
  }
  ```

### 2.4 `deep_research`
Multi-hop query decomposition, evidence retrieval, and verbatim citation synthesis.
- **Inputs:**
  - `query` (string, required): Research question.
  - `max_searches` (integer, default: 4, max: 6): Maximum decomposed search queries.
  - `max_tokens` (integer, default: 3000, max: 8000): Token budget for evidence.
- **Response Format:**
  ```json
  {
    "status": "ok",
    "query": "Quantum computing qubit coherence times 2026",
    "sub_queries": ["superconducting qubit coherence 2026", "trapped ion coherence 2026"],
    "findings": [
      {
        "claim": "Trapped ion coherence times exceeded 100 seconds.",
        "url": "https://nature.com/articles/example",
        "verbatim_span": "demonstrating coherence exceeding 100 s in 2026",
        "char_start": 412,
        "char_end": 458
      }
    ],
    "confidence": 0.94,
    "ms": 2840
  }
  ```

---

## 3. Specialized Application Tools (`profile="full"`)

### 3.1 `company_research`
Generates structured corporate intelligence profiles.
- **Inputs:** `name` (string, required): Company or organization name.
- **Output:** Detected official domain, leadership team, products, competitors, and business challenges.

### 3.2 `market_research`
Financial disclosures, stock statistics, and corporate filings.
- **Inputs:** `symbol_or_topic` (string, required): Ticker (e.g. `AAPL`) or market sector.
- **Output:** Verified trading metrics, financial statements, and regulatory citations.

### 3.3 `crawl2rag_index` & `crawl2rag_query`
Builds and searches local SQLite FTS5 / BM25 knowledge bases from crawled sites.
- **`crawl2rag_index`:** `url` (string), `kb_id` (string), `max_pages` (integer).
- **`crawl2rag_query`:** `kb_id` (string), `query` (string), `top_k` (integer).

### 3.4 `sheets_enrich`
Enriches tabular datasets row-by-row with formula injection sanitization.
- **Inputs:** `columns` (list of strings), `rows` (list of dicts), `instructions` (string).

### 3.5 `meeting_prep`
Public executive briefings from calendar events.
- **Inputs:** `calendar_or_title` (string), `attendee_names` (optional list of strings).

### 3.6 `research_chat`
Multi-turn conversational research session with memory budgeting.
- **Inputs:** `message` (string), `session_id` (optional string).

### 3.7 `tutorial_101`
Interactive runnable tutorials for developer onboarding.
- **Inputs:** `topic` (string, e.g. `"overview"`, `"search"`, `"mcp"`).

---

## 4. Standard Error Codes & Handling

WebLens MCP returns JSON-RPC 2.0 compliant errors:

| Error Code | Constant | Meaning | Remediation |
|---|---|---|---|
| `-32602` | `INVALID_PARAMS` | Input validation failed | Ensure required fields are non-empty and within bounds. |
| `-32001` | `SSRF_BLOCKED` | Target IP is private/loopback | Provide a publicly routable Internet hostname or IP. |
| `-32002` | `TIMEOUT_EXCEEDED` | Upstream fetch timed out | Downstream agent should retry or inspect site availability. |
| `-32003` | `CRAWL_TRAP_ABORTED` | Recursive trap detected | Crawl terminated safely to prevent resource exhaustion. |
| `-32004` | `NO_RELIABLE_RESULT` | Query premise unverified/fictional | Query refers to false premise; treat as non-existent entity. |

