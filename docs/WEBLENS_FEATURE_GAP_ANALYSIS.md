# WebLens Feature Gap Analysis

## 1. Executive Summary
This document establishes the verified feature baseline of the WebLens engine and maps the technical gaps between the current core MCP retrieval engine and the required 9 high-level autonomous research and knowledge applications.

---

## 2. Comprehensive Feature Matrix

| Feature | Existing State | Missing Components | Required Implementation | Verification Status | Classification |
|---|---|---|---|---|---|
| **Core Web Search** | Implemented in `weblens.search.router` with multi-provider failover (DuckDuckGo, Brave, Wikipedia, Tavily). | Dynamic rank fusion weighting based on real-time latency and query intent. | Reciprocal Rank Fusion tuning; domain allowlist/denylist filter hardening. | Verified in `weblens/tests/test_search_router.py` (162 passing). | **Already implemented and verified** |
| **URL Extraction & Passage Scoring** | Implemented in `weblens.extract` via `trafilatura`, `lxml`, and `passages.py`. | Multi-column table markdown normalization; scanned PDF OCR. | Markdown table preservation; sentence-boundary splitting improvements. | Verified in `weblens/tests/test_extract.py` and EXP-005. | **Already implemented and verified** |
| **SSRF & Egress Protection** | Implemented in `weblens.net.ssrf` (`DestinationPolicy`) blocking IPv4/IPv6 private and metadata ranges. | Container namespace isolation for local Playwright process. | Enforce DNS resolution pinning across all outgoing worker requests. | Verified in Gate 1 tamper/mutation tests and EXP-002 (38/38 blocked). | **Already implemented and verified** |
| **Prompt Injection Defense** | Regex-based scanner in `weblens.security.injection`. | Multilingual pattern coverage (Spanish, French, German, Russian, Chinese, Hindi). | Expanded internationalized injection patterns and indirect injection heuristics. | Verified in `tier-d-injection-eval` (76.24% recall, 0.00% benign FPR). | **Implemented but incomplete** |
| **Bounded Site Crawler** | Implemented in `weblens.crawl.crawler` with robots.txt parser and trap detection. | Incremental recrawl caching using content hashes for RAG syncing. | Delta-crawler module comparing SHA-256 hashes of retrieved pages. | Verified in `weblens/tests/test_crawl.py`. | **Implemented but incomplete** |
| **Deep Research Engine** | Implemented in `weblens.research.engine` with verbatim evidence spans and safety guard. | Claim-level multi-hop iteration, cross-domain diversity metrics, structured bibliography export. | `weblens.apps.deep_research` application layer with recursive sub-query orchestration. | Verified in `weblens/tests/test_research.py`. | **Implemented but incomplete** |
| **Crawl2RAG (Website to KB)** | Crawler and extractor exist; local vector/FTS indexing pipeline is missing. | Local SQLite FTS5 / BM25 indexer, chunk embedding generation, interactive KB query tool. | `weblens.apps.crawl2rag` module creating and querying local knowledge bases. | Requires end-to-end integration test with synthetic documentation site. | **Missing** |
| **Company Researcher** | Basic research engine can query company names; structured profiling is missing. | Entity disambiguation, financial/leadership schema extraction, non-existent entity detection. | `weblens.apps.company` module with validated corporate profile schema. | Requires evaluation against 100 stratified public/private company test set. | **Missing** |
| **Research Agent Chat** | MCP tools allow single-turn interactions; conversational session state is missing. | Multi-turn memory management, conversation context budgeting, follow-up resolution. | `weblens.apps.chat` module with pluggable client and prompt-injection quarantine. | Requires multi-turn benchmark with conversation memory verification. | **Missing** |
| **Market Researcher** | No specialized financial engine; general search returns web snippets. | SEC/regulatory filing extraction, stock price verification, financial disclaimer enforcement. | `weblens.apps.market` module enforcing strictly verified numbers and no-guess policies. | Requires verification on 100 factual corporate financial disclosure questions. | **Missing** |
| **Sheets Data Enrichment** | No tabular dataset enrichment tooling exists. | CSV/XLSX parser, per-row async worker pool, formula injection sanitization (`=`, `+`, `-`, `@`). | `weblens.apps.sheets` module supporting batch processing and resumable checkpoints. | Requires evaluation on 500-row enrichment test set. | **Missing** |
| **Meeting Preparation Agent** | No calendar or attendee profiling module exists. | ICS calendar parser, public professional background researcher, privacy refusal guard. | `weblens.apps.meeting` module strictly scoped to public professional facts. | Requires privacy penetration tests on synthetic calendar events. | **Missing** |
| **WebLens 101 Tutorial** | Documentation exists in `README.md` and `docs/`; step-by-step runnable tutorials missing. | Executable tutorial scripts verified against live endpoints; developer onboarding guide. | `docs/tutorials/` suite with tested code blocks for VS Code, Cline, and Roo Code. | Requires automated CI validation of all tutorial code blocks. | **Missing** |
| **SearXNG Meta-Search** | Provider class `weblens.search.searxng` implemented. | Local SearXNG instance running at `http://localhost:8080`. | SearXNG Docker container deployment. | Blocked: `ConnectError [WinError 10061]` (SearXNG offline). | **Blocked by external dependency** |
| **Tavily Direct API Spend** | Provider class `weblens.search.tavily` implemented and operational. | Budget cap policy strictly limiting calls to 60% of quota. | Real-time usage tracking against `/usage` endpoint before execution. | Operational; spend intentionally paused under owner budget directive. | **Already implemented and verified** |

---

## 3. Gap Priority Ranking

1. **Priority 1 (Core Applications Foundation):** Implement `Crawl2RAG` and `Deep Research` application modules, leveraging existing crawler, extractor, and research primitives.
2. **Priority 2 (Intelligence & Profiling):** Implement `Company Researcher` and `Market Researcher` modules with strict numerical verification and entity disambiguation.
3. **Priority 3 (Batch Data & Conversational Interaction):** Implement `Sheets` data enrichment (with CSV formula injection defense) and `Research Agent Chat`.
4. **Priority 4 (Privacy-Sensitive Capabilities):** Implement `Meeting Preparation Agent` with synthetic test calendars and strict non-public data redaction.
5. **Priority 5 (Developer Onboarding & Tooling):** Publish `WebLens 101` interactive learning modules and verify all executable code blocks.
