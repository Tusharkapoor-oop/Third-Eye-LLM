# WebLens Model Context Protocol (MCP) & API Reference

## 1. Protocol Architecture & Transports

WebLens exposes its capabilities to downstream AI agents through the Model Context Protocol (MCP) using two standard transports:
1. **Stdio Transport:** Standard input/output pipe for direct integration into local desktop agents, Claude Desktop, Cursor, Cline, and Roo Code.
2. **HTTP/SSE Transport:** Server-Sent Events over HTTP for networked, containerized, and cloud deployments.

### Endpoint Specifications
- **Local MCP Endpoint (illustrative):** `http://127.0.0.1:50301/mcp` — the actual host/port depend on CLI flags.
- **Cloud Run Remote Endpoint (illustrative):** configured by the operator at deploy time.
- **Profiles:**
  - `core`: Exposes essential retrieval tools (`web_search`, `extract_url`, `crawl_site`, `deep_research`).
  - `research`: Adds `evidence_synthesis`, `company_research`, `market_research` and `market_portfolio`.
  - `full`: Exposes all core and specialized application tools.

All responses are compact JSON strings. Field names are shortened (`q` for query, `u` for URL, `s` for span, etc.) to keep token budgets small.

---

## 2. Core Retrieval Tools

### 2.1 `web_search`
Dispatches multi-provider web discovery with consensus ranking and domain authority scoring.
- **Inputs:**
  - `query` (string, required): Clean search query.
  - `max_results` (integer, 1-10, default: 5): Maximum results to return.
  - `freshness` (string, optional): `day`, `week`, `month` or `year`.
  - `domains` (list of strings, optional): Restrict results to these domains.
  - `exclude_domains` (list of strings, optional): Exclude these domains.
  - `max_tokens` (integer, optional): Output token budget (120-2000).
- **Response keys:** `status`, `q`, `n`, `res` (each with `t`, `u`, `s`, optional `d`), `ms`, `tok`; optional `prov`, `fail`, `warn`, `cut`.
- **Response example:**
  ```json
  {
    "status": "ok",
    "q": "PostgreSQL vs MySQL",
    "n": 5,
    "res": [
      {
        "t": "PostgreSQL vs MySQL: 2026 Comparison",
        "u": "https://example.org/db-comparison",
        "s": "Key architectural differences between Postgres and MySQL..."
      }
    ],
    "ms": 482,
    "tok": 92
  }
  ```

### 2.2 `extract_url`
Fetches and declutters a target URL, stripping boilerplate and extracting query-relevant passages.
- **Inputs:**
  - `url` (string, required): Target public URL (must pass SSRF DestinationPolicy).
  - `query` (string, optional): What to look for; omit for page sections.
  - `max_tokens` (integer, optional): Output token budget (200-8000).
  - `full` (boolean, default: false): Return the full cleaned page text.
- **Response keys:** `status`, `u`, `t`, `at`, `sha` (16-char), `src`, `ps` (list of `{u, at, x, s, h?, inj?}`), `tok`; optional `d`, `cut`, `warn`. In `full` mode `ps` is replaced by `full`, `x`, `s`.
- **Response example (passage mode):**
  ```json
  {
    "status": "ok",
    "u": "https://example.org/article",
    "t": "Article Title",
    "at": "2026-01-15T10:00:00Z",
    "sha": "8a3b5c...",
    "src": "html",
    "ps": [
      {
        "u": "https://example.org/article",
        "at": "2026-01-15T10:00:00Z",
        "x": "Extracted main article body markdown...",
        "s": [120, 342]
      }
    ],
    "tok": 84
  }
  ```

### 2.3 `crawl_site`
Bounded domain graph traversal resistant to infinite calendar and recursion traps.
- **Inputs:**
  - `url` (string, required): Seed URL.
  - `mode` (string, `map` or `crawl`, default: `map`): `map` returns discovered URLs; `crawl` returns extracted passages.
  - `max_pages` (integer, 1-30, default: 10): Page/URL cap.
  - `max_depth` (integer, 0-3, default: 2): Link hop depth cap.
  - `query` (string, optional): What to extract from each page (crawl mode only).
  - `max_tokens` (integer, optional): Output token budget.
- **Response keys (map mode):** `status`, `u`, `urls`, `ms`, `tok`; optional `warn`.
- **Response keys (crawl mode):** `status`, `url`, `pages_crawled`, `pages_indexed`, `passages_indexed`, `pages` / `passages`, `ms`, `tok`; optional `failures`, `warn`.

### 2.4 `deep_research`
Multi-hop query decomposition, evidence retrieval, and verbatim citation synthesis.
- **Inputs:**
  - `query` (string, required): Research question.
  - `max_tokens` (integer, optional): Output token budget (300-8000).
- **Response keys:** `status`, `q`, `n`, `f` (list of `{c, u, at, s, h?, d?, inj?}`), `gaps`, `searched`, `ms`, `tok`; optional `conflicts`, `cut`, `warn`.
- **Response example:**
  ```json
  {
    "status": "ok",
    "q": "Quantum computing qubit coherence times 2026",
    "n": 2,
    "f": [
      {
        "c": "Trapped ion coherence times exceeded 100 seconds.",
        "u": "https://nature.com/articles/example",
        "at": "2026-01-10T08:00:00Z",
        "s": [412, 458]
      }
    ],
    "gaps": [],
    "searched": ["superconducting qubit coherence 2026", "trapped ion coherence 2026"],
    "ms": 2840,
    "tok": 156
  }
  ```

---

## 3. Specialized Application Tools (`profile="full"`)

### 3.1 `company_research`
Generates structured corporate intelligence profiles from public sources.
- **Inputs:** `company` (string, required): Company name or domain.
- **Output keys:** `status`, `company`, `detected_domain`, `profile` (overview, leadership, products, competitors, risks), `ms`, `tok`; optional `warn`.

### 3.2 `market_research`
Factual asset analysis from regulatory disclosures and filings with strict numeric verification.
- **Inputs:** `asset` (string, required): Ticker or company name; `question` (string, optional).
- **Output keys:** `status`, `asset`, `disclosures_found`, `verified_metrics` (only captured fields — `currency`, `multiplier`, `as_of_date` are omitted when not present in source text), `recent_disclosures`, `disclaimer`, `ms`.

### 3.3 `market_portfolio`
Analyzes disclosures, regulatory filings and verified metrics across several assets at once (bounded concurrency).
- **Inputs:** `assets` (list of strings, required): tickers or company names.
- **Output keys:** `status`, `portfolio_size`, `total_disclosures_analyzed`, `total_verified_metrics`, `assets` (per-asset reports keyed by input name), `disclaimer`, `ms`.

### 3.4 `crawl2rag_index`
Crawls and indexes a website into a tenant-local SQLite FTS5/BM25 knowledge base.
- **Inputs:** `url` (string, required); `max_pages` (integer, 1-20, default: 5).
- **Tool annotation:** `readOnlyHint=false` (mutating).
- **Output keys:** `status`, `url`, `pages_crawled`, `pages_indexed`, `passages_indexed`, `embeddings_indexed`, `embedding_model`, `embedding_error`, `skipped_unchanged`, `failures`, `page_failures`, `ms`.

### 3.5 `crawl2rag_query`
Searches a local Crawl2RAG knowledge base with BM25 ranking and cited passage spans.
- **Inputs:** `question` (string, required); `top_k` (integer, 1-10, default: 5).
- **Tool annotation:** `readOnlyHint=true`.
- **Output keys:** `status`, `q`, `n`, `passages` (each with `url`, `title`, `span`, `text`, `score`, optional `signals`), `mode` (`bm25` or `hybrid`), `warnings`, `ms`.

### 3.6 `sheets_enrich`
Batch-enriches tabular rows with live web research and formula injection sanitization.
- **Inputs:** `rows` (list of dicts, required); `column_prompts` (dict[string, string], required).
- **Output keys:** `status`, `total_rows`, `processed_rows`, `failed_rows`, `preview`, `ms`; enriched values have `_status` fields.

### 3.7 `meeting_prep`
Prepares a cited pre-meeting brief from public professional sources.
- **Inputs:** `meeting_title` (string, required); `attendees` (list of strings, required); `company_or_org` (string, optional).
- **Output keys:** `status`, `attendees_researched`, `attendee_profiles`, `ms`.

### 3.8 `research_chat`
Multi-turn conversational research session with SQLite persistence.
- **Inputs:** `message` (string, required); `session_id` (string, optional).
- **Tool annotation:** `readOnlyHint=false` (mutating).
- **Output keys:** `status`, `session_id`, `message_id`, `role`, `content`, `citations`, `tokens_used`.

### 3.9 `tutorial_101`
Interactive walkthrough of search, extract, crawl, RAG and deep research APIs.
- **Inputs:** `step` (string, optional): `doctor`, `search`, `chat`, `company`, `market`, `sheets`, `meeting`, `rag`, `deep_research` or `all`.
- **Output keys:** `status`, `step`, `messages`, `ms`.

---

## 4. Standard Error Codes & Handling

WebLens returns stable `status: "error"` payloads, not JSON-RPC error codes:

| Machine code (`err`) | Meaning | Remediation |
|---|---|---|
| `bad_input` | Input validation failed | Ensure required fields are non-empty and within bounds. |
| `blocked_url` | Target IP is private/loopback or disallowed | Provide a publicly routable Internet hostname or IP. |
| `timeout` | Upstream fetch or operation timed out | Retry or inspect site availability. |
| `http_error` | Non-2xx HTTP response | Check FetchError.status; 401/403 are not retryable, 429 is retryable by providers. |
| `provider_error` | Search/adaptor failure | Provider may mark retryable=true for transient errors. |
| `no_reliable_result` | Query premise unverified/fictional | Treat as a real finding, not an error to paper over. |
| `budget_exhausted` | Token budget exceeded | Reduce requested `max_tokens` or result count. |
