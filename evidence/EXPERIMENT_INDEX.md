# WebLens Experiment & Evaluation Index

## 1. Overview & Protocol

This index catalogs every empirical experiment, benchmark run, security assessment, and scoring calibration conducted across the WebLens platform lifecycle.

Each experiment adheres to strict preregistration and ledger anchoring:
- Hypotheses and scoring metrics are registered prior to evaluation execution.
- Outputs, stdout traces, and JSON summaries are preserved on disk with cryptographic SHA-256 hashes recorded in `evidence/ledger.jsonl`.
- Regressions trigger immediate rejection; improvements require independent confirmation before adoption.

---

## 2. Chronological Experiment Registry

| Experiment ID | Date | Commit | Objective / Hypothesis | Baseline | Results | Decision | Key Artifacts |
|---|---|---|---|---|---|---|---|
| **EXP-001** | 2026-11-01 | `a9bd964` | Establish isolated sandbox environment with Docker container isolation. | Local host processes | Isolated container environment verified with zero host pollution. | **KEEP** | `weblens-lab/sandbox/` |
| **EXP-002** | 2026-11-01 | `a9bd964` | Evaluate SSRF socket-level IP filter against 38 adversarial IPv4/IPv6 probe vectors. | Standard HTTP client | 38/38 SSRF vectors blocked (100% defense rate). | **KEEP** | `tests/test_ssrf_penetration.py` |
| **EXP-003** | 2026-11-01 | `a9bd964` | Optimize MCP server tool schemas to reduce client context window consumption. | Unbounded tool schemas | Reduced to 732 cl100k tokens across 4 tools (<1,000 token limit). | **KEEP** | `src/weblens/mcp_server.py` |
| **EXP-004** | 2026-11-01 | `a9bd964` | Test multi-provider search failover across keyless engines (DDG, Bing, Wikipedia). | Single provider (DDG) | Zero-downtime failover verified when DDG triggers rate limits. | **KEEP** | `src/weblens/search/router.py` |
| **EXP-005** | 2026-11-01 | `a9bd964` | Evaluate table extraction and Markdown conversion on 20 complex HTML tables. | Raw text flattening | 20/20 tables correctly converted to GitHub-flavored Markdown. | **KEEP** | `tests/test_extract.py` |
| **EXP-006** | 2026-11-01 | `a9bd964` | Evaluate crawler trap defense against calendar loops and infinite query parameters. | Default recursive crawl | Terminated loops safely at depth <= 3 and pages <= 30. | **KEEP** | `tests/test_crawler_traps.py` |
| **EXP-007** | 2026-11-01 | `a9bd964` | Implement formula injection defense in tabular CSV spreadsheet exports. | Raw CSV generation | Defanged cells prepended with single quotes (`'`). | **KEEP** | `src/weblens/apps/sheets.py` |
| **EXP-008** | 2026-11-01 | `a9bd964` | Pre-commit secret scanning and canary token leak detection. | Unaudited repo | 0 API credentials or canary tokens leaked across 92 files. | **KEEP** | `tests/test_p9_canary_secrets.py` |
| **EXP-V9A** | 2026-11-02 | `1c11ac3` | Deploy WebLens to Google Cloud Run and verify remote MCP SSE endpoint. | Local host only | Cloud Run revision `weblens-00003-l9q` operational with 13 tools. | **KEEP** | `https://weblens-16131012091.us-central1.run.app/mcp` |
| **EXP-V9B** | 2026-11-02 | `475a6ff` | Three-System comparative evaluation across 100 queries (Local, Deployed, Tavily). | Theoretical estimate | Deployed WebLens achieved 1,112.1 ms p50 latency vs Tavily 2,381.6 ms. | **KEEP** | `reports/three-system-comparison/raw-v9b-2026-11-02/` |
| **EXP-V10A** | 2026-11-02 | `21faa32` | Four-System evaluation including Google Gemini API adapter and 120 queries. | Three-system baseline | Gemini integration verified; 120-query evaluation completed. | **KEEP** | `reports/three-system-comparison/` |
| **EXP-V10-SC** | 2026-11-02 | `21faa32` | Preregister and execute corrected scoring harness (PREREG-V10-001). | Flawed token > 3 scorer | Short tokens (H2O, 405, Au) correctly scored; dynamic items validated. | **KEEP** | `evidence/prereg-v10-001-scoring-fix.md` |
| **EXP-V11-AUTH** | 2026-11-02 | `1209abb` | Institutional domain authority weighting and query comparison normalization. | Static authority list | Added `.gov.in`, `.gov.uk`, `rtings.com`, `worldbank.org`; 252 tests pass. | **KEEP** | `docs/SEARCH_QUALITY_STRATEGY.md` |

