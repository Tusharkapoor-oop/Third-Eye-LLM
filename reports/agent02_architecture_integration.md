# Agent 02: Architecture & Integration Audit Report

## 1. Executive Summary

- **Target Repository**: WebLens / MyWebEngine MCP Intelligence Server
- **Auditor**: Agent 02 - Architecture & Integration Auditor
- **Audit Date**: 2026-11-05
- **Status**: **PASS WITH ARCHITECTURAL OBSERVATIONS**
- **Test Suite Results**:
  - `tests/test_01_static_and_deps.py`: **5 passed in 8.97s** (100% pass)
  - `tests/test_02_mcp_protocol.py` + `tests/test_v14_server_event_wiring.py`: **7 passed in 10.30s** (100% pass)
  - `tests/test_both_stack_comparison.py`: **3 passed in 68.05s** (100% pass)
- **Modularity & Boundaries Verdict**:
  The repository maintains three concurrent implementations of the web intelligence engine: the **Root V14 Server** (`server.py`), the **Engine Package** (`src/engine/` + `src/server/mcp_server.py`), and the **Modular WebLens Architecture** (`src/weblens/`). While each subsystem functions and satisfies its designated test suites, significant architectural drift, boundary crossings, schema divergences, and unexercised static analysis gaps were uncovered during this audit.

---

## 2. Test Execution & Evidence Log

### 2.1. Layer 1 Architecture and Static Tests (`test_01_static_and_deps.py`)
Command: `.\.venv\Scripts\pytest -q tests/test_01_static_and_deps.py`  
Output: `5 passed in 8.97s`

| Test Identifier | Verified Capability | Status | Evidence / Line Citation |
| :--- | :--- | :--- | :--- |
| `test_ruff_lint_cleanliness` | Ruff import hygiene & zero syntax errors across `CORE_MODULES` | **PASSED** | `tests/test_01_static_and_deps.py:32-36` |
| `test_bandit_sast_security` | Bandit SAST scan (0 High, 0 Medium) across `CORE_MODULES` | **PASSED** | `tests/test_01_static_and_deps.py:39-44` |
| `test_gitignore_protects_secrets_and_profiles` | `.gitignore` covers `.env`, SQLite caches, browser profiles | **PASSED** | `tests/test_01_static_and_deps.py:46-56` |
| `test_canary_secrets_leak_prevention` | Canary token leakage defense in error envelopes (`FailedItem`) | **PASSED** | `tests/test_01_static_and_deps.py:58-74` |
| `test_core_module_import_integrity` | Core singletons and modules import cleanly without runtime errors | **PASSED** | `tests/test_01_static_and_deps.py:76-87` |

### 2.2. Protocol & Lifecycle Wiring Verification
Command: `.\.venv\Scripts\pytest -q tests/test_02_mcp_protocol.py tests/test_v14_server_event_wiring.py`  
Output: `7 passed in 10.30s`

| Test Identifier | Verified Capability | Status | Evidence / Line Citation |
| :--- | :--- | :--- | :--- |
| `test_mcp_tools_registration_and_naming` | MCP 5 core tools register with `^[a-z0-9_]+$` and no vendor prefix | **PASSED** | `tests/test_02_mcp_protocol.py:26-40` |
| `test_mcp_tools_flat_schemas` | Input schemas are flat, omitting confusing `anyOf`/`oneOf` | **PASSED** | `tests/test_02_mcp_protocol.py:42-51` |
| `test_mcp_token_tax_gate` | Combined schema token overhead strictly < 800 tokens (`cl100k_base`) | **PASSED** | `tests/test_02_mcp_protocol.py:53-68` |
| `test_stdio_stdout_contamination_gate` | STDIO transport emits zero non-JSON-RPC stdout output | **PASSED** | `tests/test_02_mcp_protocol.py:71-109` |
| `test_root_tool_wrapper_records_attempt_and_success` | `_recorded_operation` logs `attempted` and `success` to `event_store` | **PASSED** | `tests/test_v14_server_event_wiring.py:11-27` |
| `test_root_tool_wrapper_records_failure_and_reraises` | Exceptions logged as `failed` with error type and re-raised | **PASSED** | `tests/test_v14_server_event_wiring.py:29-45` |
| `test_root_tool_wrapper_records_blocked_security_failure` | `SecurityValidationError` logged as `blocked` and re-raised | **PASSED** | `tests/test_v14_server_event_wiring.py:47-60` |

### 2.3. Cross-Stack Parity Verification (`test_both_stack_comparison.py`)
Command: `.\.venv\Scripts\pytest -q tests/test_both_stack_comparison.py`  
Output: `3 passed in 68.05s`

| Test Identifier | Verified Capability | Status | Evidence / Line Citation |
| :--- | :--- | :--- | :--- |
| `test_search_both_stacks_same_query` | Search parity between `src/engine/` (`SearchAggregator`) and `src/weblens/` (`SearchRouter`) | **PASSED** | `tests/test_both_stack_comparison.py:34-68` |
| `test_extract_both_stacks_same_url` | Extraction parity between `src/engine/` (`DocumentExtractor`) and `src/weblens/` (`ExtractionService`) | **PASSED** | `tests/test_both_stack_comparison.py:73-117` |
| `test_ssrf_both_stacks_block` | SSRF defense parity blocking loopback and cloud metadata across both engines | **PASSED** | `tests/test_both_stack_comparison.py:123-159` |

---

## 3. WebLens Architectural Topology & Layer Decomposition

The codebase contains four distinct architectural layers serving different execution profiles:

```
                           +-------------------------------------------------+
                           |             MCP Clients / External AI           |
                           |   (Claude Desktop, Roo-Code, OpenWebUI, CLI)    |
                           +------------------------+------------------------+
                                                    | JSON-RPC (STDIO / HTTP)
                 +----------------------------------+----------------------------------+
                 |                                  |                                  |
                 v                                  v                                  v
+---------------------------------+  +-------------------------------+  +---------------------------------+
|      Root V14 Server Layer      |  |    Engine Subsystem Layer     |  |     Modular WebLens Layer       |
|          (server.py)            |  |  (src/server/mcp_server.py)   |  |   (src/weblens/mcp_server.py)   |
+---------------------------------+  +-------------------------------+  +---------------------------------+
| - 5 Core Tools + Extended Tools |  | - 5 Core Tools Only           |  | - Core Tools + Apps Profiles    |
| - FastMCP Server Instance       |  | - FastMCP Server Instance     |  | - Read-Only Annotations         |
| - Truthful event_store Logging  |  | - Dual Text + Structured      |  | - Strict R2 Invariant (no score)|
| - Root module composition       |  | - Lazy-loaded singletons      |  | - Pure Dependency Injection     |
+----------------+----------------+  +---------------+---------------+  +----------------+----------------+
                 |                                   |                                   |
                 v                                   v                                   v
+---------------------------------+  +-------------------------------+  +---------------------------------+
|       Root Core Engines         |  |          src/engine/          |  |          src/weblens/           |
+---------------------------------+  +-------------------------------+  +---------------------------------+
| - search_pipeline.py            |  | - search/aggregator.py        |  | - service.py (WebLens facade)   |
| - extractor.py                  |  | - extract/extractor.py        |  | - search/router.py              |
| - crawl_engine.py               |  | - crawl/crawler.py, mapper.py |  | - extract/service.py            |
| - research_engine.py            |  | - research/deep_research.py   |  | - crawl/engine.py               |
| - browser_agent.py (Playwright) |  | - security.py (26 CIDRs)      |  | - research/engine.py            |
| - document_generator.py         |  | - schemas.py (Pydantic V2)    |  | - net/ (SafeFetcher, SSRF guard)|
| - geo_mapper.py (Nominatim)     |  | - config.py (EngineConfig)    |  | - security/ (injection scan)    |
| - event_store.py (SQLite WAL)   |  |                               |  | - apps/ (9 domain applications)|
+---------------------------------+  +-------------------------------+  +---------------------------------+
```

### Detailed Layer Roles:
1. **Root V14 Server Layer (`server.py`)**:
   - The primary unified production server deployed for local and container environments (`Dockerfile`, `docker-compose.yml`).
   - Implements the complete 5 core Tavily-compatible tools (`web_search`, `extract_url`, `web_map`, `crawl_website`, `deep_research`).
   - Extends with opt-in browser control (`browser_create_session`, `browser_navigate`, `browser_interact`, `browser_screenshot`, `browser_close_session`), geographic resolution (`geo_resolve`), document synthesis (`generate_document`), and operational telemetry (`dashboard_metrics`) via `WEBLENS_V14_EXTENDED_TOOLS=1`.
   - All tool invocations are wrapped in `_recorded_operation()` (`server.py:44-100`) to guarantee that operations are faithfully recorded in `event_store.py` with zero hallucinated counts.

2. **Engine Subsystem Layer (`src/engine/` and `src/server/mcp_server.py`)**:
   - Packaged as an installable Python package under `src/` (`pyproject.toml:57`).
   - Features lazy-loaded singleton getters (`get_aggregator()`, `get_extractor()`, etc., `src/server/mcp_server.py:31-59`) ensuring sub-second startup times.
   - Emits dual-format responses via `t.CallToolResult` providing both compact JSON strings and native `structured_content` dictionaries (`src/server/mcp_server.py:61-68`).

3. **Modular WebLens Layer (`src/weblens/`)**:
   - High-modularity architecture designed around explicit dependency injection and zero global mutable state.
   - Orchestrated through the unified `WebLens` facade class (`src/weblens/service.py:38-53`).
   - Enforces the **R2 Invariant**: guarantees that uncalibrated numbers (`score`, `confidence`, `relevance`, `similarity`) are completely excluded from outputs to prevent false LLM trust.
   - Directly powers 9 specialized applications (`src/weblens/apps/`): Crawl2RAG, Deep Research, Company Researcher, Research Chat, Market Researcher, Sheets Enrichment, Meeting Prep, Tutorial 101, and Persistent Research Chat.

---

## 4. Modularity, Coupling, and Dependency Boundary Audit

### 4.1. Modularity Assessment
- **`src/weblens/` (Score: 9.5/10)**:
  Exemplary cohesion and separation of concerns. Subsystems (`net`, `security`, `extract`, `crawl`, `search`, `research`, `apps`) communicate exclusively through well-defined internal interfaces. The orchestrator `WebLens` (`src/weblens/service.py:38-53`) instantiates subsystems via dependency injection, passing `Settings`, `Cache`, and `SafeFetcher` down the stack without relying on global variables.
- **`src/engine/` (Score: 7.5/10)**:
  Well-organized package hierarchy, but coupled to global immutable configuration `src.engine.config.CONFIG`. Subsystems possess clean domain separation, but exhibit cross-layer dependency leaks (see Section 4.2).
- **Root Layer (`server.py` + Root modules) (Score: 7.0/10)**:
  Modular by file, but uses flat imports without a package namespace. Singletons are instantiated eagerly at module import time (`server.py:38-41`), creating network and cache connections upon simple module import.

### 4.2. Dependency Boundary Violations & Anomalies

#### Finding 1: Cross-Package Coupling in `browser_fallback.py`
- **Location**: `src/engine/extract/browser_fallback.py:47-52`
- **Violation**: The `src/engine` extraction pipeline reaches outside its package boundary into `weblens` / `src.weblens` to instantiate the browser egress proxy:
  ```python
  try:
      from weblens.config import Settings
      from weblens.net.browser_proxy import BrowserEgressProxy
  except ImportError:
      from src.weblens.config import Settings
      from src.weblens.net.browser_proxy import BrowserEgressProxy
  ```
- **Architectural Impact**: Creates circular architectural coupling between `src/engine` and `src/weblens`. If `src/engine` is packaged or distributed independently, this import fails.

#### Finding 2: `pyproject.toml` Script Entrypoint Points to Secondary Server
- **Location**: `pyproject.toml:57`
- **Code**:
  ```toml
  [project.scripts]
  web-intel-mcp = "src.server.mcp_server:main"
  ```
- **Violation**: The package console script entrypoint points to `src/server/mcp_server.py`, whereas the V14 extended tools, Playwright browser automation, document generation, and SQLite event auditing are implemented in root `server.py`.
- **Architectural Impact**: Users running `web-intel-mcp` after `pip install .` do not receive the V14 extended tools or event logging capabilities.

#### Finding 3: `quality_arena.py` Deep Import Coupling
- **Location**: `quality_arena.py:205, 217, 229`
- **Code**:
  ```python
  from src.engine.search.aggregator import SearchAggregator
  from src.engine.extract.extractor import DocumentExtractor
  from src.engine.research.deep_research import DeepResearchEngine
  ```
- **Architectural Impact**: Bypasses the public MCP server interface contracts and couples benchmarking directly to `src.engine` internals rather than evaluating the root server via standard protocol.

---

## 5. Interface Contracts & Protocol Conformance Audit

### 5.1. Tool Interface Contract Comparison

| Property / Feature | Root `server.py` | `src/server/mcp_server.py` | `src/weblens/mcp_server.py` |
| :--- | :--- | :--- | :--- |
| **Framework** | FastMCP (`MCPServer`) | FastMCP (`MCPServer`) | Official MCP SDK (`MCPServer`) |
| **Tool Names** | `web_search`, `extract_url`, `web_map`, `crawl_website`, `deep_research` | `web_search`, `extract_url`, `web_map`, `crawl_website`, `deep_research` | `web_search`, `extract_url`, `crawl_site`, `research_topic` |
| **Extended Tools** | 8 tools (`browser_*`, `geo_resolve`, `generate_document`, `dashboard_metrics`) | None | Apps profile tools (`company_research`, `crawl_to_rag`, etc.) |
| **Output Type** | Formatted JSON string (`model_dump_json(indent=2)`) | `t.CallToolResult` (TextContent + structured_content) | Compact single-line JSON string (`_tool_json`) |
| **Error Handling** | Re-raises exceptions after logging to `event_store` | Returns `CallToolResult(..., is_error=True)` | Raises `ToolError` on errors; non-error evidence statuses stay success |
| **Lifecycle Telemetry**| Full SQLite event recording (`attempted`, `success`, `blocked`, `failed`) | None | None |

### 5.2. Schema & Contract Incompatibilities

#### Finding 4: Incompatible `validate_url_security` Contracts
- **Root implementation** (`security.py:69-76`):
  ```python
  def validate_url_security(url: str) -> tuple[str, int]:
      # Returns (hostname, port) or raises SecurityValidationError
  ```
- **Engine implementation** (`src/engine/security.py:112-116`):
  ```python
  def validate_url_security(url: str) -> tuple[bool, str, list[str]]:
      # Returns (is_safe: bool, reason: str, resolved_ips: list[str]) without raising
  ```
- **Architectural Defect**: Both modules define `validate_url_security`, but with completely contradictory signatures, return types, and exception policies. Code expecting one will immediately crash if provided the other.

#### Finding 5: `ChunkResult` Field Discrepancy
- **Root Schema** (`schemas.py:14-21`):
  ```python
  class ChunkResult(BaseModel):
      content: str
      score: float = Field(default=0.0, ge=0.0, le=1.0)
      char_count: int = Field(default=0)
      section_title: str | None = Field(default=None)
  ```
- **Engine Schema** (`src/engine/schemas.py:15-24`):
  ```python
  class ChunkResult(BaseModel):
      model_config = ConfigDict(extra="forbid")
      content: str
      score: float
      char_count: int
      section: str = ""
      char_start: int = Field(default=0, ge=0)
      char_end: int = Field(default=0, ge=0)
  ```
- **Architectural Defect**: Field name collision between `section_title` (root) and `section` (`src/engine`), combined with `extra="forbid"` in `src/engine/schemas.py`. Cross-serialization between layers fails schema validation.

#### Finding 6: R2 Invariant Divergence (Calibrated Evidence vs. Agent Contract)
- `src/weblens` strictly enforces the R2 invariant: no uncalibrated floating-point metrics (`score`, `confidence`, `relevance`) are emitted to LLMs. Passages carry exact character offsets (`s`), fetch timestamps (`at`), and URLs (`u`).
- Root `schemas.py` and `src/engine/schemas.py` return `score: float` (0.0 to 1.0) and latency metrics to satisfy Tavily-compatible agent response contracts.
- **Architectural Observation**: Both approaches are intentional for their respective audiences (WebLens for direct grounded evidence; Root Server for drop-in Tavily replacement), but must be documented clearly to prevent integration ambiguity.

---

## 6. Static Analysis, SAST & Code Quality Audit

### 6.1. Defect in `src/engine/extract/extractor.py` (Undefined Name `os`)
- **Location**: `src/engine/extract/extractor.py:124`
- **Code**:
  ```python
  key = (CONFIG.tavily_api_key or os.getenv("TAVILY_API_KEY", "")).strip()
  ```
- **Defect**: The module `os` is not imported anywhere in `src/engine/extract/extractor.py`.
- **Ruff Diagnostic**: `F821 Undefined name 'os'`
- **Runtime Impact**: If `_tavily_extract_rescue` is called during a WAF fallback, the call will immediately raise `NameError: name 'os' is not defined`.
- **Why `test_01_static_and_deps.py` missed this**:
  `tests/test_01_static_and_deps.py:17-29` defines:
  ```python
  CORE_MODULES = [
      "server.py", "security.py", "config.py", "schemas.py",
      "extractor.py", "reranker.py", "query_engine.py",
      "search_pipeline.py", "crawl_engine.py", "research_engine.py",
      "cache.py",
  ]
  ```
  The test only checks the root files, completely omitting all modules inside `src/engine/` and `src/weblens/` from its Ruff lint suite.

### 6.2. SAST Security Scan: Untrusted XML Parsing in `src/engine`
Running Bandit with Medium+ confidence (`bandit -r src/engine -ll`) identified 2 vulnerabilities:
1. **`src/engine/crawl/mapper.py:45`**:
   `root = ET.fromstring(raw_bytes)`  
   *Issue*: `[B314:blacklist] Using xml.etree.ElementTree.fromstring to parse untrusted XML data is known to be vulnerable to XML attacks (CWE-20).*
2. **`src/engine/search/bing_provider.py:122`**:
   `root = ET.fromstring(payload)`  
   *Issue*: `[B314:blacklist] Using xml.etree.ElementTree.fromstring to parse untrusted XML data (CWE-20).*
- **Root Comparison**: The root crawler (`crawl_engine.py:137`) safely bypasses XML DOM parsing by using regex `re.findall(r"<loc>\s*(https?://[^<\s]+)\s*</loc>", text)` for sitemap extraction, preventing XML entity expansion attacks.

---

## 7. Architectural Strengths & Positive Findings

1. **Zero-Fabrication Event Logging Boundary**:
   In `server.py:44-100`, every tool invocation is mediated by `_recorded_operation()`, recording truthful lifecycle states (`attempted`, `success`, `blocked`, `failed`) into SQLite WAL `cache/operation_events.db`. Verified by `test_v14_server_event_wiring.py`.
2. **Strict SSRF Boundary Protection**:
   Both `security.py` (root) and `src/weblens/net/ssrf.py` maintain exhaustive IP blocking (RFC 1918, link-local, cloud metadata `169.254.169.254`, IPv6 loopback and ULA). Verified in `tests/test_both_stack_comparison.py:123-159`.
3. **Controlled Browser Sandboxing**:
   `browser_agent.py` and `src/weblens/net/browser_proxy.py` enforce permission levels, URL domain validation, egress proxying, and resource abort filters (preventing media/font downloads).
4. **Token Budget Gate Compliance**:
   All three stacks strictly enforce token limits, verified by `test_mcp_token_tax_gate` (<800 tokens for tool schemas) and `test_search_both_stacks_same_query`.

---

## 8. Prioritized Recommendations for Consolidation

| Priority | Issue | Recommended Action | Target File(s) |
| :--- | :--- | :--- | :--- |
| **P0 (Immediate)** | `NameError: os` in `src/engine/extract/extractor.py` | Add `import os` at top of file to prevent runtime crash on WAF fallback. | `src/engine/extract/extractor.py:124` |
| **P0 (Immediate)** | XML Entity Expansion Vulnerabilities (B314) | Replace `ET.fromstring` with `defusedxml.ElementTree` or safe regex. | `src/engine/crawl/mapper.py:45`, `src/engine/search/bing_provider.py:122` |
| **P1 (High)** | Expand `CORE_MODULES` in Static Tests | Update `test_01_static_and_deps.py` to audit `src/engine/` and `src/weblens/` alongside root modules. | `tests/test_01_static_and_deps.py:17` |
| **P1 (High)** | Resolve Package Script Entrypoint | Update `pyproject.toml` to point `web-intel-mcp` to root `server:main` (or unify into `src/`). | `pyproject.toml:57` |
| **P2 (Medium)** | Remove Cross-Package Coupling | Move `BrowserEgressProxy` into a shared network package or decouple `browser_fallback.py`. | `src/engine/extract/browser_fallback.py:47-52` |
| **P2 (Medium)** | Harmonize Schema Contracts | Standardize `ChunkResult` fields (`section` vs `section_title`) across `schemas.py` and `src/engine/schemas.py`. | `schemas.py:20`, `src/engine/schemas.py:21` |
| **P3 (Cleanup)** | Consolidate Duplicate Stacks | Document the relationship between Root V14 and `src/weblens/` or migrate root modules into a unified `src/` package. | Root repository structure |
