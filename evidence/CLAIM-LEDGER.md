# WebLens Claim Ledger

## 1. Verified Claims Registry
This ledger records all formal performance, security, and quality claims evaluated under the WebLens protocol. Every claim is tied to an immutable record in `evidence/ledger.jsonl`.

---

## 2. Claim Table

| Claim ID | Category | Claim Statement | Measured Value | Sample Size / CI | Status | Evidence Reference |
|---|---|---|---|---|---|---|
| **CLM-001** | Test Suite | Package test suite passes cleanly | 162 passed, 1 skipped | $n=163$ (99.39% [96.65%, 99.89%]) | **PASS — VERIFIED** | `EXP-001b` / `tests-weblens-suite` |
| **CLM-002** | Test Suite | Root stack test suite passes | 245 passed | $n=245$ (100.0% [98.46%, 100.00%]) | **PASS — VERIFIED** | `tests-root-suite` |
| **CLM-003** | Security | In-process SSRF guard blocks private/metadata IP probes | 38 blocked of 38 attempts | $n=38$ (100.0% [90.82%, 100.00%]) | **PASS — VERIFIED** | `EXP-002` / `gate1-tamper-mutation-v3` |
| **CLM-004** | Security | Benign web passages trigger zero false positive injection flags | 0 false flags of 10,000 | $n=10,000$ (0.00% [0.00%, 0.04%]) | **PASS — VERIFIED** | `tier-d-injection-eval` |
| **CLM-005** | Security | English prompt injection attacks are reliably detected | 3,812 flagged of 5,000 | $n=5,000$ (76.24% [75.04%, 77.40%]) | **PASS — VERIFIED** | `tier-d-injection-eval` |
| **CLM-006** | Security | Non-English prompt injections are detected | 0 flagged of 528 attacks | $n=528$ (0.00% [0.00%, 0.70%]) | **FAIL — VERIFIED** | `tier-d-injection-eval` |
| **CLM-007** | Performance | WebLens Keyless search latency is lower than Tavily Direct | Mean 886.8 ms vs 1,637.3 ms | $n=70$, difference -750.5 ms | **PASS — VERIFIED** | `rederive-stage7-raw` |
| **CLM-008** | Quality | WebLens Keyless answer support rate on complex queries | 47 supported of 70 items | $n=70$ (67.14% [55.49%, 76.99%]) | **PASS — VERIFIED** | `rederive-stage7-raw` |
| **CLM-009** | Competitor | Tavily Direct answer support rate on same complex queries | 68 supported of 70 items | $n=70$ (97.14% [89.92%, 99.23%]) | **PASS — VERIFIED** | `rederive-stage7-raw` |
| **CLM-010** | Tokens | WebLens Keyless returns fewer payload tokens than Tavily | 505.3 tokens vs 1,034.1 tokens | $n=70$, 51.1% token reduction | **PASS — VERIFIED** | `rederive-stage7-raw` |
| **CLM-011** | Tokens | Core MCP schema size stays within 1,000 token budget | 732 `cl100k_base` tokens | 4 registered tools | **PASS — VERIFIED** | `EXP-006` |
| **CLM-012** | Integrity | Tamper and broken-build mutations are caught by test harness | 3 mutations caught of 3 | $n=3$ (100.0% [43.85%, 100.00%]) | **PASS — VERIFIED** | `EXP-007b` / `gate1-tamper-mutation-v3` |
| **CLM-013** | Secrets | No real API secrets are committed in source or git history | 0 secret hits in 92 files | $n=92$ files scanned | **PASS — VERIFIED** | `EXP-008` / `test-p9-canary-v3` |
| **CLM-014** | Supply Chain | Zero known vulnerabilities across pinned dependency tree | 0 CVEs across 75 packages | Google OSV API audit | **PASS — VERIFIED** | `supply-chain-audit` |
| **CLM-015** | Conflict | Keyless search detects contradictory/conflicting sources | 0 conflicts flagged of 18 | $n=18$ (0.00% [0.00%, 18.00%]) | **FAIL — VERIFIED** | `rederive-stage7-raw` |
| **CLM-016** | Infrastructure | SearXNG meta-search provider integration operates live | Connection refused (port 8080) | Local engine offline | **BLOCKED** | `ConnectError [WinError 10061]` |

