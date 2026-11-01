# Extreme-Scale Equivalent — Release Decision

**Campaign:** `stage7-20261028-a4a64151`  
**Decision:** **CONDITIONAL GO** for default keyless local/single-user use  
**Unconditional production certification:** **NO-GO**

---

## 1. Decision summary

The measured system is useful and operationally viable for a local, single-user, keyless workflow. It is not quality-equivalent to Tavily, not conflict-aware, not reliably abstaining, not extraction-equivalent, not crawl/map-equivalent, and not a security sandbox.

| Claim | Supported? | Evidence |
|---|---|---|
| Default keyless search is fast and token-light | **YES** | 886.8 ms mean, 505 tokens mean; p95 2.51 s |
| Keyless quality matches Tavily | **NO** | test precision 0.0588 vs 0.2706; support 0.5294 vs 1.0 |
| WebLens-Tavily matches Tavily search quality | **YES on this test** | 0.2706 vs 0.2706; support 1.0 vs 1.0; but Tavily-backed |
| Keyless research matches Tavily-backed research | **NO** | 0.5294 vs 0.9412 test; 0.7857 vs 0.9143 combined |
| Conflict detection works | **NO** | 0/18 recall |
| Abstention is reliable | **NO** | 45% keyless false confidence combined; 60% test |
| Extraction matches Tavily | **NO** | 7/10 vs 10/10 support; two hard errors |
| Crawl/map matches Tavily | **NO** | 0 vs 10 map results; 0 vs 3 crawl results |
| Controlled SSRF/private-network bypass gate passes | **YES for tested cases** | 14/14 SSRF, 3/3 proxy |
| HTTP 429/503 retry works | **NO** | one request, terminal error |
| Full MCP conformance | **NO** | official runner not completed |
| Browser sandbox isolation | **NO** | application-level proxy only |
| Budget respected | **YES** | 381/420 credits; 449 remaining |
| Clean preregistration timing | **NO** | dev search began before recorded preregistration |

---

## 2. Release gates

| Gate | Result | Decision |
|---|---|---|
| Critical security | 0 critical in controlled suite | PASS for tested cases |
| High security | 0 high in controlled suite | PASS for tested cases |
| SSRF/private/metadata | 14/14 | PASS |
| Browser egress | 3/3 | PASS |
| Cache isolation/corruption | 5/5 | PASS |
| Injection detection | 4/4 | PASS with residual risk |
| Timeout/malformed/redirect/oversize | 4/4 | PASS |
| Retry 429/503 | 0/2 | **FAIL** |
| Keyless quality non-inferiority | Fails precision/support | **FAIL** |
| Research quality | Keyless fails; WT improves | **CONDITIONAL** |
| Conflict | 0/18 | **FAIL** |
| Abstention | 45% false confidence | **FAIL** |
| Extraction | 7/10 | **FAIL** |
| Crawl/map | 0 results | **FAIL** |
| MCP conformance | Not completed | **NOT TESTED** |
| Browser isolation | Application-level only | **LIMITED** |
| Budget | 381/420 | **PASS** |
| Pre-registration | Timing violation | **PROCESS FAIL** |

---

## 3. Conditions for release

1. Fix bounded 429/503 retry before claiming robust reliability.
2. Treat extraction 403/JavaScript failures as known gaps.
3. Do not advertise keyless precision/support, research, abstention, crawl/map, or extraction parity.
4. Keep Tavily optional and paid; describe WebLens-Tavily as a Tavily-backed optimization layer.
5. Do not claim full MCP conformance, browser sandbox isolation, or multi-tenant security certification.
6. Disclose the preregistration timing violation in any publication.
7. Do not use the 10,000-row synthetic corpus as ground truth.

---

## 4. What would change the decision

- A clean preregistered 500+ query campaign with human relevance audits.
- A real 10,000-row labelled dataset with reproducible partitions.
- Bounded retry implementation and rerun.
- Extraction fixes for 403/JavaScript pages.
- Conflict-detection work with measured recall > 0.
- Abstention calibration.
- Independent security review and browser sandbox design.
- Full MCP conformance on a supported host.

Until then, the correct label is **conditional**, not certified.

---

## 5. Final statement

**CONDITIONAL GO** for default keyless local/single-user use.  
**NO-GO** for unconditional production certification, multi-tenant security certification, Tavily-quality parity, conflict-detection parity, extraction parity, crawl/map parity, or full MCP conformance.

The evidence is in `../tavily-comparison/`; the archived prior “unconditional full pass” artifacts are not evidence and are retained only in `../_archive/prior-run-20261027/`.
