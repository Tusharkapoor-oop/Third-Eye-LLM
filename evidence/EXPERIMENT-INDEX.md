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

