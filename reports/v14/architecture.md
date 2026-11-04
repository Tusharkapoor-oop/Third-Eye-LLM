# V14 Architecture & Canonical Infrastructure

## Unified Architecture Overview

The WebLens architecture has been unified into a high-performance, headless AI web-intelligence service that external AI agents and LLMs call via Model Context Protocol (MCP) and Python API.

```text
[External AI Agent / Host LLM]
       │
       ▼
[Unified FastMCP Server (server.py)]  <-- Flat schema (597 tokens, zero stdout contamination)
       │
       ├──> [Search Pipeline] ─────────> Multi-Query Consensus + Domain Authority + Fallbacks
       ├──> [Tiered Extractor] ────────> Fast HTTP / PrimP -> Stealth Headless -> Table/Code Safe
       ├──> [Crawl Engine] ────────────> Asynchronous CrawlJob State Machine + Robots.txt + Link Graph
       ├──> [Deep Research Engine] ────> Multi-Hop Decomposition + Gap Analysis + Cited Synthesis
       ├──> [Controlled Browser Agent] > 4-Tier Permission Model + DOM Observation + Connect SSRF Guard
       ├──> [Geographic Mapper] ───────> OpenStreetMap Geocoder + Boundary Validation + Haversine Routing
       ├──> [Document Generator] ──────> Validated DOCX, PDF, PPTX, XLSX, CSV, MD Compilation
       └──> [Event Store & Ledger] ────> Canonical SQLite Event Persistence (Zero Fake Counts)
```

## Resolved Gaps & Unified Solutions

1. **Shared Event & Provenance Ledger**:
   - `event_store.py` provides persistent SQLite logging across all 8 capabilities (`search`, `extract`, `crawl`, `map_geo`, `map_web`, `research`, `browser`, `document`).
   - Distinguishes attempted, succeeded, failed, and blocked requests.

2. **Persistent Crawl & Deep Research State Machines**:
   - `crawl_engine.py` supports `start_crawl_job()`, `get_crawl_status()`, `cancel_crawl_job()`, and link graph export (`CrawlLinkGraph`).
   - `research_engine.py` supports `start_research_job()`, `get_research_status()`, `cancel_research_job()`, and document export via `DocumentGenerator`.

3. **Controlled AI Browser Infrastructure**:
   - `browser_agent.py` provides isolated Playwright Chromium sessions with DOM accessibility observation, form controls inspection, text previews, and 4-tier permission model.

4. **Geographic Mapping Engine**:
   - `geo_mapper.py` implements OpenStreetMap Nominatim geocoding, boundary validation, and Haversine great-circle distance matrix routing.

5. **Document Generation Engine**:
   - `document_generator.py` compiles research reports and tables into verified DOCX, PDF, PPTX, XLSX, CSV, and MD artifacts with magic-byte and structural integrity checks.

6. **Defensive Security Perimeter**:
   - `security.py` enforces connection-time SSRF socket checks, DNS rebinding guards, streaming zip bomb 2MB abort, and hidden DOM injection sanitization.
