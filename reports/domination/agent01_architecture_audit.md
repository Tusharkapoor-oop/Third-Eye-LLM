# Agent 01: Repository Architecture, Package Boundaries, and Mirror Synchronization Audit

## Executive Summary

- Root Decision: Consolidate the repository under the canonical WebLens domain architecture (`src/weblens`) and eliminate legacy shadow implementations (`webintel`, root-level duplicate modules, and dead scratch files).
- Critical Defect Identified: A silent divergence exists between `src/weblens/extract/passages.py` (7,633 bytes) and `weblens/src/weblens/extract/passages.py` (8,177 bytes). Commit `800a4cc0cadfbe4ce8cb0334721bb6f9ec7069f1` added `spread_chunks()` to `weblens/`, but left `src/weblens/` unpatched. In the active virtual environment, `import weblens` resolves to `src/weblens`, meaning `spread_chunks` is missing in local execution (`hasattr(...) == False`).
- Architectural Tri-State: The repository maintains three separate server implementations:
  1. `server.py` (root): FastMCP "MyWebEngine" MCP server wiring 15 tools against root modules (`extractor.py`, `crawl_engine.py`, etc.).
  2. `src/server/mcp_server.py`: Registered CLI entry point `web-intel-mcp` in root `pyproject.toml:58`, importing from `src/engine/`.
  3. `src/weblens/mcp_server.py`: Canonical WebLens server deployed in Cloud Run (`Dockerfile:43`), importing from `src/weblens/`.
- Test Verification: `.\.venv\Scripts\pytest -q tests/test_01_static_and_deps.py tests/test_both_stack_comparison.py` ran with 100% pass rate (8 passed in 77.68s).

---

## 1. Pytest Empirical Execution Evidence

### 1.1 Test Invocation
- Environment: Windows 11, Python 3.14.0, pytest-9.1.1, pluggy-1.7.0.
- Executable: `C:\Users\ACER\Downloads\Broswer for ai agnets\.venv\Scripts\pytest.exe`.
- Command:
  ```powershell
  .\.venv\Scripts\pytest -q tests/test_01_static_and_deps.py tests/test_both_stack_comparison.py
  ```
- Output:
  ```text
  ........                                                                 [100%]
  8 passed in 77.68s (0:01:17)
  ```

### 1.2 Granular Execution Timings and Latencies
Command executed:
```powershell
.\.venv\Scripts\pytest -v tests/test_01_static_and_deps.py tests/test_both_stack_comparison.py --durations=0
```

Observed Latencies:
| Test Name | File | Duration | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `test_search_both_stacks_same_query` | `tests/test_both_stack_comparison.py:35` | 49.75s call (+ 6.89s teardown) | PASSED | Executes live dual-engine queries across DuckDuckGo, Bing, and Wikipedia. |
| `test_core_module_import_integrity` | `tests/test_01_static_and_deps.py:76` | 12.29s call | PASSED | Imports all root singletons (`server`, `config`, `schemas`, `security`). |
| `test_bandit_sast_security` | `tests/test_01_static_and_deps.py:39` | 3.02s call | PASSED | Bandit scan detected 0 High and 0 Medium issues on 11 root core modules. |
| `test_extract_both_stacks_same_url` | `tests/test_both_stack_comparison.py:74` | 1.73s call | PASSED | Real-world extraction test on `https://www.python.org/about/`. |
| `test_ruff_lint_cleanliness` | `tests/test_01_static_and_deps.py:32` | 0.53s call | PASSED | Ruff lint check passed with 0 errors across 11 root core modules. |
| `test_canary_secrets_leak_prevention` | `tests/test_01_static_and_deps.py:58` | 0.07s call | PASSED | Validates no secret token leakage in `FailedItem` serialization. |
| `test_ssrf_both_stacks_block` | `tests/test_both_stack_comparison.py:124` | 0.05s call | PASSED | Confirms loopback/metadata SSRF blocking in both engines. |
| `test_gitignore_protects_secrets_and_profiles` | `tests/test_01_static_and_deps.py:46` | < 0.01s call | PASSED | Confirms `.gitignore` coverage for `.env`, `*.db`, `.venv`. |

Total: 8 passed in 79.65s (0:01:19). Zero failures, zero warnings suppressed as errors.

---

## 2. Canonical Package Boundaries & Three-Stack Architecture

The repository exhibits an evolutionary stratification consisting of three distinct package domains:

```
+----------------------------------------------------------------------------------------------------+
|                                    REPOSITORY ROOT & ENTRY POINTS                                  |
+----------------------------------------------------------------------------------------------------+
       |                                       |                                      |
       v                                       v                                      v
+-----------------------------+ +-----------------------------+ +------------------------------------+
|           STACK 1           | |           STACK 2           | |              STACK 3               |
|      Root / Legacy App      | |      src/engine Package     | |     src/weblens & weblens/         |
+-----------------------------+ +-----------------------------+ +------------------------------------+
| - Entry: server.py          | | - Entry: src/server/        | | - Entry: src/weblens/mcp_server.py |
| - Modules: *.py in root     | |   mcp_server.py             | | - CLI: weblens.cli:main            |
|   (extractor.py, config.py, | | - pyproject.toml:58         | | - Container: Dockerfile:43         |
|    crawl_engine.py, etc.)   | |   (web-intel-mcp)           | | - Self-contained architecture:     |
| - MCP Server: MyWebEngine   | | - Submodules:               | |   apps/, crawl/, extract/, net/,   |
| - FastMCP implementation    | |   crawl/, extract/,         | |   research/, search/, security/    |
| - 15 tools (5 core + 10 v14)| |   search/, research/        | | - 13 MCP tools (profile=full)      |
+-----------------------------+ +-----------------------------+ +------------------------------------+
```

### 2.1 Stack Analysis and Divergence

1. **Stack 1 (`server.py` + Root Modules)**
   - Location: `server.py`, `config.py`, `schemas.py`, `extractor.py`, `reranker.py`, `query_engine.py`, `search_pipeline.py`, `crawl_engine.py`, `research_engine.py`, `cache.py`, `security.py`, `event_store.py`, `geo_mapper.py`, `document_generator.py`, `model_provider.py`, `browser_agent.py`, `quality_arena.py`.
   - Entry Point: `server.py:385` (`if __name__ == "__main__": main()`).
   - Coupling: `server.py` directly imports root modules using unqualified names (`from config import CONFIG` at `server.py:29`, `from extractor import TieredExtractor` at `server.py:32`).
   - Tool Surface: Exposes 5 core tools (`web_search`, `extract_url`, `web_map`, `crawl_website`, `deep_research`), plus 10 opt-in v14 tools under `WEBLENS_V14_EXTENDED_TOOLS=1` (`browser_*`, `geo_resolve`, `generate_document`, `dashboard_metrics`).

2. **Stack 2 (`src/engine/` + `src/server/mcp_server.py`)**
   - Location: `src/engine/` (`crawl/`, `extract/`, `research/`, `search/`, `config.py`, `query_engine.py`, `reranker.py`, `schemas.py`, `security.py`) and `src/server/mcp_server.py`.
   - Entry Point: Configured in `pyproject.toml:58` (`web-intel-mcp = "src.server.mcp_server:main"`).
   - Package Boundary Leakage: `src/engine` is NOT self-contained. It violates domain separation by importing from `weblens`:
     - `src/engine/security.py:202`: `from src.weblens.security.injection import scan_injection`
     - `src/engine/extract/browser_fallback.py:48-52`: imports `BrowserEgressProxy` from `weblens.net.browser_proxy` and `src.weblens.net.browser_proxy`.
   - Internal Divergence from Root: Root modules were originally copied or derived from `src/engine/`, but have since diverged:
     - `schemas.py`: 7,645 bytes (root) vs 2,356 bytes (`src/engine/schemas.py`).
     - `extractor.py`: 14,694 bytes (root) vs 21,226 bytes (`src/engine/extract/extractor.py`).
     - `crawl_engine.py`: 14,792 bytes (root) vs 6,245 bytes (`src/engine/crawl/crawler.py`).
     - `search_pipeline.py`: 17,077 bytes (root) vs 22,286 bytes (`src/engine/search/aggregator.py`).

3. **Stack 3 (`src/weblens/` & `weblens/` Subproject)**
   - Location: `src/weblens/` and `weblens/src/weblens/`.
   - Entry Point: `weblens.cli:main` (`weblens/pyproject.toml:41`).
   - Production Deployment: `Dockerfile:39-43` explicitly designates this as the canonical production server:
     ```dockerfile
     # Run the canonical WebLens MCP server (weblens package), not the legacy root app.
     # The deployed revision before this change was also the weblens package; the
     # root server.py is the older MyWebEngine demo and must not silently replace it.
     CMD ["sh", "-c", "exec python -m weblens.cli serve --http --host 0.0.0.0 --port ${PORT:-8080} --profile full --allow-insecure"]
     ```
   - Self-Containment: `src/weblens` imports zero code from `src/engine`, `webintel`, or root modules.

---

## 3. Mirror Synchronization Audit: `weblens/` vs `src/weblens/`

### 3.1 Python Package Comparison (`src/weblens/` vs `weblens/src/weblens/`)
Automated byte-level diff across all 46 Python files yielded exactly ONE file out of sync:

```text
DIFF: src/weblens\extract\passages.py != weblens/src/weblens\extract\passages.py
(All other 45 Python modules match byte-for-byte)
```

### 3.2 Exact Code Divergence in `extract/passages.py`
Git Diff (`git diff --no-index src/weblens/extract/passages.py weblens/src/weblens/extract/passages.py`):
```diff
diff --git a/src/weblens/extract/passages.py b/weblens/src/weblens/extract/passages.py
index 1a5759d..a4df2b0 100644
--- a/src/weblens/extract/passages.py
+++ b/weblens/src/weblens/extract/passages.py
@@ -121,6 +121,21 @@ def _chunk(idx: int, start: int, end: int, text: str, heading: str | None) -> Ch
     return Chunk(idx=idx, start=start, end=end, text=text, heading=heading, tokens=toks, tf=tf)
 
 
+
+
+def spread_chunks(chunks: list[Chunk], limit: int) -> list[Chunk]:
+    """Evenly spaced chunks including the first and last.
+
+    Used when no query is supplied so that facts near the tail of a long page
+    remain reachable without query guidance.
+    """
+    if limit <= 0 or len(chunks) <= limit:
+        return chunks
+    if limit == 1:
+        return [chunks[0]]
+    indices = sorted({round(i * (len(chunks) - 1) / (limit - 1)) for i in range(limit)})
+    return [chunks[i] for i in indices]
+
 def score_chunks(chunks: list[Chunk], query: str, title: str = "") -> None:
     """Annotate chunk scores in place. Not exposed to callers."""
     terms, phrases = query_terms(query)
@@ -192,7 +207,7 @@ def select_passages(
         pool = full if full else [c for c in chunks if getattr(c, "_coverage", 0.0) > 0]
         ordered = sorted(pool, key=lambda c: (-getattr(c, "_score", 0.0), c.idx))
     else:
-        ordered = chunks
+        ordered = spread_chunks(chunks, max_passages)
         best_cov = 0.0
 
     selected: list[Chunk] = []
```

### 3.3 Root Cause and Runtime Consequence
- Originating Commit: Commit `800a4cc0cadfbe4ce8cb0334721bb6f9ec7069f1` ("feat(release): upgrade WebLens v14/v9 engine...") modified `weblens/src/weblens/extract/passages.py` to add `spread_chunks()`, but neglected to copy or apply the patch to `src/weblens/extract/passages.py`.
- Runtime Collision:
  Empirical check in the project virtual environment (`.\.venv\Scripts\python.exe`):
  ```python
  import weblens.extract.passages
  print(weblens.extract.passages.__file__)
  # Outputs: C:\Users\ACER\Downloads\Broswer for ai agnets\src\weblens\extract\passages.py
  print(hasattr(weblens.extract.passages, 'spread_chunks'))
  # Outputs: False
  ```
- Impact: In local execution, test suites importing `weblens` or `src.weblens` do not receive tail-passage preservation for non-query extraction requests. Only the Docker container (which installs `./weblens` via `Dockerfile:29`) gets the updated behavior.

### 3.4 Divergence Across Ancillary Directories
The outer `weblens/` folder functions as an independent shadow monorepo:
1. `weblens/tests/` (17 test files) vs `tests/` (35 test files):
   - 14 test files exist ONLY in `weblens/tests/` (`test_browser_optional.py`, `test_browser_proxy.py`, `test_config.py`, `test_crawl.py`, `test_http_auth.py`, `test_mcp.py`, `test_passages.py`, `test_research.py`, `test_search_parsing.py`, `test_search_router.py`, `test_service.py`, `test_ssrf.py`, `test_tokens.py`, `test_urls.py`).
   - `test_cache.py`, `test_extract.py`, and `conftest.py` have divergent implementations between `tests/` and `weblens/tests/`.
2. `weblens/docs/`:
   - Contains 8 ADRs (`0001` through `0008`) and design specs (`CLIENTS.md`, `COMPARISON.md`, `LIMITATIONS.md`, `MEASUREMENTS.md`, `PROTOCOL.md`, `RESEARCH.md`) completely absent from root `docs/`.
3. `weblens/benchmarks/`:
   - Contains 10 benchmark runners and 16 historical JSON/MD run results from October 2026 not present in root `benchmarks/`.

---

## 4. Dead Code, Duplicated Code, and Technical Debt Inventory

An empirical file scan identified significant non-canonical, dead, and duplicate artifacts:

### 4.1 Dead Code and Leftover Artifacts
| File Path | Size | Reason for Classification |
| :--- | :--- | :--- |
| `src/engine/search/aggregator.py.bak` | 12,462 bytes | Orphaned backup file left in source directory. |
| `src/engine/extract/fix_chunker.py` | 7,960 bytes | Unreferenced experimental chunker. Its logic was already merged into `src/engine/extract/chunker.py`. Never imported anywhere in repo. |
| `test_answers.py` | 1,435 bytes | Root-level scratch script containing hardcoded Windows absolute paths (`sys.path.insert(0, r'C:\Users\ACER\...')`). |
| `test_answers2.py` | 1,752 bytes | Root-level scratch script with hardcoded Windows absolute paths. |
| `test_chunks.py` | 3,365 bytes | Root-level scratch script testing `fix_chunker` vs `chunker` with hardcoded Windows absolute paths. |
| `test_count8.py` | 1,279 bytes | Root-level scratch script testing `count=8` query performance with hardcoded Windows absolute paths. |
| `omni-web-mcp/` | Directory | Abandoned skeleton package containing only `.env.example`, `pyproject.toml`, and `.ruff_cache`. No source code. |
| `legacy/weblens_tests/` | 5 files | Stale test duplicates (`test_passages.py`, `test_search_parsing.py`, `test_ssrf.py`, `test_tokens.py`, `test_urls.py`). |
| `deploy_v10.log` | 43,916 bytes | Leftover deployment console log in root. |
| `deploy_v10b.log` | 5,820 bytes | Leftover deployment console log in root. |
| `modelcontextprotocol-server-2.3.1.tgz` | 1,537,977 bytes | Unpacked NPM/tarball archive in repository root. |

### 4.2 Large-Scale Code Duplication: `webintel/` Package
The `webintel/` directory contains 19 Python modules (~150 KB of code):
- Files: `authority.py`, `cache.py`, `config.py`, `crawl.py`, `extract.py`, `extractor.py`, `http_client.py`, `limits.py`, `query_engine.py`, `ranking.py`, `reranker.py`, `research.py`, `research_engine.py`, `schemas.py`, `search_pipeline.py`, `security.py`, `server.py`, `utils.py`, `__init__.py`, `__main__.py`, plus `search/` subproviders (`base.py`, `bing_rss.py`, `brave.py`, `engine.py`, `searxng.py`, `tavily.py`).
- Active Usage: Only 3 test files in the entire test suite import `webintel`:
  - `tests/test_cache.py:1`
  - `tests/test_mcp_e2e.py:10`
  - `tests/test_search_engine.py:10`
- No CLI entry point, Dockerfile, or production service utilizes `webintel`. It represents an abandoned intermediate fork between the original `weblens` and the current engine.

---

## 5. Architectural Recommendations

1. **Immediate Mirror Remediation:**
   Sync `spread_chunks()` and the `select_passages()` update from `weblens/src/weblens/extract/passages.py` into `src/weblens/extract/passages.py` so local runs match the container behavior.
2. **Eliminate Dead Files:**
   Delete `src/engine/search/aggregator.py.bak`, `src/engine/extract/fix_chunker.py`, `test_answers.py`, `test_answers2.py`, `test_chunks.py`, `test_count8.py`, `omni-web-mcp/`, `deploy_v10*.log`, and `modelcontextprotocol-server-2.3.1.tgz`.
3. **Canonicalize Package Boundaries:**
   - Enforce `src/weblens` as the primary, authoritative WebLens implementation.
   - Remove duplicate files in `webintel/` and migrate tests in `tests/test_cache.py`, `test_mcp_e2e.py`, and `test_search_engine.py` to canonical `src/weblens` or `src/engine` APIs.
   - Isolate `src/engine` dependencies or formally merge `src/engine` and `src/weblens` to avoid cross-stack coupling in `security.py` and `browser_fallback.py`.
4. **Subproject De-duplication:**
   Resolve the split between root `.` and the nested `weblens/` subdirectory by deciding whether `weblens/` remains an exportable distribution tree or should be consolidated into the root workspace.
