# Controlled Security and Reliability Results

**Run:** `stage7-security-f432267e3e`  
**Campaign:** `stage7-20261028-a4a64151`  
**Cases:** 40  
**Result:** 38 PASS, 2 FAIL, 0 ERROR, 0 BLOCKED, 0 SKIPPED, 0 INCONCLUSIVE, 0 CANCELLED  
**Rerun:** 2026-11-01 under Python 3.14.0; the earlier Python 3.13.15 run is preserved at `../tavily-comparison/raw/security_py313.jsonl`.

Full machine-readable results: `../tavily-comparison/SECURITY-RESULTS.json`.  
Raw records: `../tavily-comparison/raw/security.jsonl`.  
Run summary: `../tavily-comparison/raw/security_summary.json`.

---

## 1. Group results

| Group | Cases | PASS | FAIL |
|---|---:|---:|---:|
| SSRF and destination policy | 14 | 14 | 0 |
| Browser egress proxy | 3 | 3 | 0 |
| Cache | 5 | 5 | 0 |
| Injection detection | 4 | 4 | 0 |
| Input boundary | 4 | 4 | 0 |
| MCP schema | 2 | 2 | 0 |
| Reliability | 8 | 6 | 2 |
| **Total** | **40** | **38** | **2** |

---

## 2. The two failures

### REL-RETRY-001

- Expected: 503 then 200; two server hits; final 200.
- Actual: one hit; `status=error:http_error`.
- Severity: medium.
- Meaning: no bounded retry for service-unavailable responses.

### REL-RETRY-002

- Expected: 429 with `Retry-After: 1`, then 200; two hits; final 200.
- Actual: one hit; `status=error:http_error`.
- Severity: medium.
- Meaning: no bounded retry for rate-limit responses.

These are preserved as failures. The harness was not changed to make them pass.

---

## 3. Selected passes

| Case | Observed |
|---|---|
| SSRF literal/hostname/alternate forms | non-public targets blocked |
| DNS rebinding/mixed answers | rejected before connect |
| Redirect to `169.254.169.254` | blocked |
| Direct loopback fetch | blocked |
| Browser proxy private HTTP | 403 |
| Browser proxy private CONNECT | 403 |
| Authorized loopback fixture | forwarded only with `allow_private_networks=True` |
| Cache cap | 5 evictions, 1 entry, bounded bytes |
| Corrupt cache value | ignored, no raise |
| Cache persistence | survives close/reopen |
| Auth fingerprint | separate cache keys |
| Injection text/comment | flagged |
| Oversized body | `too_large` |
| Redirect loop | bounded error |
| MCP out-of-range `max_results` | rejected before service call |

---

## 4. Interpretation

The suite found no critical or high-severity bypass in the controlled cases. It did find a real reliability gap: transient 429/503 responses are not retried. The browser proxy is application-level egress control, not an OS/container sandbox. No full MCP conformance or independent security audit is claimed.

**Release impact:** security bypass gate passes for the listed cases; robust-reliability gate fails. Overall decision remains **CONDITIONAL**.
