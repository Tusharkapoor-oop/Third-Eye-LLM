# WebLens Best-Known-Good Baseline (Ratchet)

## 1. Baseline Summary
- **Baseline Commit:** `902415d49f8da502b9de0e1c78da7f5777a1d2f8`
- **Ledger Head Hash:** `271bc8c3cc6b5b4ff81d80f86511f6106a3ee5f61818bc36a5716c5825125a53`
- **Runtime Environment:** Python 3.14.0 (Windows 11 AMD64)

---

## 2. Established Performance & Security Metrics

### 2.1 Reliability & Test Integrity
- **WebLens Core Test Suite:** 162 passed, 1 skipped of 163 collected (`EXP-001b`).
- **WebIntel Root Test Suite:** 245 passed of 245 collected (`tests-root-suite`).
- **Mutation & Tamper Detection:** 3 of 3 mutations detected; 1 clean negative control verified (`EXP-007b`).

### 2.2 Security Baselines
- **In-Process SSRF Block Rate:** 100.0% (38 of 38 attempts blocked; 0 packets reached fixture servers; `EXP-002`).
- **Prompt Injection Benign False Positive Rate:** 0.00% [0.00%, 0.04%] (0 false flags of 10,000 benign passages; `tier-d-injection-eval`).
- **English Prompt Injection Recall:** 76.24% [75.04%, 77.40%] (3,812 flagged of 5,000; `tier-d-injection-eval`).
- **Secrets & Canary Redaction:** 0 leaked keys in source tree or full git history (`EXP-008`).
- **Dependency CVEs:** 0 known vulnerabilities across 75 pinned packages (`supply-chain-audit`).

### 2.3 Retrieval & Efficiency Metrics
- **Core MCP Schema Token Overhead:** 732 `cl100k_base` tokens across 4 tools (`EXP-006`). Budget: $\le 1,000$ tokens.
- **WebLens Keyless Search Latency:** Mean 886.8 ms, Median 657.4 ms ($n=70$).
- **WebLens Keyless Payload Size:** Mean 505.3 tokens ($n=70$; 51.1% smaller than Tavily Direct).
- **WebLens Keyless Answer Support:** 67.14% [55.49%, 76.99%] ($n=70$).
- **Tavily Direct Answer Support:** 97.14% [89.92%, 99.23%] ($n=70$).

---

## 3. Ratchet Rules
1. Under the v7 improvement loop, these numbers serve as the baseline ratchet.
2. A candidate change is rejected if any guarded metric regresses:
   - Answer support difference worse than $-2$ percentage points.
   - False confidence increases by more than $+1$ percentage point.
   - p95 latency increases by more than $+10\%$.
   - Output tokens per call increase by more than $+5\%$.
   - Any security regression (SSRF bypass, canary leakage, injection FPR increase) causes immediate rejection.

