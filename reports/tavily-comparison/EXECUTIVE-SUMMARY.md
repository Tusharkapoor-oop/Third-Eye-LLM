# Executive Summary

**Campaign:** `stage7-20261028-a4a64151`  
**Date:** 2026-10-28  
**Dataset:** 108 frozen hand-labelled queries, SHA-256 `a4a64151fbdbda850a9de128bb7f83ec67f126b633aac42488c6f0b9296a9b21`  
**Split:** 81 dev / 27 sealed test  
**Systems:** Direct Tavily, WebLens keyless (`ddg,mwmbl,wikipedia`, fuse), WebLens-Tavily  
**Evidence:** `reports/tavily-comparison/`

---

## Bottom line

**Tavily direct is the quality leader. WebLens keyless is the mean-speed and payload-size leader. WebLens-Tavily recovers most of Tavily's quality but is a Tavily-backed optimization layer, not an independent engine.**

The correct release decision is **CONDITIONAL GO** for the default keyless local/single-user configuration, with documented quality and security limits. It is **NO-GO** for an unconditional production certification, multi-tenant security certification, Tavily-quality parity claim, conflict-detection claim, or full MCP conformance claim.

---

## 1. Headline results

### Sealed test (27 queries, 17 answerable)

| Metric | Direct Tavily | WebLens keyless | WebLens-Tavily |
|---|---:|---:|---:|
| Search precision@5 | **0.2706** | 0.0588 | **0.2706** |
| Search support | **1.0000** | 0.5294 | **1.0000** |
| Research support | — | 0.5294 | **0.9412** |
| No-result accuracy | — | 0.4000 | **0.8000** |
| False confidence | — | 0.6000 | **0.2000** |
| Conflict recall | — | 0.0000 | 0.0000 |

### Combined (70 answerable queries)

| Metric | Direct Tavily | WebLens keyless | WebLens-Tavily |
|---|---:|---:|---:|
| Search precision@5 | **0.2571** | 0.1686 | 0.2429 |
| Search support | 0.9714 | 0.6714 | **0.9857** |
| Research support | — | 0.7857 | **0.9143** |
| Mean search latency | 1,637.3 ms | **886.8 ms** | 901.1 ms |
| Mean payload tokens | 1,034.1 | **505.3** | 891.2 |

Paired direct-minus-keyless:

- Precision@5: `+0.0886`, 95% CI `[0.0257, 0.1486]`.
- Support: `+0.3000`, 95% CI `[0.1857, 0.4143]`.
- Latency: keyless is faster by `750.5 ms`, CI `[580.1, 906.9]`.
- Payload tokens: keyless uses `528.7` fewer, CI `[455.0, 604.1]`.

The quality and efficiency wins are real but belong to different systems. There is no single winner on every axis.

### Research and extraction

- WebLens-Tavily research support beats keyless: `+0.1286`, 95% CI `[0.0143, 0.2429]`, but is `929.4 ms` slower on paired answerable rows (`n=70`).
- Extraction: Tavily `10/10` support; WebLens full `7/10` with two genuine errors (SitePoint HTTP 403, Reddit JavaScript-only page). WebLens uses far fewer text tokens (`2,421` vs `12,214` mean) but is not equivalent.
- Map/crawl: Tavily returned 10 map / 3 crawl results; WebLens keyless returned 0 / 0 while reporting `ok`. Do not claim parity.

### Conflict and abstention

- Conflict recall is **0/18** overall: `0/8` numeric and `0/10` conceptual. This is a measured failure.
- Unanswerable false confidence is **45%** for keyless and **35%** for WebLens-Tavily combined. Abstention is not reliable.

### Performance and load

- All three search modes are below the pre-registered 5,000 ms p95 gate on this run. Keyless p95 `2,513.8 ms`; direct Tavily `2,531.4 ms`; WebLens-Tavily `2,539.9 ms`.
- The keyless advantage is in the typical case, not the tail.
- Small load probe (6 queries, concurrency 1/2/5): WebLens-Tavily stayed `ok`; keyless mostly returned `partial`. This is not a production capacity test.

### Security and reliability

- Controlled suite: **40 cases, 38 PASS, 2 FAIL, 0 critical, 0 high**.
- SSRF/private-network/redirect/alternate-URL cases: 14/14 PASS.
- Browser proxy private HTTP and CONNECT: 3/3 PASS.
- Cache corruption/cap/auth separation: 5/5 PASS.
- Injection detection: 4/4 PASS, with the residual risk that flagged text is still returned.
- MCP schema validation: 2/2 PASS.
- **Two failed retry cases (one medium finding):** `SafeFetcher` does not retry HTTP 429 or 503. Each produced one request and a terminal `http_error`. This is a reliability gap, not a security bypass.
- No independent penetration test, browser sandbox audit, or full MCP conformance run was completed. The browser proxy is application-level egress control, not an OS/container sandbox.

### Verification

- `uv run pytest -q`: **163 tests, 0 failures, 0 errors, 0 skipped** (`data/pytest.xml`).
- `uv run ruff check .`: **All checks passed**.
- `uv lock --check`: **lock is current** (75 packages).
- `uv run pyright src/weblens/extract/html.py tests/test_extract.py`: **7 pre-existing errors**, no clean type-check claim. The new `age_days` test itself is not flagged.
- Controlled security harness: **38 PASS / 2 FAIL** (rerun 2026-11-01 under Python 3.14.0; the earlier 3.13.15 run is preserved).
- Secret scan: **0** live-key-format matches in the current campaign deliverables; code examples mentioning `OPENAI_API_KEY` are not credentials.

### Cost

- Tavily plan: `Researcher`, 1,000 credits.
- Before: 170 used. Final: **551/1,000 used, 449 remaining**.
- Campaign delta: **381 credits**, within the 420 cap and above the 200 stop.
- Observed paid calls: 375 search, 10 extract, 1 map, 1 crawl. Meter deltas differ by one search credit; the discrepancy is preserved.
- No invoice or per-credit USD price was available. Incremental USD cost is **not verified**.
- Tokens are `cl100k_base` counts of delivered JSON, not billed model tokens.

---

## 2. What changed during the campaign

- A real extraction bug was found and fixed: `age_days()` passed a string to date subtraction. The pre-fix extraction evidence is preserved; the post-fix run is the headline evidence. A regression test was added.
- The benchmark harness changed after the first smoke run and before the paid dev campaign. The change was harness-only; original and current hashes are recorded in `PREREGISTRATION.json`.
- The Tavily usage endpoint returned HTTP 429 mid-campaign. A final authenticated check succeeded and supersedes stale snapshots.

---

## 3. Integrity disclosure

The recorded preregistration timestamp is `2026-10-28T03:10:00Z`, but paid dev search started at `03:05:15Z` and smoke search at `03:00:28Z`. The campaign is therefore **not** a clean preregistered-before-all-evaluation study. The test split was opened after dev collection, but the final analyzer artifact was generated after the test run. This is disclosed in `PREREGISTRATION.json` (`timing_audit`) and `METHODOLOGY.md`.

The scoring rules and thresholds are frozen in the preregistration file and were not changed after test observation. That mitigation does not erase the timing violation. Any future campaign must write and hash the preregistration before the first paid call.

---

## 4. Release gates

| Gate | Result | Decision |
|---|---|---|
| Controlled SSRF/private-network/redirect/scheme/proxy/injection/oversize/auth | 38 PASS; 2 retry FAILs outside the listed bypass set | Security bypass gate passes; reliability gate fails |
| Keyless quality non-inferiority | Fails on precision@5 and support | Do not market keyless as Tavily-quality |
| Research quality | Keyless fails; WebLens-Tavily improves but is Tavily-backed | No independent research parity claim |
| Conflict detection | 0/18 | No contradiction-handling claim |
| Abstention | 45% keyless false confidence | No reliable no-answer claim |
| Extraction | 7/10 support; 2 hard errors | No extraction parity claim |
| Map/crawl | 0 results keyless | No crawl/map parity claim |
| Search latency p95 | All under 5 s | Operationally viable |
| MCP conformance | Not completed | No conformance claim |
| Browser isolation | Application-level egress only | No sandbox claim |
| Budget | 381/420 credits; 449 remaining | PASS |

---

## 5. Recommendation

**CONDITIONAL GO** for default keyless, local/single-user use, with these conditions:

1. Fix bounded HTTP 429/503 retry before the next reliability gate.
2. Treat extraction 403/JavaScript failures and zero conflict recall as known product gaps.
3. Do not advertise keyless precision/support, research, abstention, crawl/map, or extraction parity with Tavily.
4. Keep Tavily optional and paid. Describe WebLens-Tavily as a Tavily-backed optimization layer.
5. Do not claim full MCP conformance, browser sandbox isolation, or multi-tenant security certification.

**NO-GO** for an unconditional production certification or any claim that the system is security-equivalent to an isolated sandbox, conflict-aware, or Tavily-quality without qualification.

---

## 6. Superseded artifacts

Prior `reports/redteam/` and `reports/extreme-benchmark/` artifacts claimed an unconditional full pass, 38/38 SSRF, 401/401 tests, and production certification. Those claims are not supported by this campaign's measured evidence. They have been moved to `reports/_archive/prior-run-20261027/` for historical preservation and are superseded by the truthful reports in this directory and the regenerated red-team/extreme-benchmark reports. No historical file was deleted.
