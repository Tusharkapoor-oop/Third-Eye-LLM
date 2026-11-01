# Extreme-Scale Equivalent — Security and Failure Results

**Controlled cases:** 40  
**Result:** 38 PASS, 2 FAIL, 0 critical, 0 high  
**Evidence:** `../tavily-comparison/raw/security.jsonl`, `../tavily-comparison/SECURITY-RESULTS.json`

This is a controlled local test suite, not a full penetration test. No Tavily or third-party infrastructure was attacked.

---

## 1. Results by group

| Group | Records | PASS | FAIL | Notes |
|---|---:|---:|---:|---|
| SSRF | 14 | 14 | 0 | literals, IPv6, hostnames, alternate forms, DNS, redirects |
| Egress proxy | 3 | 3 | 0 | private HTTP, CONNECT, authorized loopback |
| Cache | 5 | 5 | 0 | cap, corruption, persistence, auth key, missing table |
| Injection | 4 | 4 | 0 | text, comment, passage flag, warning |
| Input | 4 | 4 | 0 | empty, long, non-HTTP, Unicode/control |
| MCP schema | 2 | 2 | 0 | tool surface, out-of-range max_results |
| Reliability | 8 | 6 | 2 | 429/503 retry failures |
| **Total** | **40** | **38** | **2** | |

---

## 2. Confirmed failures

### REL-RETRY-001 — 503 not retried

- Fixture: first response 503, second would be 200.
- Observed: **one** request; terminal `error/http_error`.
- Expected: two requests, final 200.
- Severity: medium.
- Impact: transient service-unavailable responses become terminal errors.

### REL-RETRY-002 — 429 not retried

- Fixture: first response 429 with `Retry-After: 1`, second would be 200.
- Observed: **one** request; terminal `error/http_error`.
- Expected: two requests, final 200.
- Severity: medium.
- Impact: transient rate limits become terminal errors.

Both are reliability findings. They are not SSRF, injection, or cache bypasses.

---

## 3. What passed

- SSRF: 9 non-public IPv4 literals, 4 IPv6 forms, 5 internal hostnames, 6 alternate/ambiguous URL forms, DNS rebinding, mixed public/private answers, DNS failure, redirect to `169.254.169.254`, and direct loopback fetch.
- Browser proxy: private HTTP target 403; private CONNECT 403; authorized loopback 200 only with `allow_private_networks=True`.
- Cache: logical cap/eviction; corrupt zlib value returns miss; close/reopen persistence; auth fingerprint separates keys; dropped table returns miss with error count.
- Injection: text patterns, HTML comment smuggling, passage flag, comment warning. Flagged text is still returned.
- Input: empty query `bad_input`; long query structured response; non-HTTP URL rejected; Unicode/control URL structured.
- MCP: four read-only tools; out-of-range `max_results` rejected before service call.
- Timeout: 1.15 s bounded error; truncated body: 2 attempts then error; redirect loop: bounded; oversized body: `too_large`; non-retryable 500: one request; cache-disabled path works.

---

## 4. Residual risk

- Browser proxy is application-level egress control, not an OS/container sandbox.
- No browser crash-loop, renderer compromise, WebSocket, download, or HTTPS interception test.
- No full MCP conformance run.
- Injection detection is heuristic; flagged text remains available.
- SSRF coverage is case-based, not exhaustive.
- No independent audit.
- No volumetric load or third-party DoS.

---

## 5. Failure behavior beyond security

- Keyless search test support `0.5294`; false confidence `0.60` on sealed test.
- Conflict recall `0/18`.
- Extraction `7/10` support; two hard errors.
- Map/crawl keyless `0` results.
- Pre-registration timing violation (dev search started before recorded preregistration).
- Usage endpoint 429 mid-campaign; final check succeeded.

These are product/process failures, not security passes.

---

## 6. Verdict

- No critical/high finding in the controlled suite.
- Two failed retry cases (one medium finding) block a robust-reliability claim.
- The security bypass gate for the listed SSRF/private-network/redirect/proxy/injection/oversize/auth cases passes.
- The overall release is **CONDITIONAL**, not an unconditional certification.
