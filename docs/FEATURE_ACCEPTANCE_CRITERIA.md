# WebLens Feature Acceptance Criteria

## 1. Principles of Verification
Under the WebLens Zero-Fabrication Directive, no feature may be marked `PASS - VERIFIED` or `SHIPPED` unless it satisfies seven mandatory release gates:
1. **Gate 1 (Implementation):** Working source code exists in the repository without placeholder stubs.
2. **Gate 2 (Correctness):** Unit and integration tests pass deterministically.
3. **Gate 3 (Security):** Passes threat model checks, injection defenses, and SSRF restrictions.
4. **Gate 4 (Performance):** Latency and token consumption fall within pre-registered budgets.
5. **Gate 5 (Evidence):** Execution output and test logs are preserved in `evidence/` with SHA-256 hashes.
6. **Gate 6 (Documentation):** Accurate API reference and known limitations are documented.
7. **Gate 7 (Regression):** Existing package tests and security baselines remain unaffected.

---

## 2. Application-Specific Acceptance Criteria

### 2.1 Crawl2RAG (`weblens.apps.crawl2rag`)
- **Ingestion & Politeness:** Respects `robots.txt` per host; restricts crawl rate to $\le 1$ req/sec; enforces max depth $\le 3$ and max pages $\le 30$.
- **Indexing:** Stores chunks in local SQLite database with FTS5 virtual table for BM25 retrieval.
- **SSRF Hardening:** Validates every crawled hyperlink against `DestinationPolicy` before queuing.
- **Retrieval Grounding:** Queries against the knowledge base return exact text spans, character offsets, source URLs, and timestamps.
- **Acceptance Threshold:** $100\%$ valid citations on test corpus; zero SSRF leakage on loopback/metadata links.

### 2.2 Deep Research (`weblens.apps.deep_research`)
- **Decomposition:** Automatically decomposes complex multi-hop research questions into 2 to 4 distinct sub-queries.
- **Evidence Provenance:** Every claim in the synthesized report links to an explicit source URL and exact character offset range.
- **Conflict Handling:** Flags contradictory claims across independent domains instead of asserting a single answer.
- **Abstention:** Returns `no_reliable_result` when queries address unanswerable, fictional, or future speculative queries.
- **Acceptance Threshold:** Zero hallucinated citations; $100\%$ of claims verified against fetched text.

### 2.3 Company Researcher (`weblens.apps.company`)
- **Schema Validation:** Emits structured JSON containing company overview, leadership, products, funding/news, competitors, and risks.
- **Entity Disambiguation:** Differentiates same-name companies using geography, industry, or official domain.
- **Non-Existent Entity Handling:** Explicitly returns `not_found` for fictional or unverified company entities; never fabricates corporate data.
- **Acceptance Threshold:** $100\%$ precision on non-existent entity detection; zero fabricated executives or financial figures.

### 2.4 Research Agent Chat (`weblens.apps.chat`)
- **Context Retention:** Maintains multi-turn conversation history within a strict token budget (default 4,000 tokens).
- **Prompt Injection Defense:** Scans all retrieved web passages before adding them to conversation context.
- **Citation Preservation:** Returns cited references for every answer turn.
- **Acceptance Threshold:** Passes multi-turn state consistency tests; rejects prompt injection payloads planted in web pages.

### 2.5 Market Researcher (`weblens.apps.market`)
- **Data Veracity:** Extracts market metrics only from authoritative disclosures, investor relations, and regulatory filings.
- **Missing Data Handling:** Returns `not_available` when real-time prices or financial ratios are unverified; never estimates numbers.
- **Mandatory Disclaimer:** Appends non-financial-advice disclaimer to every market research report.
- **Acceptance Threshold:** Zero fabricated prices, multiples, or market caps; $100\%$ inclusion of compliance disclaimer.

### 2.6 Sheets Enrichment (`weblens.apps.sheets`)
- **Input Formats:** Accepts CSV, TSV, and JSON tabular datasets.
- **Formula Injection Defense:** Sanitizes all cell values starting with dangerous characters (`=`, `+`, `-`, `@`) by prepending a single quote `'`.
- **Enrichment Provenance:** Every filled cell is paired with a source URL, retrieval timestamp, and status (`verified`, `not_found`, `conflicting`).
- **Resilience:** Resumes interrupted batch jobs from checkpointed rows without duplicating work.
- **Acceptance Threshold:** Zero formula execution in exported sheets; $100\%$ attribution for enriched cells.

### 2.7 Meeting Preparation Agent (`weblens.apps.meeting`)
- **Input Sources:** Accepts local ICS calendar files or manual attendee/meeting specifications.
- **Privacy Boundary:** Strictly restricts research to public corporate and professional information (LinkedIn, company bios, press releases).
- **Redaction Guard:** Refuses and logs requests seeking private personal information (home addresses, personal phone numbers, family details).
- **Acceptance Threshold:** $100\%$ refusal on private personal information probes; zero data leakage to unauthorized endpoints.

### 2.8 WebLens 101 Tutorial (`weblens.apps.tutorial`)
- **Reproducibility:** Every code block in the tutorial is executed against live/fixture endpoints in CI.
- **Accuracy:** Tutorial output snippets match actual CLI/API outputs byte-for-byte or schema-for-schema.
- **Acceptance Threshold:** $100\%$ passing CI execution for all tutorial documentation code blocks.
