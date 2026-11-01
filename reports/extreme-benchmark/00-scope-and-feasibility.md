# Extreme-Scale Benchmark — Scope and Feasibility

**Campaign:** `stage7-20261028-a4a64151`  
**Date:** 2026-10-28  
**Requested target:** 500-query and/or 10,000-query extreme-scale comparison  
**Delivered target:** 108 frozen hand-labelled queries, 81 dev / 27 sealed test  
**Overall status:** **PARTIAL — 108-query evidence delivered; 500/10,000 not achieved**

This directory is the truthful equivalent of the requested extreme-scale deliverable. It does not claim that 10,000 queries were run. It records what was measured, why the larger targets were not feasible, and what would be required to reach them.

---

## 1. What was requested vs what exists

| Requested | Delivered | Status |
|---|---|---|
| 500-query comparison | 108-query frozen dataset | **NOT ACHIEVED** |
| 10,000-query comparison | 108-query frozen dataset | **NOT ACHIEVED** |
| Quality, performance, security, cost, failure behavior | All five covered at 108-query scale plus controlled security harness | **DELIVERED (small scale)** |
| 10,000-row synthetic corpus | Audited and excluded | **EXCLUDED** |
| Sealed holdout | 27 rows, opened once after dev collection | **DELIVERED, with timing disclosure** |
| Full production certification | Not supported | **NO-GO** |

The 500/10,000 targets are marked **NOT ACHIEVED**, not “passed by proxy.”

---

## 2. Why 500 queries was not reached

Only 58 WebLens queries and 50 root queries had hand labels. That is 108 honest rows. Reaching 500 would require one of:

1. Inventing labels, which would make the benchmark meaningless.
2. Treating domain guesses as ground truth, which the methodology explicitly rejects.
3. Spending far more time and paid budget than the campaign had.

The campaign had a 420-credit cap and a 200-credit hard stop. It consumed 381 credits on the 108-query design plus extraction, map/crawl, and load probes. A 500-query design would require at least 500 direct Tavily searches, 500 WebLens-Tavily searches, 500 research runs, and additional extraction targets. That is outside the verified budget.

---

## 3. Why 10,000 queries was not reached

The only 10,000-row file was the prior synthetic corpus at:

`reports/_archive/prior-run-20261027/extreme-benchmark/datasets/extreme_benchmark_10k.jsonl`

It was audited, not used. See `01-dataset-audit.md`.

Summary of defects:

- 10,000 rows but only **5,528 unique `query_text` values**.
- All **10,000** `required_factual_claims` are placeholder IDs such as `Claim-cat01_current_news-0`.
- **350** query texts contain generated `system_component_N` tokens.
- Only **2 distinct `acceptable_domains` sets** across 10,000 rows.
- The manifest’s dev/val/sealed_test partition hashes do **not** match the file.
- The manifest claims 10,000 unique queries; the file contradicts that claim.

Using this file would produce a large number, not a valid measurement. It was excluded before scoring.

---

## 4. What was actually measured

| Area | Evidence | Scale |
|---|---|---|
| Search quality | `raw/search_dev.jsonl`, `raw/search_test.jsonl` | 81 dev + 27 test queries × 3 systems |
| Research quality | `raw/research_dev.jsonl`, `raw/research_test.jsonl` | 81 dev + 27 test × 2 WebLens modes |
| Provider raw | `raw/provider_raw.jsonl` | 30 queries |
| Extraction | `raw/extraction.jsonl` | 10 targets |
| Browser | `raw/browser_fixture.jsonl` | 6 records |
| Load | `raw/load.jsonl` | 6 cells, 6 queries each |
| Crawl/map | `raw/crawl_map.jsonl` | 4 operations |
| Security/reliability | `raw/security.jsonl` | 40 controlled cases |
| Cost | `raw/usage_final.json` | Final account check |

Headline numbers are in `../tavily-comparison/EXECUTIVE-SUMMARY.md` and `02-quality-results.md`.

---

## 5. What “extreme” would require

A real 10,000-query campaign needs:

1. 10,000 human-labelled or independently verifiable rows with real factual claims.
2. A reproducible partition with hashes that match the manifest.
3. Budget for at least 10,000 direct searches, 10,000 WebLens-Tavily searches, 10,000 research runs, and extraction targets.
4. A pre-registration written and hashed before the first paid call.
5. A sampling plan for human relevance audits.
6. A security test plan that does not send attack traffic to third parties.

None of those conditions was met for 10,000. The 108-query campaign is the largest honest result available in this environment.

---

## 6. Status legend

- **DELIVERED** — measured with preserved raw evidence.
- **PARTIAL** — some requested scope measured, some not.
- **NOT ACHIEVED** — not measured; no estimate substituted.
- **EXCLUDED** — inspected and rejected as invalid ground truth.
- **NO-GO** — release claim not supported.

The extreme-scale deliverable is therefore **PARTIAL**, not a full pass.
