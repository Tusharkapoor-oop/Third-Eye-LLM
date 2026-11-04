# AUTONOMOUS TEST, SECURITY AUDIT & SELF-HEALING LOOP CONTROLLER

Do NOT summarize or ask for permission. Execute this 4-step verification and remediation loop right now in the terminal:

### STEP 1: COMPLETE ALL 7 TEST FILES
If any test file from Layer 1 through Layer 7 (`test_01` to `test_07`) is missing or incomplete, write the complete file right now with zero `# TODO` or skipped assertions.

### STEP 2: EXECUTE THE FULL TEST & SECURITY PIPELINE IN TERMINAL
Run the following commands sequentially and capture all output:
1. Static & Security Audit:
   `uv run ruff check .`
   `uv run bandit -r . -x ./tests,./.venv`
2. Unit, Protocol, Security Boundary, Fuzzing & Performance Suite:
   `uv run pytest tests/ -v --tb=short --cov=.`
3. Live Quality Arena (comparing against Tavily & Gemini API):
   `uv run pytest tests/test_07_live_quality_arena.py -s`

### STEP 3: ROOT-CAUSE TRIAGE & IN-PLACE CODE PATCHING
For EVERY failed test, security warning, timeout, or coverage gap discovered in Step 2:
- **Do NOT delete or weaken the test.**
- Trace the failure to the exact line in my server codebase (`security.py`, `extractor.py`, `reranker.py`, `query_engine.py`, `cache.py`, `server.py`) and fix the underlying bug:
  - If an SSRF redirect or DNS rebinding test failed -> harden the `httpx` event hook / socket validator in `security.py`.
  - If hidden prompt-injection text leaked into Markdown -> tighten DOM tree pruning before Markdown generation in `extractor.py`.
  - If `hypothesis` fuzzing triggered an unhandled exception -> add strict input normalization and error boundaries in `schemas.py` / `server.py`.
  - If a code block or table was mangled or bottom-of-page answer was missed -> fix the atomic chunk splitter and BM25/Cross-Encoder weights in `reranker.py`.
  - If tool schema tokens exceeded 800 tokens -> compress `@mcp.tool()` docstrings and parameter descriptions in `server.py`.

### STEP 4: RE-RUN UNTIL 100% GREEN & PRINT FINAL AUDIT SCORECARD
Re-run `uv run pytest tests/ -v --cov=.` after applying fixes.
Keep looping Steps 2 -> 3 -> 4 automatically until **100% of tests pass with zero warnings**.
Once 100% green, output a final **Engineering Verification Scorecard Table** showing:
- Total Tests Passed / Failed
- Code Coverage %
- Bandit Security Findings (must be 0 High/Medium)
- SSRF, Redirect, Byte-Cap & Prompt-Injection Defense Pass Rate (must be 100%)
- MCP Schema Token Tax (tokens)
- Cache Hit Latency (ms) & Live Search Latency (ms)
- Comparative Quality Score: MyWebEngine vs. Tavily vs. Gemini

Execute this loop now.

