# Red-Team Scope, Boundaries, and Threat Model

**Campaign:** `stage7-20261028-a4a64151`  
**Date:** 2026-10-28  
**Target:** WebLens local package and owned test fixtures  
**Authorization:** Local, owned-asset testing only. No third-party attack traffic.  
**Status:** Controlled evaluation, not a full penetration test or production certification.

---

## 1. Scope

### 1.1 In scope

- `weblens/src/weblens/net/ssrf.py` — destination policy and DNS/IP classification.
- `weblens/src/weblens/net/client.py` — HTTP fetch, redirects, size/time limits, retry behavior.
- `weblens/src/weblens/net/browser_proxy.py` — loopback browser egress proxy.
- `weblens/src/weblens/cache.py` — SQLite cache, compression, eviction, auth partitioning.
- `weblens/src/weblens/extract/` — HTML extraction, passage selection, injection flags.
- `weblens/src/weblens/service.py` — public error boundary.
- `weblens/src/weblens/mcp_server.py` — tool schema and read-only annotations.
- Owned loopback HTTP fixtures started by `weblens/benchmarks/stage7_security.py`.
- The browser fixture phase (`raw/browser_fixture.jsonl`) using Playwright Chromium through the loopback proxy.

### 1.2 Out of scope

- Tavily infrastructure, authentication, rate-limit bypass, or denial-of-service.
- DuckDuckGo, Wikipedia, Mwmbl, or any third-party site attack.
- OS/container escape, hypervisor, or host compromise.
- Browser renderer exploitation, malicious downloads, WebSocket abuse, or certificate interception.
- Exhaustive parser-differential fuzzing.
- Unbounded load or volumetric traffic.
- Credential exfiltration against real accounts.
- Multi-tenant isolation certification.

### 1.3 Stop conditions

Testing stops on:

1. Any real credential value appearing in output.
2. Unintended private-network or cloud-metadata traffic.
3. Runaway CPU/memory or host instability.
4. Corruption of preserved evidence or unrelated work.
5. Any request that would leave the owned-fixture boundary.

No stop condition was triggered.

---

## 2. Data flow

```text
MCP client / CLI
      |
      v
WebLens service (validation, status contract)
      |
      +--> search router --> keyless providers (DDG, Mwmbl, Wikipedia)
      |                  \-> Tavily adapter (optional, keyed)
      |
      +--> extraction service
             |--> SafeFetcher: normalize URL -> DestinationPolicy
             |                  -> resolve all A/AAAA -> block non-public
             |                  -> connect to pinned IP -> redirects re-checked
             |                  -> size/time/redirect caps -> cache -> parse
             |
             \--> browser fallback (disabled by default)
                    -> Playwright Chromium
                    -> loopback BrowserEgressProxy
                    -> DestinationPolicy before HTTP/CONNECT
```

The browser proxy is **application-level egress control**. It is not an OS firewall, container boundary, or browser sandbox.

---

## 3. Threat model

| ID | Threat | Vector | Control | Measured result |
|---|---|---|---|---|
| T1 | SSRF to loopback/private IP | URL literal, alternate form, redirect | `DestinationPolicy` blocks non-public resolved IPs; redirects re-checked | 14/14 controlled cases PASS |
| T2 | Cloud metadata access | `169.254.169.254`, metadata hostnames | Link-local/metadata IP blocked; internal hostnames blocked | PASS |
| T3 | DNS rebinding | Public first answer, private second | Resolve and pin; reject any non-public answer | PASS |
| T4 | Mixed DNS answers | Public + private A/AAAA | Reject the hostname if any answer is non-public | PASS |
| T5 | Browser subresource egress | Page loads script/image/WebSocket | Loopback proxy; private target refused; authorized fixture proxied | 3/3 proxy cases PASS; browser fixture `/js` used 1 proxy request |
| T6 | Prompt injection in retrieved content | Page text/comment instructs model | Heuristic flags, warning, data-not-instructions contract | 4/4 detection cases PASS; flagged text is still returned |
| T7 | Cache poisoning/corruption | Corrupt compressed row, missing table | Contain errors, return miss; auth fingerprint in key | 5/5 PASS |
| T8 | Oversized/malformed response | Huge `Content-Length`, truncated body, redirect loop | Byte cap, timeout, redirect cap, bounded transport retries | Oversize `too_large`; truncation 2 attempts then error; redirect loop bounded |
| T9 | Transient provider failure | HTTP 429/503 | Bounded retry with `Retry-After` | **FAIL**: one request, terminal `http_error` |
| T10 | Input abuse | Empty/long/Unicode/non-HTTP URL | Validation and structured error boundary | 4/4 PASS |
| T11 | Tool schema abuse | Out-of-range `max_results` | MCP/Pydantic validation before service call | PASS |
| T12 | Credential leakage | Logs/reports/errors | No key printing; final report secret scan | No key value found in reports |

---

## 4. Test matrix and status rules

The harness records one row per case in `reports/tavily-comparison/raw/security.jsonl`.

Status vocabulary:

- **PASS** — expected control behavior observed for that case.
- **FAIL** — expected control behavior not observed.
- **ERROR** — harness or target raised unexpectedly.
- **BLOCKED** — test could not be executed for an environmental or authorization reason.
- **SKIPPED** — deliberately not run; reason recorded.
- **INCONCLUSIVE** — evidence insufficient.
- **CANCELLED** — stopped by a stop condition.

A PASS is not a universal security guarantee. A FAIL is preserved even if a fix is later applied.

### 4.1 Results

| Group | Records | PASS | FAIL |
|---|---:|---:|---:|
| SSRF | 14 | 14 | 0 |
| Egress | 3 | 3 | 0 |
| Cache | 5 | 5 | 0 |
| Injection | 4 | 4 | 0 |
| Input | 4 | 4 | 0 |
| MCP schema | 2 | 2 | 0 |
| Reliability | 8 | 6 | 2 |
| **Total** | **40** | **38** | **2** |

Full details: `reports/tavily-comparison/SECURITY-RESULTS.json`.

---

## 5. Findings

### 5.1 Medium: no HTTP 429/503 retry

`REL-RETRY-001` and `REL-RETRY-002` each made one request and returned `http_error`. The fetch layer retries transport failures (timeout/truncated body), but not rate-limit or service-unavailable status codes.

Impact: transient provider conditions become terminal errors. This is a reliability gap, not an SSRF or injection bypass.

Remediation: bounded retry for 429/502/503/504 with `Retry-After`, at most two attempts, jitter, total deadline; record retry counts.

### 5.2 Low/residual: injection is flagged, not removed

The injected passage is returned with an `ignore_instructions` flag; the comment fixture produces `html_comment_instructions`. The contract says retrieved content is data, never instructions. A caller that ignores flags can still consume the text.

Remediation: strict mode that drops flagged passages; keep the warning-only mode for transparency.

### 5.3 No critical/high finding in this suite

The controlled suite found no critical or high-severity bypass. This does not establish absence of unknown vulnerabilities.

---

## 6. Limitations

- No independent penetration test or code audit.
- No OS/container sandbox; browser proxy is application-level only.
- No browser crash-loop, renderer compromise, WebSocket, download, or HTTPS interception test.
- No full MCP conformance run; schema validation was exercised directly.
- Injection detection is heuristic.
- SSRF coverage is case-based, not exhaustive.
- No volumetric load or third-party DoS.
- Windows-only environment.
- The 10,000-row synthetic corpus was excluded from quality scoring.

---

## 7. Evidence

- `reports/tavily-comparison/raw/security.jsonl` — 40 case records.
- `reports/tavily-comparison/raw/security_summary.json` — run summary.
- `reports/tavily-comparison/SECURITY-RESULTS.json` — structured results/findings.
- `reports/tavily-comparison/raw/browser_fixture.jsonl` — browser routing evidence.
- `reports/redteam/00-environment-fingerprint.json` — environment.
- `reports/_archive/prior-run-20261027/` — superseded prior claims, not evidence.
