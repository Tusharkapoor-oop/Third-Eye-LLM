# WebLens Experiment Index

## 1. Overview
Every experiment executed under the WebLens protocol is assigned a permanent identifier, cryptographic hash, and entry in `evidence/ledger.jsonl`. Raw inputs, outputs, and standard streams are preserved in `evidence/raw/<id>/`.

---

## 2. Master Experiment Registry

| Experiment ID | Class | Kind / Description | Target / Suite | Rows / Samples | Key Findings | Raw Output Location |
|---|---|---|---|---|---|---|
| **EXP-000** | REAL | Environment & Version Audit | System, Python, Git | 1 | Commit `902415d49f8d`, Python 3.14.0 | `evidence/raw/EXP-000/` |
| **EXP-001b** | REAL | Core Unit Test Suite | `weblens/tests/` | 163 | 162 passed, 1 skipped | `evidence/raw/EXP-001b/` |
| **EXP-002** | SIMULATED | SSRF & Egress Protection Matrix | `weblens.net.ssrf` | 38 | 38/38 blocked, 0 fixture packets | `evidence/raw/EXP-002/` |
| **EXP-003** | SIMULATED | Prompt Injection Synthetic Fuzz | `weblens.security.injection` | 100 attacks, 100 benign | 82/100 detected, 0/100 benign FPR | `evidence/raw/EXP-003/` |
| **EXP-004b** | REAL | SQLite HTTP Cache Functionality | `weblens.cache` | 4 cases | 4/4 cache behaviors verified | `evidence/raw/EXP-004b/` |
| **EXP-005** | SIMULATED | Document Extraction & Passage Scoring | `weblens.extract` | 14 test pages | 23/34 facts found (67.65%), 11 HTTP calls | `evidence/raw/EXP-005/` |
| **EXP-006** | REAL | MCP Schema Token Measurement | `weblens.mcp_server` | 4 tools | 732 `cl100k_base` tokens (budget: 1000) | `evidence/raw/EXP-006/` |
| **EXP-007b** | REAL | Mutation & Tamper Detection | Evidence runner & SSRF | 4 cases | 3/3 mutations caught, 1 clean control | `evidence/raw/EXP-007b/` |
| **EXP-008** | REAL | Working Tree & History Secrets Scan | Full repository | 92 files | 0 real secrets detected | `evidence/raw/EXP-008/` |
| **EXP-101c** | SIMULATED | Long Page Tail-Fact Extraction Baseline | `weblens.extract.passages` | 30 held-out pages | 0/30 tail-fact recall on 15k char docs | `evidence/raw/EXP-101c/` |
| **EXP-102** | SIMULATED | Spaced Chunking Tail-Fact Evaluation | `weblens.extract.passages` | 30 held-out pages | Tail-fact recall improved to 30/30 | `evidence/raw/EXP-102/` |
| **EXP-104** | REAL | Post-Chunking Test Suite Regression | `weblens/tests/` | 163 | 162 passed, 1 skipped | `evidence/raw/EXP-104/` |
| **EXP-105** | REAL | Post-Chunking Token Schema Audit | `weblens.mcp_server` | 4 tools | 732 tokens unchanged | `evidence/raw/EXP-105/` |
| **EXP-106** | SIMULATED | Post-Chunking SSRF Matrix | `weblens.net.ssrf` | 38 | 38/38 blocked unchanged | `evidence/raw/EXP-106/` |
| **EXP-107** | REAL | Root Stack Test Suite Verification | `tests/` | 245 | 245 passed in 203.7s | `evidence/raw/EXP-107/` |
| **tests-root-suite** | REAL | Comprehensive Root Test Execution | `tests/` | 245 | 245 passed | `evidence/raw/tests-root-suite/` |
| **tests-weblens-suite** | REAL | Full Weblens Package Execution | `weblens/tests/` | 163 | 162 passed, 1 skipped | `evidence/raw/tests-weblens-suite/` |
| **tier-d-injection-eval** | SIMULATED | Large-Scale Prompt Injection Benchmark | Synthetic corpus | 5,000 attacks, 10k benign | 76.24% recall, 0.00% benign FPR | `evidence/raw/tier-d-injection-eval/` |
| **supply-chain-audit** | REAL | Dependency OSV API Vulnerability Scan | 75 pinned packages | 75 | 0 CVEs found | `evidence/raw/supply-chain-audit/` |
| **static-analysis-audit** | REAL | Static Analysis Danger AST Grep | 92 source files | 92 | 0 `eval`, 0 `exec`, 0 shell calls | `evidence/raw/static-analysis-audit/` |
| **rederive-stage7-raw** | REAL | Stage 7 Raw Data Re-derivation | 70 complex queries | 70 | Keyless vs Tavily paired metrics | `evidence/raw/rederive-stage7-raw/` |
| **EXP-V9B-100Q** | REAL | Three-System Benchmark — 100-Query Extension | `benchmarks/eval_dataset_expanded.json` (first 100, SHA-256 `6130548d…`) | 100 × 3 systems | Tavily wins quality (P@5 0.756, support 0.90); local WebLens wins latency (922.7 ms p50) & cost ($0, 425.8 tokens); deployed within 4 pp of local, 99% success; one graceful abstention | `reports/three-system-comparison/raw-v9b-2026-11-02/` |
| **SEC-V9-001** | REAL | Secret scan of committed markdown reports | All tracked `.md` surfaces | 2 files hit | Live Tavily key found in 2 committed reports (v9 regression vs CLM-013, which scanned only source files); both redacted; rotation required | `evidence/SECURITY-FINDINGS.md` |
| **DEPLOY-DRIFT-001** | REAL | Deployment identity drift probe | `https://weblens-16131012091.us-central1.run.app` | 5 probes | `/healthz` 404 on deployed while present at HEAD (`a9bd964`); 10-tool surface matches `src/weblens/mcp_server.py`; no `mcp-session-id` issued; MCP init healthy | `reports/deployed-security/DEPLOYMENT_DRIFT_2026-11-02.md` |
| **EXP-V10-120** | REAL | V10 three-system benchmark | 120 curated queries × local MCP, deployed MCP, Tavily direct | 120 × 3 | Local P@5 0.553 / nDCG 0.669 / p50 837 ms / 182.3 tokens; deployed 0.471 / 0.729 / 1037.8 ms / 206.2; Tavily 0.740 / 0.777 / 1537.4 ms / 1378.7; paired local−Tavily P@5 −0.187 [−0.265, −0.108] | `reports/three-system-comparison-v10/` |
| **EXP-V10-DATASET** | REAL | V10 dataset validation | 120 items, 30 categories, 60/60 | 120 | Schema PASS; unique IDs, 0 duplicates; sample-size target BLOCKED at 120/100k | `reports/three-system-comparison-v10/dataset_validation_v10.json` |
| **APPS-V10-9** | REAL | Nine application end-to-end verification | Live workflows, temp work dir | 9 apps | 9 PASS / 0 PARTIAL / 0 FAIL with output assertions | `reports/nine_applications_verification.json` |
| **SEC-V10-LOCAL** | REAL | Local security audit v2 | Real local MCP process | 38 checks | 38 PASS after injection/Crawl2RAG/query-cap fixes | `reports/local-security/local_security_results_v2.json` |
| **SEC-V10-DEPLOYED** | REAL | Deployed security audit v2 | Real Cloud Run MCP, revision `weblens-00006-l9h` | 23 checks | 18 PASS / 4 FAIL / 0 UNVERIFIED / 1 UNSUPPORTED; open: unauth initialize, bogus Bearer, no visible rate limit, no HSTS; cross-tenant UNSUPPORTED because public listener omits stateful tools; SSRF verified blocking | `reports/deployed-security/deployed_security_results_v2.json` |
| **MODEL-ACCESS-V10** | REAL | Model access probe | NVIDIA NIM + configured keys | 3 models | Mistral Large 4 HTTP 200 exact JSON; GPT-OSS 20B timeout 150 s; Mistral NeMo 12B 404; no model-vs-model ranking possible | `weblens-lab/model_eval/probe_model_access.py` output in this report |
| **TAVILY-UC-V10** | REAL | Official Tavily demo use cases 5.1–5.8 | 8 cases × real WebLens MCP + Tavily `/search` | 8 × 2 | WebLens facet coverage 0.263 / 149.1 tokens / 9,102.4 ms; Tavily 0.844 / 1,278.6 tokens / 332.3 ms; retrieval-only Tavily baseline; query echoes excluded from scoring | `reports/tavily-use-cases-v10/results.json` |
| **POST-DEPLOY-V10** | REAL | Post-remediation deployed smoke | First 10 V10 queries × 3 systems | 10 × 3 | Deployed revision `00006-l9h`: P@5 0.80 / nDCG 0.932 / p50 1,211.5 ms / 266.4 tokens; directional only | `reports/three-system-comparison-v10/analysis-post-deploy-smoke/` |
| **DEPLOY-V10** | REAL | Redeploy current HEAD to Cloud Run | `weblens` service, `us-central1` | 2 revisions | `weblens-00005-mzl` exposed cross-tenant state; `weblens-00006-l9h` now serves 10 stateless tools; Dockerfile starts canonical weblens CLI | `reports/three-system-comparison-v10/V10_REPORT.md`, `Dockerfile` |

