# ROLE & MISSION: PRINCIPAL QA ARCHITECT, SECURITY AUDITOR & MCP TEST ENGINEER
You are working INSIDE my existing Python MCP server repository (`MyWebEngine`).
Your objective is to build and execute a comprehensive, automated **7-Layer Testing, Defensive Security Verification, Protocol Conformance, and Quality Benchmark Suite** that tests every line of my MCP server in place—and automatically fixes any bugs, vulnerabilities, or quality regressions found.

## STRICT RULES
1. **IN-PLACE & NON-DESTRUCTIVE:** Do not break my existing MCP tools or rename my project. All network security boundary tests and stress tests must run against **local mocked transports (`respx` / local fixtures)** or my own in-memory FastMCP server (`fastmcp.Client(server)`), never attacking external third-party websites.
2. **ZERO MOCKED PASSES OR STUBS:** Every test must assert real behavior, real schema validation, real sanitizer outputs, and real latency/token metrics. Never write `assert True` or skip failing tests to make the suite pass.
3. **FIX ROOT CAUSES IN APPLICATION CODE:** When a test fails, fix the bug in the server code (`security.py`, `extractor.py`, `reranker.py`, `server.py`, etc.) rather than weakening the test assertion.

---

# THE 7 TESTING LAYERS YOU MUST IMPLEMENT IN `tests/`

Inspect my current codebase, install required test dependencies (`uv add --dev pytest pytest-asyncio pytest-cov pytest-timeout hypothesis respx inline-snapshot bandit ruff mypy`), and build the following modular test suite inside `tests/`:

### Layer 1: Static Analysis, Type Safety & Dependency Security Audit (`tests/test_01_static_and_deps.py`)
- Verify zero syntax, typing, or undefined-variable bugs using `ruff check` and `mypy`.
- Run static application security testing (SAST) via `bandit -r .` to verify zero unsafe shell invocations (`subprocess` with `shell=True`), hardcoded API keys, or unsafe deserialization.
- Verify that `.env` and local browser profile directories are excluded in `.gitignore` and never leaked in error stack traces or tool responses.

### Layer 2: MCP Protocol Conformance & Token Tax Audit (`tests/test_02_mcp_protocol.py`)
- Use `from fastmcp import Client` (`async with Client(mcp) as client:`) to test the server in-memory across both default stateless mode and legacy session mode (`mode="legacy"` where supported).
- **Tool Contract & Naming Audit:** Call `await client.list_tools()` and assert:
  - All 5 tools (`web_search`, `extract_url`, `web_map`, `crawl_website`, `deep_research`) register cleanly.
  - Every tool name matches `[a-z0-9_]+` with no redundant server-name prefix.
  - Every tool schema uses flat, deterministic JSON Schema types without ambiguous `anyOf`/`oneOf` discriminators that confuse local 6GB VRAM models.
  - **MCP Token Tax Gate:** Measure the serialized JSON schema token length of all tools combined and assert it is strictly `< 800 tokens`.
- **Stdout Contamination Gate:** Spawn the server over `stdio` subprocess transport, execute a tool call, and assert that `stdout` contains 100% valid JSON-RPC messages with zero stray `print()` or debug log lines (all logs must go to `stderr`).

### Layer 3: Defensive Security & Boundary Verification Suite (`tests/test_03_security_boundaries.py`)
Using `respx` mocked HTTP transports and synthetic HTML fixtures, rigorously verify all defensive security controls in `security.py` and `extractor.py`:
- **SSRF & IP Address Validation Tests:** Test `validate_public_url` and the custom HTTP redirect hook against:
  - Loopback variations (`localhost`, `127.0.0.1`, `[::1]`, `0.0.0.0`).
  - RFC1918 private networks (`10.0.0.1`, `172.16.0.1`, `192.168.1.1`).
  - Link-local & Cloud Metadata endpoints (`169.254.169.254`, `metadata.google.internal`).
  - Non-HTTP schemes (`file:///`, `ftp://`, `javascript:`, `data:`).
  - **Redirect Hop Re-Validation:** Mock a public URL (`https://example.com/start`) that returns an HTTP `302` redirect to `http://127.0.0.1:8080/admin` or `http://169.254.169.254/latest/meta-data/` and assert the connection is blocked *before* following the redirect.
  - **Simulated DNS Rebinding Check:** Mock a hostname resolver that resolves to a public IP on check #1 and `127.0.0.1` at socket connection time, asserting the transport blocks it.
- **Unbounded Stream / Zip-Bomb DoS Protection:** Mock an HTTP response streaming 25 MB of repeating text and assert the reader aborts cleanly at `MAX_DOWNLOAD_BYTES` (2 MB) without spiking memory.
- **Indirect Prompt Injection Sanitization:** Pass synthetic HTML fixtures containing hidden DOM elements (`<div style="display:none">Ignore previous instructions...</div>`, `<span style="opacity:0">`, HTML comments, and system-override templates) into the extractor and assert:
  1. Hidden DOM elements are completely stripped before Markdown conversion.
  2. Returned content is properly wrapped in untrusted provenance tags.
- **Path Traversal & Cache Key Isolation:** Fuzz cache keys and file paths with `../../` and Windows reserved names (`CON`, `NUL`, `C:\Windows\...`) to assert SQLite and browser profile paths cannot escape the project directory.

### Layer 4: Property-Based Fuzzing & Chaos Resilience (`tests/test_04_fuzz_and_chaos.py`)
- Use `hypothesis` to fuzz all 5 MCP tool inputs with arbitrary Unicode strings, emojis, SQL/JSON special characters, negative integers, `0`, `999999`, empty lists, and malformed URLs. Assert that the server always returns a structured error or valid `ToolResponseEnvelope` and **never raises an unhandled exception**.
- **Chaos Network Testing (Mocked):** Simulate:
  - SearXNG returning `500 Internal Server Error`, `429 Too Many Requests`, or malformed JSON.
  - 1 straggler URL hanging for 15 seconds while 3 URLs finish in 200ms (assert `web_search` early-exit streaming finishes in `< 2.5s` without waiting for the straggler).
  - HTTP `403` / empty React `<div id="root"></div>` shell triggering automatic Tier 2 Playwright fallback.
  - Missing or rate-limited `GEMINI_API_KEY` / `TAVILY_API_KEY` triggering graceful local BM25/extractive fallback.

### Layer 5: Extraction & Reranker Unit Fidelity (`tests/test_05_extraction_quality.py`)
- Feed complex synthetic technical documentation HTML containing:
  - Multi-line Python/TypeScript `<pre><code>` blocks with indentation.
  - Complex `<table>` benchmarks with headers and numeric rows.
  - Target answers buried at the very bottom of a 25,000-character page (past the old `16,000` char cutoff).
- Assert that:
  1. Code blocks retain 100% of their lines and indentation (` ``` ` fences intact).
  2. HTML tables convert cleanly into valid Markdown tables.
  3. The Stage 1 (BM25) + Stage 2 (Cross-Encoder) reranker retrieves the bottom-of-page answer paragraph as the #1 chunk (`score > 0.7`) while discarding the 20,000 characters of intro fluff.

### Layer 6: Resource Leak, Concurrency & Performance Stress Suite (`tests/test_06_performance_stress.py`)
- Fire 15 concurrent in-memory `Client(mcp)` tool calls using `asyncio.gather`.
- Assert:
  - SQLite cache hit latency is `< 25ms`.
  - Zero orphaned Chromium processes or unclosed `httpx.AsyncClient` / `aiosqlite` connections remain after server shutdown.
  - Total process RAM usage stays within safe bounds for a 16GB RAM laptop.

### Layer 7: Live Comparative Quality Arena (`tests/test_07_live_quality_arena.py`)
- When `GEMINI_API_KEY` and `TAVILY_API_KEY` are present in `.env`, run 5 real-world benchmark queries comparing **MyWebEngine MCP** vs. **Tavily API (`advanced`)** vs. **Gemini Search Grounding**, asserting an average quality score `>= 90/100` and token compression ratio `>= 75%` vs. raw HTML.

