# Environment Inventory

**Generated**: 2026-10-24T09:33:00Z  
**Auditor**: Independent Evaluation Lead  
**Machine**: ACER Laptop, Windows 11  

---

## 1. Hardware

| Component | Value |
|---|---|
| OS | Microsoft Windows 11 Home Single Language (Build 26300) |
| CPU | Intel Core 5 210H — 8 cores / 12 logical processors |
| RAM | 16,072 MB (~16 GB) |
| GPU | NVIDIA GeForce RTX 3050 6GB Laptop GPU (6144 MiB VRAM) |
| Disk | 238 GB free / 475 GB total (C:) |

## 2. Runtime Environment

| Tool | Version | Status |
|---|---|---|
| Python | 3.13.15 | ✅ Installed |
| Node.js | v24.19.0 | ✅ Installed |
| pip/uv | uv (via uv.lock) | ✅ Configured |
| Git | Present | ✅ Single commit (`b531618`) |

## 3. Browsers

| Browser | Version | Path | Status |
|---|---|---|---|
| Google Chrome | 155.0.8059.86 | `C:\Program Files\Google\Chrome\Application\chrome.exe` | ✅ Installed |
| Microsoft Edge | 155.0.4283.62 | `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` | ✅ Installed |
| Playwright Chromium | Installed in both root and weblens venvs | N/A (managed by Playwright) | ✅ Available |

## 4. API Keys & Credentials (Redacted)

| Key | Status | Length |
|---|---|---|
| TAVILY_API_KEY | ✅ SET | 57 chars |
| BRAVE_SEARCH_API_KEY | ❌ EMPTY | — |
| EXA_API_KEY | ❌ EMPTY | — |
| SEARXNG_BASE_URL | ❌ EMPTY (root .env) | — |
| DEFAULT_SEARCH_PROVIDER | SET | "ddgs" |

**Security Scan**: No API keys found in git history or `.env.example` files. ✅ PASS

## 5. External Services

| Service | Endpoint | Status |
|---|---|---|
| SearXNG | `http://localhost:8080` | ✅ Reachable (HTTP 200), but JSON API returns 403 (needs config fix) |
| Ollama | N/A | ❌ Not installed |
| LM Studio | `http://localhost:1234` | ❌ Not reachable |
| Tavily API | `https://api.tavily.com` | ✅ Key configured |

## 6. Project Structure

The workspace contains **two stacks**:

### Stack A: "WebIntel" (root `src/`)
- **Entry point**: `src.server.mcp_server:main`
- **Search providers**: Bing (HTML scrape), Wikipedia REST, DuckDuckGo (ddgs lib + HTML fallback), Brave API, SearXNG, Tavily API
- **Extraction**: Trafilatura + BeautifulSoup + PyMuPDF (PDF) + headless Edge/Chrome DOM dump
- **Research**: Multi-query sub-query decomposition engine
- **Crawling**: Bounded recursive crawler with robots.txt, cycle detection
- **Mapping**: Sitemap XML + link discovery
- **Security**: SSRF protection with DNS resolution, streaming byte limits, prompt injection detection
- **Token management**: tiktoken `o200k_base`, strict budgets
- **MCP**: 5 tools (web_search, extract_url, crawl_website, web_map, deep_research)

### Stack B: "WebLens" (in `weblens/`)
- Separate `pyproject.toml` with hatchling build
- Own search, extract, crawl, research, security, caching modules
- Playwright as optional dependency for browser rendering
- More mature configuration (pydantic-settings, structured error handling)
- Own benchmark infrastructure with SQLite cache

## 7. Existing Tests

**Root `tests/` directory** (18 test files):
- `test_security.py` — SSRF and private IP blocking
- `test_extract.py` — Extraction and BM25 passage grounding
- `test_search.py` — Search provider tests
- `test_search_engine.py` — Dedup, ranking, domain diversity
- `test_mcp_protocol.py` — MCP tool registration
- `test_mcp_e2e.py` — End-to-end MCP roundtrips
- `test_mcp_stress.py` — MCP load tests
- `test_ssrf_penetration.py` — Penetration testing for SSRF
- `test_injection_sanitization.py` — Prompt injection defense
- `test_edge_fuzz.py` — Edge case fuzzing
- `test_cache.py` — Cache correctness
- `test_crawler.py` / `test_crawler_traps.py` — Crawl logic
- `test_both_stack_comparison.py` — Cross-stack comparison
- `test_failure_injection.py` — Fault injection
- `test_load_stress.py` — Load/stress testing
- `test_token_boundaries.py` — Token budget enforcement

## 8. Existing Benchmarks

- **Dataset**: `benchmarks/eval_dataset.json` (50 queries), `eval_dataset_expanded.json` (larger)
- **Runner**: `benchmarks/run_benchmarks.py` with `benchmark_harness.py`
- **Baseline results**: `reports/baseline_benchmark_results.json`
  - Schema tokens: 680 (o200k), 655 (cl100k)
  - Search p50: 3.06s, p95: 9.94s
  - Extract p50: 5.91s, p95: 10.89s
  - Answer support rate: 40% (16/40) — **fails gate**
  - False confidence rate: 20% (2/10) — **fails gate**
  - Precision@5: 0.694

## 9. Known Issues (from baseline)

1. **Answer support rate is 40%** — well below the 60% gate
2. **False confidence rate is 20%** — above the 15% gate
3. **Search latency p95 is ~10s** — excessive for real-time use
4. **SearXNG JSON API returns 403** — needs configuration fix
5. **No conflict detection** — deep research does not detect contradictions effectively
6. **Browser fallback is basic** — subprocess-based Chrome/Edge DOM dump, no Playwright integration in Stack A
7. **No persistent test database** — results stored only as JSON files
8. **Two separate stacks** — WebIntel (root) and WebLens (weblens/) with significant code duplication

## 10. Meta/Spark/Other Integrations

- **Meta browser**: No Meta browser product found installed. No Meta-related extensions or integrations discovered in the project configuration.
- **Spark**: No Spark-related components found. No references in project files, configs, or installed extensions.
- **Browser extensions**: Not inspected (privacy constraint — never attach to personal browser profiles).

> [!NOTE]
> These items are marked as **UNIDENTIFIED**. The user should clarify if they refer to specific products.
