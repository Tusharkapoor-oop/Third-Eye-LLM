# WebLens Master Improvement Loop & Applications Summary (v7)

## 1. Executive Summary & Verification Ratchet
- **Evaluation Status:** COMPLETED
- **Ledger Head Hash:** `271bc8c3cc6b5b4ff81d80f86511f6106a3ee5f61818bc36a5716c5825125a53`
- **Total Valid Ledger Records:** 41 cryptographically chained entries in `evidence/ledger.jsonl`.
- **Package Tests:** 172 passed, 1 skipped (100% pass on executable tests).
- **Root Stack Tests:** 245 passed of 245 collected.
- **Tavily Credit Spend:** 0 credits consumed during this pass (preserved under 60% user quota budget).

---

## 2. Mandated Applications Program Deliverables

Under the v7 directive, WebLens implements fresh, independent versions of the 8 example applications popularized by Tavily, built on WebLens's local-first search, extraction, crawling, and security primitives.

### Mandated Application Status Table

| Application | Spec & Module | Test Suite & Gates | Results ($n$ & Intervals) | Security & Abuse Defenses | Schema Token Cost | Status | Evidence ID |
|---|---|---|---|---|---|---|---|
| **Crawl2RAG** | `weblens.apps.crawl2rag` | `test_crawl2rag_lifecycle` in `test_apps.py` | 2/2 pages indexed, 100% BM25 citation match | `DestinationPolicy` SSRF check on every link; polite 1 req/s crawl | 125 tokens (profile: full) | **SHIPPED** | `test_apps.py` |
| **Deep Research** | `weblens.apps.deep_research` | `test_deep_research_diversity_and_citations` | 2/2 claims cited with exact text spans; diversity ratio calculated | Claim-level citations; contradiction detection; refusal guard | Built-in core (126 tokens) | **SHIPPED** | `test_apps.py` |
| **Company Researcher** | `weblens.apps.company` | `test_company_researcher_real_and_fictional` | 100% detection of fictional companies (`status="not_found"`) | Entity disambiguation; zero hallucinated executive bios | 88 tokens (profile: research) | **SHIPPED** | `test_apps.py` |
| **Research Agent Chat** | `weblens.apps.chat` | `test_research_chat_session`, `test_research_chat_injection_quarantine` | Context retained across turns; history pruned within token budget | `scan_injection` quarantines malicious web text from context | Exposed via CLI/API | **SHIPPED** | `test_apps.py` |
| **Market Researcher** | `weblens.apps.market` | `test_market_researcher` in `test_apps.py` | Extracted verified metrics; returns `not_available` when unverified | Zero-guess policy; mandatory disclaimer included on 100% of outputs | 117 tokens (profile: research) | **SHIPPED** | `test_apps.py` |
| **Sheets Enrichment** | `weblens.apps.sheets` | `test_defang_formula`, `test_sheets_enricher` | 1/1 rows enriched with verified HQ; checkpointing verified | Formula injection defense: prepends `'` to dangerous `=, +, -, @` | Exposed via CLI/API | **SHIPPED** | `test_apps.py` |
| **Meeting Prep Agent** | `weblens.apps.meeting` | `test_meeting_prep_privacy_refusal`, `test_meeting_prep_public_brief` | 100% refusal on private personal information probes | Strictly public professional sources; zero calendar exfiltration | 146 tokens (profile: full) | **SHIPPED** | `test_apps.py` |
| **WebLens 101 Tutorial** | `docs/tutorials/WEBLENS_101.md` | `weblens/examples/tutorial_101.py` | End-to-end execution of all 7 modules passing in CI | Reproducible, verified code blocks; zero simulated outputs | N/A (Documentation/CLI) | **SHIPPED** | `tutorial_101.py` |

---

## 3. MCP Tool Profile Token Measurement

Measurements performed using `cl100k_base` tiktoken encoding via `weblens.cli tokens`:

| Profile | Tools Exposed | Tool Count | Measured Schema Tokens | Token Budget | Status |
|---|---|---|---|---|---|
| **`core` (default)** | `web_search`, `extract_url`, `crawl_site`, `deep_research` | 4 | **838 tokens** | $\le 1,000$ | **PASS — WITHIN BUDGET** |
| **`research`** | Core + `company_research`, `market_research` | 6 | **1,043 tokens** | Uncapped profile | **OPERATIONAL** |
| **`full`** | Research + `crawl2rag_query`, `meeting_prep` | 8 | **1,314 tokens** | Uncapped profile | **OPERATIONAL** |

---

## 4. Per-Slice Comparison Table versus Tavily Direct

*Evaluated on $n=70$ paired complex multi-hop queries (`rederive-stage7-raw`). Losses listed first.*

| Benchmark Slice / Metric | WebLens Keyless | Tavily Direct | Paired Difference [95% CI] | Statistical Test ($p$-value) | Winner |
|---|---|---|---|---|---|
| **Answer Support Rate** | 67.14% (47/70) [55.49%, 76.99%] | **97.14% (68/70)** [89.92%, 99.23%] | Tavily +30.00% [18.57%, 41.43%] | McNemar $p < 0.0001$ | **Tavily** |
| **Precision@5** | 0.1686 | **0.2571** | Tavily +0.0885 [0.0350, 0.1420] | Paired t-test $p = 0.0016$ | **Tavily** |
| **Conflict Detection Recall** | 0.00% (0/18) [0.00%, 18.00%] | **61.11% (11/18)** [38.62%, 79.69%] | Tavily +61.11% [38.62%, 83.60%] | McNemar $p = 0.0010$ | **Tavily** |
| **Search Latency (Mean)** | **886.8 ms** [812.5, 965.2] | 1,637.3 ms [1,520.1, 1,760.4] | WebLens -750.5 ms [-870.2, -630.8] | Paired t-test $p < 0.0001$ | **WebLens** |
| **Search Latency (Median p50)** | **657.4 ms** | 1,514.8 ms | WebLens -857.4 ms | Wilcoxon $p < 0.0001$ | **WebLens** |
| **Payload Tokens per Call** | **505.3 tokens** [472.1, 538.5] | 1,034.1 tokens [985.4, 1,082.8] | WebLens -528.8 tokens (51.1% smaller) | Paired t-test $p < 0.0001$ | **WebLens** |
| **Direct API Cost** | **$0.00 / 0 credits** | Commercial API credits | WebLens 100% cost reduction | Deterministic | **WebLens** |

---

## 5. Security & Threat Posture Summary
- **SSRF & Egress Protection:** 38 of 38 attack attempts blocked. Zero packets reached fixture destinations (`EXP-002`).
- **Canary & API Key Leaks:** Zero secrets committed in source or git history (`EXP-008`). Redaction active on all logging.
- **Benign Prompt Injection False Positive Rate:** 0.00% [0.00%, 0.04%] (0 false flags on 10,000 clean passages; `tier-d-injection-eval`).
- **English Prompt Injection Detection Recall:** 76.24% [75.04%, 77.40%] (3,812 of 5,000 flagged; `tier-d-injection-eval`).
- **Spreadsheet Formula Injection:** 100% sanitized by prepending `'` to dangerous characters (`=`, `+`, `-`, `@`).
- **Meeting Prep Privacy Boundary:** 100% refusal rate on personal attribute extraction requests.

---

## 6. Honesty Section: Remaining Limitations & Unverified Claims
1. **SearXNG Integration is BLOCKED:** SearXNG provider exists in code but is offline (`ConnectError [WinError 10061]`). Marked BLOCKED / NOT RUN.
2. **Non-English Prompt Injection Gap:** 0.00% detection recall across 528 non-English injection prompts (Spanish, French, German, Russian, Hindi, Chinese) because regex patterns match only English tokens.
3. **Headless Browser Disabled by Default:** Playwright browser execution is disabled by default (`WEBLENS_ALLOW_BROWSER=false`) to preserve memory and avoid orphan process leaks.
4. **Keyless Conflict Recall Gap:** On the 18 conflicting-sources benchmark items, WebLens keyless retrieval scored 0/18 (0.00%), failing to surface opposing chronological viewpoints.
