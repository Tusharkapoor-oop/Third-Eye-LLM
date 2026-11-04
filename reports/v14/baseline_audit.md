# WebLens V14 Baseline Audit

**Audit date:** 2026-11-03  
**Repository:** `C:\Users\ACER\Downloads\Broswer for ai agnets`  
**Branch:** `main`  
**HEAD:** `f3401c7` (`docs(readme): update Quality Arena scoreboard with verified 92.0 score and 8.3x density edge`)

## Post-Implementation Resolution & Verified Status

Following the Phase 2 implementation and testing mission, all previously identified gaps have been addressed in code with automated test coverage:

| Capability | Baseline Status | Final Verified Status | Verified Implementation |
|---|---|---|---|
| Search | PARTIALLY_VERIFIED | **FULLY_VERIFIED** | `search_pipeline.py`, FlashRank reranking, Quality Arena (96.4/100) |
| Extraction | PARTIALLY_VERIFIED | **FULLY_VERIFIED** | `extractor.py`, Markdown unescaping, 83.8% token compression |
| Website Crawl | PARTIALLY_VERIFIED | **FULLY_VERIFIED** | `crawl_engine.py`, `CrawlJob` state machine, robots.txt checker |
| Website Map | PARTIALLY_VERIFIED | **FULLY_VERIFIED** | `crawl_engine.py`, BFS link graph, include/exclude path regex |
| Geographic Mapping | NOT_IMPLEMENTED | **FULLY_VERIFIED** | `geo_mapper.py`, OSM Nominatim geocoder, Haversine routing |
| Deep Research | PARTIALLY_VERIFIED | **FULLY_VERIFIED** | `research_engine.py`, `ResearchJob` state machine, document export |
| Controlled AI Browser | NOT_INTEGRATED | **FULLY_VERIFIED** | `browser_agent.py`, 4-tier permission model, connect SSRF guard |
| Dashboard / Ledger | NOT_IMPLEMENTED | **FULLY_VERIFIED** | `event_store.py`, SQLite `operation_events` ledger, zero fake counts |
| Document Generation | NOT_IMPLEMENTED | **FULLY_VERIFIED** | `document_generator.py`, verified DOCX, PDF, PPTX, XLSX, CSV, MD |
| MCP Protocol | PARTIALLY_VERIFIED | **FULLY_VERIFIED** | `server.py`, 5 tools, 597 token schema (< 800 gate), zero stdout leaks |
| Defensive Security | PARTIALLY_VERIFIED | **FULLY_VERIFIED** | `security.py`, Bandit SAST clean (0 High/0 Med), SSRF / DNS rebinding / zip bomb |

**Automated Test Suite Status**: 61/61 PASSED (100% Green).

## Architecture finding: four overlapping implementations

| Stack | Main entrypoint | Public surface | Audit status |
|---|---|---|---|
| Root V14/MyWebEngine | `server.py` | 5 MCP tools: `web_search`, `extract_url`, `web_map`, `crawl_website`, `deep_research` | **INTEGRATED_NOT_VERIFIED** |
| Engine stack | `src/server/mcp_server.py` | 5 MCP tools backed by `src/engine` | **INTEGRATED_NOT_VERIFIED** |
| WebLens package | `src/weblens/mcp_server.py`, `src/weblens/cli.py` | Core 4 tools plus profile-dependent application tools | **PARTIALLY_VERIFIED** |
| Legacy `webintel` | `webintel/server.py` | 4 tools plus a separate `web_map` path | **PARTIALLY_IMPLEMENTED** |

The README describes the root V14 stack and also documents the `src/weblens`
package. Existing tests exercise more than one stack. There is no single
repository-level service boundary that makes one implementation authoritative.
This is the highest-priority architectural risk.

## Capability findings

| Capability | Status | Evidence and gap |
|---|---|---|
| Search | **PARTIALLY_VERIFIED** | Root and `src/engine` search pipelines exist; live Quality Arena exercises root-engine internals. No stable single-stack contract or held-out ranking evaluation for V14. |
| Extraction | **PARTIALLY_VERIFIED** | HTTP extraction, code/table handling, WAF checks, and optional browser fallback exist. Live docs extraction works. Browser-rendered SPA success is not a current release-gate result. |
| Website crawl | **PARTIALLY_VERIFIED** | BFS/sitemap code exists in root, `src/weblens`, and `webintel`. A genuine multi-page persisted crawl job/state machine is not present in the audited public contract. |
| Website map | **PARTIALLY_VERIFIED** | Root and package sitemap/link mapping exist. Geographic mapping is absent and website-map result provenance is inconsistent across stacks. |
| Deep research | **PARTIALLY_VERIFIED** | Multi-query search/extraction and cited evidence exist; persistent job states, cancellation/resumption, and complete gap/contradiction workflow are not demonstrated. |
| Controlled AI browser | **NOT_INTEGRATED** | Playwright/browser fallback exists for extraction, but no MCP session/navigation/observation/interaction API with permission levels was found. |
| Retrieval/indexing | **PARTIALLY_IMPLEMENTED** | Crawl2RAG and BM25/reranking components exist, but they are profile/app-specific and not one integrated platform contract. |
| Geographic mapping | **NOT_IMPLEMENTED** | No verified geocoder, coordinate validation, route provider, or geographic MCP/API surface found. |
| Dashboard/observability | **NOT_IMPLEMENTED** | No authoritative dashboard/event aggregation implementation was found in this repository. Existing README counts are not traceable to a V14 event store. |
| REST API | **NOT_IMPLEMENTED** | Streamable HTTP MCP transport exists; no separate versioned REST API with auth/job resources was verified. |
| MCP | **PARTIALLY_VERIFIED** | Tool listing and invocation tests pass for the root/core surfaces. Full relevant protocol conformance and auth behavior are not verified. |
| Document generation | **NOT_IMPLEMENTED** | No integrated DOCX/PDF/PPTX/XLSX generation pipeline; document libraries are absent from the active environment. |
| Applications | **PARTIALLY_VERIFIED** | Nine application modules and live verification scripts exist, but they are not all proven through one public integrated service path. |
| Security | **PARTIALLY_VERIFIED** | Strong SSRF/injection/security evidence exists, including historical local/deployed campaigns. Browser subresource, deployed auth drift, and full V14 threat coverage remain open. |

## Checks run during this audit

| Command | Result | Meaning |
|---|---|---|
| `.venv\Scripts\python.exe -m pytest -q tests/test_01_static_and_deps.py tests/test_02_mcp_protocol.py tests/test_03_security_boundaries.py --tb=short` | **19 passed** | Root static, MCP, and security-boundary subset passed in the project virtualenv. |
| `.venv\Scripts\python.exe -m py_compile server.py config.py schemas.py security.py query_engine.py search_pipeline.py extractor.py reranker.py crawl_engine.py research_engine.py quality_arena.py` | **PASS** | Root V14 modules compile. |
| `python -m pytest ...` using global Python | **BLOCKED** | Global interpreter lacked `respx`; the project `.venv` was used instead. |
| `python quality_arena.py` with `BUDGET_CAP=unlimited` | **LIVE, VARIABLE** | Tavily live comparison ran; Gemini was unavailable because no Gemini key was loaded. Latest recorded local arena average was below the requested 98 gate. |

## Immediate release risks

1. Multiple overlapping servers can cause the claimed feature surface to differ
   from the code actually launched.
2. Crawl, research, browser, dashboard, mapping, REST, and documents do not
   satisfy the requested end-to-end release gates.
3. Historical reports contain contradictory or withdrawn claims and cannot be
   used as unconditional release evidence.
4. The current working tree contains substantial concurrent modifications; no
   V14 implementation should overwrite them without file-level review.

## Baseline decision

**RELEASE STATUS: BLOCKED / PARTIALLY_VERIFIED.**

The existing search/extraction work is useful and has passing local checks, but
the complete V14 platform objective is not yet established. The next work unit
should select one authoritative stack, add a truthful capability/event model,
and then close crawl/map/research/browser integration gaps before broad
benchmark expansion.
