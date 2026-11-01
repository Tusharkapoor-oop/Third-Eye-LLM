# Failure Analysis

**Campaign:** `stage7-20261028-a4a64151`  
**Dataset:** `stage7_dataset.jsonl`, 108 rows, SHA-256 `a4a64151fbdbda850a9de128bb7f83ec67f126b633aac42488c6f0b9296a9b21`  
**Frozen split:** 81 dev / 27 sealed test  
**Evidence:** `raw/*.jsonl`, `data/analysis.json`, `SECURITY-RESULTS.json`  
**Status vocabulary:** PASS, FAIL, ERROR, BLOCKED, SKIPPED, INCONCLUSIVE, CANCELLED

This document records failures that were observed. It does not convert an unmeasured condition into a pass. The campaign is **not** a full production certification and is **not** a full MCP conformance run.

---

## 1. Failure summary

| Area | Observed result | Severity / status | Release impact |
|---|---|---|---|
| Keyless search quality vs Tavily direct | Sealed-test precision@5 `0.0588` vs `0.2706`; support `0.5294` vs `1.0` | FAIL (quality) | Keyless is not non-inferior on this test split |
| Keyless research quality | Sealed-test support `0.5294`; combined `0.7857` | FAIL (quality) | Research is not a substitute for Tavily-backed research |
| Conflict recall | `0/18` overall; `0/8` numeric and `0/10` conceptual | FAIL (capability) | No contradiction-detection parity claim |
| Unanswerable queries | Combined false confidence `45%` keyless, `35%` WebLens-Tavily | FAIL (truthfulness) | Abstention is unreliable |
| Extraction | Tavily `10/10` support; WebLens full `7/10`, two hard errors | FAIL (coverage) | Extraction is not equivalent |
| HTTP retry | 429 and 503 each produced one request and a terminal `http_error` | FAIL (reliability) | Transient provider errors are not absorbed |
| Map/crawl | Keyless map/crawl returned `0` results; Tavily returned `10` / `3` | FAIL (functional) | Do not claim crawl/map parity |
| Search latency | Keyless is faster by ~750 ms mean; direct Tavily p95 ~2.53 s | PASS for keyless speed; not a universal latency win | Tavily remains optional |
| Security probes | 38 PASS, 2 FAIL; 0 critical/high in the controlled suite | CONDITIONAL | No full security certification |
| Pre-registration timing | Dev search began before the recorded preregistration time | PROCESS FAIL | Must not be described as preregistered-before-all-evaluation |

---

## 2. Quality failures

### 2.1 Keyless search precision and support

Sealed test, answerable rows only (`n=17`):

| System | Precision@5 | Search support | Status distribution |
|---|---:|---:|---|
| Direct Tavily | 0.2706 | 1.0000 | 27 `ok` |
| WebLens keyless | 0.0588 | 0.5294 | 22 `partial`, 5 `no_reliable_result` |
| WebLens-Tavily | 0.2706 | 1.0000 | 27 `ok` |

Combined (`n=70` answerable rows):

| System | Precision@5 | Search support |
|---|---:|---:|
| Direct Tavily | 0.2571 | 0.9714 |
| WebLens keyless | 0.1686 | 0.6714 |
| WebLens-Tavily | 0.2429 | 0.9857 |

Paired direct-minus-keyless:

- Precision@5: `+0.0886`, 95% CI `[0.0257, 0.1486]`.
- Support: `+0.3000`, 95% CI `[0.1857, 0.4143]`.

The confidence intervals exclude zero and the point estimates clear the pre-registered practical thresholds. **Tavily direct is better on labelled-domain precision and evidence support.** The keyless engine remains useful where cost, latency, and payload size dominate, but it is not quality-equivalent.

Caveat: precision uses strict labelled-domain membership, not human relevance. The dataset has no exhaustive relevant-URL set, so recall is not estimable.

### 2.2 Research quality

Combined (`n=70` answerable rows):

| System | Research support | Mean latency |
|---|---:|---:|
| WebLens keyless | 0.7857 | 3,399.7 ms |
| WebLens-Tavily | 0.9143 | 4,329.1 ms |

Paired WebLens-Tavily minus keyless support: `+0.1286`, 95% CI `[0.0143, 0.2429]`. WebLens-Tavily is also slower by `929.4 ms` mean (`[384.2, 1480.7]`).

Sealed test (`n=17` answerable rows):

| System | Research support | No-result accuracy | False confidence |
|---|---:|---:|---:|
| WebLens keyless | 0.5294 | 0.4000 | 0.6000 |
| WebLens-Tavily | 0.9412 | 0.8000 | 0.2000 |

**Failure:** keyless research misses 47.1% of the expected answer terms on the sealed split (support `0.5294`) and is wrong on 60% of unanswerable test queries. This blocks any claim that keyless research is a general Tavily replacement.

### 2.3 Conflict recall

The conflict set has 18 frozen rows:

- Numeric conflicts: `0/8` recalled.
- Conceptual conflicts: `0/10` recalled.
- Overall: `0/18`, rate `0.0`.

A conflict is counted as recalled only when the research payload status is `conflicting_sources` or the payload explicitly names the conflicting values. The system returned none. This is a measured failure, not a missing metric.

### 2.4 Extraction failures

Ten frozen extraction targets, paired:

| Variant | Status | Support | Mean latency | Mean text tokens |
|---|---|---:|---:|---:|
| Direct Tavily extract | 10 `ok` | 1.0 | 1,223.8 ms | 12,214 |
| WebLens full | 8 `ok`, 2 `error` | 0.7 | 5,370.1 ms | 2,421 |
| WebLens query-focused | 6 `ok`, 2 `error`, 1 `no_reliable_result`, 1 `possibly_outdated` | 0.7 | 3,644.4 ms | 433 |

The two WebLens full errors are genuine:

1. SitePoint returned HTTP 403 to the WebLens client.
2. Reddit served a JavaScript-only/empty page that the HTTP extractor could not use.

A separate real bug was found and fixed during the campaign: `age_days()` passed a string to date subtraction in `weblens/src/weblens/extract/html.py`. The pre-fix extraction run is preserved as `raw/extraction_pre_fix.jsonl`; the post-fix run is `raw/extraction.jsonl`. The fix added a regression test. The two remaining errors above are not caused by that bug.

### 2.5 Map and crawl

Single-site comparison:

| Operation | Direct Tavily | WebLens keyless |
|---|---:|---:|
| Map latency | 1,683.4 ms | 12,506.5 ms |
| Map results | 10 | 0 |
| Crawl latency | 2,042.8 ms | 6,932.7 ms |
| Crawl results | 3 | 0 |

WebLens keyless returned `status=ok` with zero results for both map and crawl. That is a functional failure, not a latency-only difference. The report does not claim crawl/map parity.

---

## 3. Performance and load failures

### 3.1 Search latency

Combined successful paired queries (`n=70`):

| System | Mean | p50 | p90 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| Direct Tavily | 1,637.3 | 1,544.5 | 2,116.7 | 2,531.4 | 3,014.1 |
| WebLens keyless | 886.8 | 753.0 | 1,158.3 | 2,513.8 | 3,650.0 |
| WebLens-Tavily | 901.1 | 339.0 | 2,287.1 | 2,539.9 | 4,004.7 |

Keyless is faster by `750.5 ms` mean (`[580.1, 906.9]`), but its p95 is essentially the same as Tavily direct (`2,513.8` vs `2,531.4` ms). The win is in the typical case, not the tail. All three systems are below the pre-registered 5,000 ms search p95 operational gate on this run.

### 3.2 Load

Six queries per cell, concurrency 1/2/5:

| Provider | Concurrency | Wall time | Mean latency | Status |
|---|---:|---:|---:|---|
| WebLens keyless | 1 | 8,860.9 ms | 1,474.2 ms | 3 `ok`, 3 `partial` |
| WebLens keyless | 2 | 8,432.3 ms | 2,569.0 ms | 6 `partial` |
| WebLens keyless | 5 | 4,178.1 ms | 3,022.9 ms | 6 `partial` |
| WebLens-Tavily | 1 | 2,640.8 ms | 440.0 ms | 6 `ok` |
| WebLens-Tavily | 2 | 1,053.6 ms | 348.3 ms | 6 `ok` |
| WebLens-Tavily | 5 | 940.1 ms | 563.3 ms | 6 `ok` |

This is a small load probe, not a stress test. It shows that keyless degrades into `partial` statuses under concurrency while WebLens-Tavily stays `ok` on this fixture set. It does not establish production capacity.

### 3.3 Browser

Six browser-fixture records:

- Static fixture: HTTP and browser both `ok`.
- JavaScript fixture: HTTP `no_reliable_result`; browser `ok` at 2,756.8 ms with one proxy request.
- Injection fixture: both `ok`; passage injection flagged `ignore_instructions`; the injected text remained in the payload.

The browser path is real and proxied for the measured `/js` case. This is not a browser sandbox audit and does not cover downloads, WebSockets, renderer compromise, or crash loops.

---

## 4. Reliability and security failures

The controlled security harness ran 40 cases against owned loopback fixtures. Results: **38 PASS, 2 FAIL, 0 ERROR, 0 BLOCKED, 0 SKIPPED, 0 INCONCLUSIVE, 0 CANCELLED**.

### 4.1 Confirmed medium finding: no HTTP 429/503 retry

- `REL-RETRY-001`: fixture returned 503 on the first request; `SafeFetcher` made **one** request and returned `error/http_error`.
- `REL-RETRY-002`: fixture returned 429 with `Retry-After: 1`; `SafeFetcher` made **one** request and returned `error/http_error`.

The fetch layer retries transport failures (the timeout and truncated-body cases made two attempts), but it does not retry HTTP rate-limit or service-unavailable status codes. This is a reliability gap, not a security bypass. It can turn a transient provider condition into a terminal search/research error.

**Remediation:** add a bounded retry policy for 429/502/503/504 with `Retry-After` support, at most two attempts, jitter, and a total deadline. Preserve retry counts in evidence. Rerun the reliability gate after the change.

### 4.2 What did pass

- SSRF: 9 non-public IPv4 literals, 4 IPv6 forms, 5 internal hostnames, 6 alternate/ambiguous URL forms, DNS rebinding/mixed answers, redirect-to-metadata, and direct loopback fetch were blocked (14/14 cases).
- Browser egress: HTTP private target refused, CONNECT private target refused, authorized loopback fixture forwarded only with `allow_private_networks=True` (3/3).
- Cache: cap/eviction, corrupt compressed value, close/reopen persistence, auth-fingerprint separation, and missing-table containment (5/5).
- Injection: text patterns, HTML comment smuggling, passage flags, and explicit comment warning (4/4).
- Input boundary: empty query, very long query, non-HTTP URL, Unicode/control URL (4/4).
- MCP schema: four read-only tools; out-of-range `max_results` rejected before service call (2/2).
- Timeout, non-retryable 500, truncated body, redirect loop, oversized body, cache-disabled path (6/8 reliability cases; the two retry cases above failed).

### 4.3 Residual security limitations

- The browser proxy is **application-level egress control**, not an OS/container sandbox. A compromised browser process is out of scope.
- No independent penetration test or code audit was performed.
- No browser crash-loop, renderer compromise, WebSocket, download, or HTTPS interception test was run.
- MCP schema validation was exercised directly. The official conformance runner is **not** reported as passing on this Windows host; full MCP conformance is not claimed.
- Injection detection is a heuristic warning, not a classifier. Flagged content is still returned; consumers must isolate or strip it.
- SSRF coverage is limited to the listed literal, hostname, DNS, redirect, and proxy cases. No exhaustive parser-differential fuzzing was performed.
- No denial-of-service or volumetric traffic was sent to Tavily or any third party.

---

## 5. Process failures

### 5.1 Pre-registration timing

The recorded preregistration timestamp is `2026-10-28T03:10:00Z`. The paid dev search meta starts at `2026-10-28T03:05:15Z`; the smoke search starts at `03:00:28Z`. The rules were therefore **not** fully frozen before the first paid calls. The test split was opened later (`04:33:34Z`), but the final analyzer artifact was generated after the test run (`04:42:16Z`). The report does not claim a clean preregistered-before-all-evaluation sequence. Details are in `PREREGISTRATION.json` under `timing_audit`.

### 5.2 Harness hash amendment

The original `stage7_run.py` hash no longer matches. The change was a harness-only fix made after the first smoke run and before the paid dev campaign:

- resume key includes the phase tag,
- fixture HTML uses `id="app"` so the JavaScript-shell detector recognizes it,
- injection flags are captured in browser evidence.

No metric, threshold, split, label, or provider configuration changed. The original and current hashes are both recorded in `PREREGISTRATION.json`.

### 5.3 Usage endpoint rate limit

The Tavily usage endpoint returned HTTP 429 during the campaign. Mid-campaign meta snapshots are stale. A final authenticated check at `2026-10-28T10:25:24Z` succeeded: account `551/1000`, `449` remaining; campaign delta `381` credits, within the `420` cap and above the `200` stop. The final check supersedes the stale snapshots.

---

## 6. Release implications

| Gate | Result | Decision |
|---|---|---|
| Controlled SSRF / private-network / redirect / scheme / proxy / injection / oversize / auth probes | 38 PASS, 2 FAIL (retry only) | Security gate passes for the listed bypass probes; retry gate fails |
| Keyless quality non-inferiority | Fails on precision@5 and support | Do not market keyless as Tavily-quality |
| Research quality | Keyless fails; WebLens-Tavily improves but is Tavily-backed | Do not claim independent research parity |
| Conflict detection | 0/18 | Do not claim contradiction handling |
| Abstention | 45% keyless false confidence | Do not claim reliable no-answer behavior |
| Extraction | 7/10 support, 2 hard errors | Do not claim extraction parity |
| Map/crawl | 0 results for keyless | Do not claim crawl/map parity |
| Latency | Keyless p95 under 5 s; typical case faster | Default keyless is operationally viable |
| MCP conformance | Not run to completion | Do not claim conformance |
| Browser isolation | Application-level egress only | Do not claim sandbox isolation |

**Recommendation:** `CONDITIONAL GO` for the default keyless local/single-user configuration with the limitations above. `NO-GO` for an unconditional production certification, multi-tenant security certification, Tavily-quality parity claim, conflict-detection claim, or full MCP conformance claim. Tavily remains an optional, paid quality path; WebLens-Tavily is an optimization layer over Tavily, not an independent provider.

The two retry failures should be fixed before the next reliability gate. The extraction errors and zero conflict recall should be treated as known product gaps, not papered over with synthetic passes.
