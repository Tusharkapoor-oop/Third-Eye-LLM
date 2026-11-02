# WebLens Evidence-Backed Claim Ledger

## 1. Governance & Verification Standards

This ledger records every factual claim asserted regarding the WebLens platform, its components, security controls, and comparative performance against external commercial systems (Tavily Direct API and Google Gemini API).

In accordance with strict engineering standards, every claim is assigned exactly one verification status:
- **Verified:** Directly reproduced and confirmed by an automated test, cryptographic hash, or execution log in this repository.
- **Partially verified:** Confirmed in specific environments or on a subset of tests; further fleet validation is ongoing.
- **Not tested:** Hypothesized or designed, but not yet evaluated against an empirical benchmark.
- **Blocked:** Cannot be verified due to external dependency, missing network access, or environmental restriction.
- **Failed:** Empirical measurement failed to meet the specified threshold.
- **Rejected:** Hypothesis tested and deliberately discarded due to regressions or invalid design.
- **Inferred:** Derived analytically from other verified measurements rather than measured directly.

---

## 2. Complete Claims Registry

| Claim ID | Category | Claim Statement | Status | Evidence Location | Verification Command |
|---|---|---|---|---|---|
| **CLM-001** | Architecture | WebLens exposes 13 active tools under `--profile full` over MCP. | **Verified** | `src/weblens/mcp_server.py:46-270` | `pytest tests/test_mcp_protocol.py` |
| **CLM-002** | Security | Socket-level SSRF defense blocks all RFC 1918, loopback, link-local, and cloud metadata IPs. | **Verified** | `src/weblens/net/ssrf.py:30-110` | `pytest tests/test_ssrf_penetration.py` |
| **CLM-003** | Security | Prompt injection scanner blocks 35/35 adversarial instruction override vectors with 0% false positives. | **Verified** | `weblens/src/weblens/security/injection.py:12-45` | `pytest tests/test_injection_sanitization.py` |
| **CLM-004** | Security | Deployed Cloud Run instance blocks 10/10 remote penetration probes (SSRF, metadata, auth bypass). | **Verified** | `reports/deployed-security/deployed_security_results_v2.json` | `python weblens-lab/security_lab/run_security_audit_v2.py --deployed` |
| **CLM-005** | Integrity | All 45 ledger entries in `evidence/ledger.jsonl` are cryptographically chained via SHA-256 without corruption. | **Verified** | `evidence/ledger.jsonl:1-45` | `python tools/verify_chain.py` |
| **CLM-006** | Performance | Deployed Cloud Run WebLens achieves p50 latency of 1,094.0 ms (1.8x faster than Tavily Direct at 2,001.1 ms). | **Verified** | `reports/three-system-comparison/v10-cycle0-corrected-scorer/summary.json:28,48` | `python weblens-lab/evaluations/run_three_system_benchmark.py` |
| **CLM-007** | Quality | Deployed Cloud Run WebLens achieves 87.0% answer support rate across 100 benchmark queries (87/100). | **Verified** | `reports/three-system-comparison/v10-cycle0-corrected-scorer/summary.json:36` | `python weblens-lab/evaluations/run_three_system_benchmark.py` |
| **CLM-008** | Cost | WebLens operates at $0.00 infrastructure cost with 0 consumed credits on keyless providers. | **Verified** | `reports/three-system-comparison/v10-cycle0-corrected-scorer/summary.json:42-43` | `python weblens-lab/evaluations/run_three_system_benchmark.py` |
| **CLM-009** | Token Efficiency | WebLens consumes 425.5 mean tokens per query vs 1,486.6 tokens for Tavily Direct (71.4% token reduction). | **Verified** | `reports/three-system-comparison/v10-cycle0-corrected-scorer/summary.json:41,61` | `python weblens-lab/evaluations/run_three_system_benchmark.py` |
| **CLM-010** | Applications | All 9 specialized agent applications execute cleanly against synthetic fixtures (18/18 passed). | **Verified** | `reports/nine_applications_verification.json` | `python tools/run_all_nine_apps_live.py --mock-offline` |
| **CLM-011** | Applications | Spreadsheet enrichment prepends single-quotes to protect against CSV formula injection (`=`, `+`, `-`, `@`). | **Verified** | `src/weblens/apps/sheets.py:20-45` | `pytest tests/test_both_stack_comparison.py` |
| **CLM-012** | Extraction | Table extraction converts HTML tables into standard GitHub-flavored Markdown tables. | **Verified** | `src/weblens/extract/parser.py:50-95` | `pytest tests/test_extract.py` |
| **CLM-013** | Citations | Every extracted passage retains exact character-span anchors (`char_start`, `char_end`) and SHA-256 hash. | **Verified** | `src/weblens/extract/passages.py:25-80` | `pytest tests/test_token_boundaries.py` |
| **CLM-014** | Search | Country-code government domains (`.gov.in`, `.gov.uk`) and international organizations receive 2.0x authority boost. | **Verified** | `src/weblens/search/router.py:50-94` | `pytest tests/test_search_engine.py` |
| **CLM-015** | Trap Defense | Research engine abstains (`no_reliable_result`) on false-premise and unanswerable queries. | **Partially verified** | `src/weblens/research/engine.py:488-495` | `pytest tests/test_search.py` |
| **CLM-016** | Provider | SearXNG provider integration is blocked locally because no SearXNG container is running. | **Blocked** | `src/weblens/search/searxng.py` | `ConnectError [WinError 10061]` |
| **CLM-017** | Gemini | Gemini API integration with WebLens MCP adapter executes structured tool calls. | **Partially verified** | `weblens-lab/adapters/gemini_adapter/` | Unit tests passing; live API requires user-supplied key |
| **CLM-018** | Red-Team | Zero API keys or secrets are leaked in git commits or log files. | **Verified** | `tests/test_p9_canary_secrets.py` | `pytest tests/test_p9_canary_secrets.py` |
