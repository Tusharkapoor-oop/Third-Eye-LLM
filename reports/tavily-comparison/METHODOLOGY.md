# Methodology

**Campaign:** `stage7-20261028-a4a64151`  
**Base commit:** `902415d49f8da502b9de0e1c78da7f5777a1d2f8`  
**Campaign window:** 2026-10-28T03:00Z–10:25Z  
**Evidence root:** `reports/tavily-comparison/`

---

## 1. Question and scope

This campaign compares three operating modes on the same frozen query set:

1. **Direct Tavily** — raw `POST https://api.tavily.com/search` results, with no WebLens filtering.
2. **WebLens keyless** — default providers `ddg,mwmbl,wikipedia`, `search_mode=fuse`.
3. **WebLens-Tavily** — WebLens orchestration with Tavily as the search backend, `search_mode=fallback`.

The comparison covers quality, performance, extraction, browser fallback, map/crawl, cost/token accounting, controlled security probes, and failure behavior.

It does **not** establish:

- full MCP protocol conformance,
- an OS/container sandbox or browser isolation guarantee,
- Tavily-internal security,
- production capacity under stress,
- human-judged relevance,
- true recall,
- general web coverage.

---

## 2. Dataset

### 2.1 Frozen file

`reports/tavily-comparison/data/stage7_dataset.jsonl`

- 108 unique hand-labelled rows.
- SHA-256: `a4a64151fbdbda850a9de128bb7f83ec67f126b633aac42488c6f0b9296a9b21`.
- Split: 81 dev / 27 sealed test.
- Categories: `docs` 28, `niche_technical` 22, `current_facts` 20, `unanswerable` 20, `conflicting` 18.
- Answerable: 70; unanswerable: 20; conflicting: 18.

The split was assigned by the frozen builder before the test run. The test split was opened once, after dev collection. The final analyzer artifact was generated after the test run; the timing audit in `PREREGISTRATION.json` records this limitation. No test row was used to change code, labels, provider settings, or thresholds.

### 2.2 Source hashes

- `weblens/benchmarks/queries.jsonl`: `442c7bfc90acc3aef89a22d17ebf24ec8a2b6e310ed10ceab32aa0df2ca9ccba`
- `benchmarks/eval_dataset.json`: `846b4de9b38de945821ad56e5bd4fa2375af9640164b9e9c2de6bf8245e32df1`

### 2.3 Why 108 and not 500 or 10,000

Only 58 WebLens queries and 50 root queries had hand labels. That yields 108 honest rows. A 500-query campaign would require inventing labels or treating domain guesses as ground truth. The 10,000-row synthetic corpus was inspected and excluded:

- whole-file hash `d1d91fe1...` matched the published card,
- but the file had only 5,528 unique `query_text` values for 10,000 rows,
- all 10,000 `required_factual_claims` values were placeholders,
- 350 query texts contained generated `system_component_N` tokens,
- only 2 distinct `acceptable_domains` sets existed,
- manifest/card partition hashes did not reproduce.

The 10,000-row corpus is therefore not used for scoring. The 500-query and 10,000-query targets are documented as **NOT ACHIEVED**, not simulated.

### 2.4 Label limitations

- Relevance is strict labelled-domain membership, not human relevance.
- Recall@5/10 is not estimable: there is no exhaustive relevant-URL set.
- nDCG is binary with ideal DCG=1; it is rank-sensitive but not graded relevance.
- Answer support is expected-term presence, not semantic correctness.
- No LLM judge was used.

---

## 3. Systems and configuration

| Mode | Configuration |
|---|---|
| Direct Tavily | Raw Tavily `/search`, `search_depth=basic`, `max_results=10`, no WebLens filter |
| WebLens keyless | `search_providers=ddg,mwmbl,wikipedia`, `search_mode=fuse`, `default_results=10` |
| WebLens-Tavily | `search_providers=tavily`, `search_mode=fallback`, `default_results=10`, cache disabled for measurement |
| WebLens research | `deep_research` over the selected search mode; keyless and WebLens-Tavily variants |
| WebLens extraction | Full-page and query-focused extraction; browser fallback disabled by default |
| Browser | Playwright Chromium through the loopback egress proxy; enabled only for the browser fixture phase |

Tavily keyed calls used an 8.0 s transport deadline for WebLens providers. Direct Tavily used a 15 s client timeout. No paid call was made after remaining credits fell below 200; the final campaign stayed above the stop.

---

## 4. Metrics

### 4.1 Search

- **Precision@k:** relevant returned URLs / returned URLs at rank ≤ k. Relevance = labelled domain.
- **Hit@k:** any labelled-domain hit at rank ≤ k.
- **MRR@10:** reciprocal rank of the first labelled-domain hit.
- **nDCG@5/10:** binary gain, ideal DCG=1; secondary only.
- **URL validity:** returned URL parses and has an allowed scheme/host.
- **Duplicate rate:** duplicate URL share.
- **Search evidence support:** frozen expected answer terms appear in title+snippet evidence. This is not answer correctness.
- **Latency:** client wall-clock from request start to payload.
- **Payload tokens:** `cl100k_base` count of the delivered JSON, not billed model tokens.

### 4.2 Research

- **Research answer-term support:** expected answer terms appear in extracted research finding claims.
- **No-result accuracy:** fraction of unanswerable rows whose status is `no_reliable_result`.
- **False confidence:** unanswerable row returns `ok`/`partial` with findings.
- **Conflict recall:** research sets a conflict flag or names the conflicting values. Numeric and conceptual sets are reported separately.
- **Citation structural error:** malformed URL, missing `fetched_at`, bad span, or text length not equal to span length. This does not prove the quote exists on the live page.

### 4.3 Extraction

- **Support:** expected answer terms appear in extracted text.
- **Text tokens:** `cl100k_base` count of extracted text.
- **Latency:** client wall-clock, including fetch and parse.
- **Status:** `ok`, `partial`, `no_reliable_result`, `possibly_outdated`, `error`.

### 4.4 Security and reliability

- Fixed status vocabulary: PASS, FAIL, ERROR, BLOCKED, SKIPPED, INCONCLUSIVE, CANCELLED.
- Controlled local fixtures only; no third-party attack traffic.
- A PASS means the expected control behavior was observed in that case, not that the component is universally secure.
- A FAIL is preserved even when a later fix exists; the pre-fix extraction evidence is retained separately.

### 4.5 Statistics

- Paired unit: query.
- Bootstrap iterations: 10,000.
- Seed: `20261028`.
- Confidence level: 95%.
- No family-wise correction; secondary comparisons are exploratory.
- Pairwise deletion only for the paired metric; missing provider results remain in the status ledger.
- Practical thresholds: precision/support absolute 0.05; latency ratio 0.8; token ratio 0.8. A winner is declared only when the point estimate clears the practical threshold and the CI excludes zero.

---

## 5. Run sequence and integrity

1. Dataset frozen; manifest and card written.
2. Smoke search/research (preserved, excluded from headline).
3. Harness-only fixes; hash amendment recorded.
4. Dev search: 81 queries × 3 providers = 243 records.
5. Dev research: 81 queries × 2 WebLens providers = 162 records.
6. Provider-raw subset: 30 queries.
7. Extraction: 10 targets; pre-fix run preserved, bug fixed, post-fix run recorded.
8. Crawl/map and load probes.
9. Browser fixture: 6 records.
10. Sealed test search: 27 × 3 = 81 records.
11. Sealed test research: 27 × 2 = 54 records.
12. Analysis: `data/analysis.json`.
13. Controlled security/reliability harness: 40 records. Rerun on 2026-11-01 under Python 3.14.0; the earlier Python 3.13.15 run is preserved as `raw/security_py313.jsonl`.
14. Final usage check and report assembly.

### 5.1 Pre-registration timing disclosure

The recorded preregistration timestamp is `2026-10-28T03:10:00Z`, but paid dev search started at `03:05:15Z` and smoke search at `03:00:28Z`. The campaign is therefore **not** a clean preregistered-before-all-evaluation study. The test split was opened after dev collection, but the final analyzer artifact was generated after the test run. This is disclosed in `PREREGISTRATION.json` (`timing_audit`). The scoring rules and thresholds are frozen in that file and were not changed after test observation; that mitigation does not erase the timing violation.

### 5.2 Harness hash amendment

`stage7_run.py` changed after the first smoke run and before the paid dev campaign. The change was harness-only:

- resume key includes phase tag,
- fixture HTML uses `id="app"` for the JavaScript-shell detector,
- injection flags captured.

No scoring rule, split, label, or provider setting changed. Original and current hashes are in `PREREGISTRATION.json`.

### 5.3 Extraction bug

`age_days()` in `weblens/src/weblens/extract/html.py` passed a string to date subtraction. The pre-fix extraction run failed accordingly. The fix and a regression test were added; the post-fix run is the headline extraction evidence. Both runs are preserved.

---

## 6. Environment

- Windows 11 x64.
- Python 3.14.0 via `uv` (the historical red-team file claimed 3.13.15; the current fingerprint is authoritative).
- Playwright Chromium available for the browser fixture.
- Local SQLite cache.
- Network access through the host's normal egress; browser traffic through the loopback proxy.
- No OS/container isolation was configured for this campaign.

Exact values are in `reports/redteam/00-environment-fingerprint.json` and `SECURITY-RESULTS.json`.

---

## 7. Cost accounting

- Account plan: Tavily `Researcher`, 1,000 credits.
- Before campaign: account usage 170.
- Final check: `2026-10-28T10:25:24Z`, account usage 551/1,000; 449 remaining.
- Campaign delta: 381 credits.
- Campaign cap: 420; hard stop: 200 remaining. Both respected.
- Key usage endpoint reported 520/1,000; account and key values differ and are not reconciled by Tavily.
- No invoice or per-credit USD price was available; incremental USD cost is **not verified**.
- Observed paid calls from raw/meta: 375 search, 10 extract, 1 map, 1 crawl. Meter deltas: 376 search, 4 extract, 1 map, 0 crawl. The 1-credit search difference is unreconciled and preserved.

The usage endpoint returned HTTP 429 mid-campaign, so mid-campaign meta snapshots are stale. `raw/usage_final.json` is the authoritative final accounting.

---

## 8. Evidence map

| Artifact | Purpose |
|---|---|
| `raw/search_dev.jsonl` | 243 dev search records |
| `raw/search_test.jsonl` | 81 sealed test search records |
| `raw/research_dev.jsonl` | 162 dev research records |
| `raw/research_test.jsonl` | 54 sealed test research records |
| `raw/provider_raw.jsonl` | 30 provider-raw comparisons |
| `raw/extraction.jsonl` | Post-fix 10-target extraction |
| `raw/extraction_pre_fix.jsonl` | Preserved pre-fix extraction failures |
| `raw/browser_fixture.jsonl` | 6 browser/HTTP fixture records |
| `raw/load.jsonl` | 6 load cells |
| `raw/crawl_map.jsonl` | 4 crawl/map records |
| `raw/security.jsonl` | 40 controlled security/reliability records |
| `raw/usage_final.json` | Final Tavily usage check |
| `data/analysis.json` | Consolidated metrics |
| `QUALITY-RESULTS.json` | Quality and conflict/no-result results |
| `PERFORMANCE-RESULTS.json` | Latency, load, browser, crawl |
| `COST-AND-TOKEN-RESULTS.json` | Credits and token counts |
| `SECURITY-RESULTS.json` | Controlled security results and findings |
| `PREREGISTRATION.json` | Frozen rules plus amendments/timing audit |

---

## 9. What was not measured

- 500-query or 10,000-query quality. Not feasible with honest labels and budget.
- Human relevance judgments.
- True recall.
- Tavily Research answer correctness (non-equivalent endpoint).
- Brave (no API key).
- Full MCP conformance (official runner not completed on Windows).
- OS/container/browser sandbox isolation.
- Production capacity or sustained load.
- Tavily internal security.
- Network bytes for WebLens (only payload bytes captured).
- Browser child-process CPU/RSS (Windows probe failed).

These are reported as limitations, not inferred as passes.
