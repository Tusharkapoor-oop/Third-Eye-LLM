# WebLens Independent Final Verdict

**Verdict:** `FAIL - NOT ACCEPTED`  
**Audit date:** 2026-11-05 (Asia/Kolkata)  
**Original audit base:** `044cf4a17a06ef1641051623885dd73bc0db0bbc`; campaign synthesis at `b3a0b62`; latest `main` `4e0885d` is a docs-only deployment record  
**Deployed revision audited:** `weblens-00008-t5p`  
**Public endpoint:** `https://weblens-fgunqcnrla-uc.a.run.app`  
**Machine-readable summary:** `reports/independent-audit/acceptance.json`  
**Full audit:** `reports/independent-audit/AGENT30_INDEPENDENT_AUDIT.md`

## 1. Independence limitation

This session did **not** launch 30 genuinely independent specialist subagents. The workspace already had an external multi-agent campaign actively writing `reports/domination/` and running benchmarks. Duplicating that campaign would have collided with its benchmark data and could have corrupted the evidence.

The harness available here exposes only the `explore` and `general` subagents. Those are not 30 isolated specialist environments. I therefore acted as an independent auditor of the external campaign's evidence and re-ran the decisive checks myself. I did not count report labels as independent agents.

There are **29 numbered agent reports** plus a master synthesis. There is no independent `agent30` report. The master synthesis is not a substitute for a 30th workstream. Agent28 claims the fuzz suite passed in 31.43 s, but direct observation showed the same test still running after more than four minutes despite `addopts = "--timeout=60"`; the timeout evidence is conflicting, not clean.

## 1.1 Independent fresh GitHub install and real-world run

Two subagents were used as requested. Subagent 1 cloned and installed the canonical `weblens` package from GitHub commit `b3a0b62` into an isolated temp venv (Python 3.13.15), with 58 packages and 14 CLI invocations. Subagent 2 independently re-ran six key commands with fresh caches, audited all 49 raw artifacts, and checked accuracy against live ground truth. Six of six reruns exited 0; secret scan found 0 matches; no Tavily or paid API was used.

| Capability | Actual observation | Verdict |
|---|---|---|
| Install / version | Clean clone `b3a0b62`; editable install; `weblens 0.1.0`; no global install; workspace venv untouched | **PASS** |
| Search | 5 results, 5 unique URLs, titles/snippets present; DuckDuckGo `TimeoutError`; 2/5 results off-topic | **PARTIAL** |
| Extract example.com, requested query | `no_reliable_result`, **0 passages**; lexical query terms had no match | **FAIL** |
| Extract example.com, `--full` | Exact 156-character live page text; title `Example Domain` present | **PASS** |
| Extract example.com, alternate query | 1 passage with the exact page sentence | **PASS** |
| Extract Python 3.14 docs | 2 passages; 488 tokens; template strings, deferred annotations, subinterpreters, `compression.zstd` present | **PASS** |
| Map example.com | 1 URL, 0 duplicates; `no_links_found` matches the page's 0 anchors | **PASS** |
| Map docs.python.org | 5 unique URLs, 0 duplicates, all on `docs.python.org` | **PASS** |
| Crawl asyncio docs | 2 pages, both `ok`, 2 passages, 562 tokens; no `page_failures` field | **PASS with caveat** |
| Research example.com | 4 findings / 3 distinct sources; all 4 traceable; 1 off-topic; extractive only, no LLM prose | **PARTIAL** |
| Research Python 3.14 | 2 findings / 1 source; **0/2 claims mention 3.14**; self-reports `no_source_for:3.14` | **FAIL** |
| Real-world overall | Deterministic extract/map/crawl work; keyless search and version-specific research do not | **PARTIAL** |

Accuracy details:

- The live `example.com` page in November 2026 is a **156-character stub** containing ?documentation examples,? but not ?illustrative examples? and no `iana.org` link. The review plan's expected text was stale. The extractor was faithful; the failure is query-mode passage selection returning zero passages for a terse page. `--full` is the reliable path.
- Search returned the correct first result (`https://docs.python.org/3.14/whatsnew/3.14.html`, HTTP 200), but also `History of Python` and `CPython`, which are off-topic. The primary general-web provider (DuckDuckGo) timed out, leaving only MWMbl + Wikipedia.
- Research is extractive-only by design: every finding is a verbatim sentence with a URL and span. There is no LLM synthesis. The Python 3.14 run returned generic release-cadence prose, not 3.14 features, even though the extract command had just retrieved the correct 3.14 page. This is a real retrieval/coverage defect, honestly self-reported by the tool's gap field.
- Provenance: the install is pinned to `b3a0b62`. Latest `main` `4e0885d` differs only in three deployment/report documentation files; no code changed. The primary working tree is dirty; its uncommitted changes were not attributed to the GitHub install.

Evidence: `reports/independent-audit/github-install-run/` (49 raw files), `reports/independent-audit/github-install-review/REVIEW.md`, `reports/independent-audit/github-install-review/review.json`, and `reports/independent-audit/github-install-review/review-raw/`.

## 2. Decisive quality result: V10, 120 queries

The authoritative V10 run used 120 curated queries across 30 categories, 60 development and 60 held-out, with 120 raw records and 107 graded. It compared local WebLens, deployed WebLens, and Tavily on the same queries.

| Metric | Local WebLens | Deployed WebLens | Tavily |
|---|---:|---:|---:|
| Success rate | 0.900 | 0.942 | 1.000 |
| P@5 | 0.553 | 0.471 | **0.740** |
| nDCG@5 | 0.669 | 0.729 | **0.777** |
| Hit@5 | 0.729 | 0.832 | **0.935** |
| p50 latency | **837.0 ms** | 1,037.8 ms | 1,537.4 ms |
| Tokens | **182.3** | 206.2 | 1,378.7 |

Paired local-minus-Tavily P@5: **-0.187**, 95% CI **[-0.265, -0.108]**, 24 wins / 34 ties / 49 losses. The confidence interval excludes zero, so this is not noise.

The required P@5, nDCG@5, Hit@5, and success gates are not met. The local system is faster and far more token-efficient, but it retrieves materially worse results.

## 3. Tavily use cases are not at parity

The corrected V10 evidence-only use-case run, which excludes query/input echoes and counts only output evidence fields:

| Metric | WebLens | Tavily |
|---|---:|---:|
| Mean facet coverage | 0.263 | **0.844** |
| Evidence URLs present | 4/8 | **8/8** |
| Tokens | **149.1** | 1,278.6 |
| Latency | 9,102.4 ms | **332.3 ms** |

The older v14 use-case report gives WebLens scores of 55-70 while reporting `sources_count: 0` for **all 8** WebLens cases. Those scores are not evidence-grounded. Reports that cite the v14 figures as proof of use-case dominance are rejected.

## 3.1 Tavily capability matrix

| Capability | Evidence | WebLens status | Tavily comparison |
|---|---|---|---|
| Search | V10 120-query held-out run | P@5 0.553, nDCG 0.669, Hit@5 0.729, success 0.900; p50 837.0 ms; 182.3 tokens | Tavily P@5 0.740, nDCG 0.777, Hit@5 0.935, success 1.0; p50 1,537.4 ms; 1,378.7 tokens. Tavily wins quality; WebLens wins latency/tokens. |
| Extraction | No validated canonical corpus; agent20 describes legacy tiered extractor | `UNVERIFIED` | No head-to-head extraction run. The claimed 8.23x-18.09x density is stale/legacy and not accepted. |
| Crawl | agent21 ran 7 local tests; no Tavily crawl run | `UNVERIFIED / REJECTED as parity` | Tavily crawl not executed; no page-coverage, duplicate-rate, or cost comparison. |
| Map | agent21/agent08 local sitemap/link tests | `PARTIAL / UNVERIFIED` | Tavily map not executed; no ground-truth URL coverage comparison. |
| Deep research | V10 use cases: 0.263 vs 0.844; agent22 cites zero-source v14 | `FAIL / UNVERIFIED` | Tavily leads evidence coverage 0.844 vs 0.263 and evidence URLs 8/8 vs 4/8; WebLens latency 9,102.4 ms vs 332.3 ms. |
| Application workflows | 9/9 live WebLens workflows | `PARTIAL` | No head-to-head Tavily application-workflow evaluation; operational success is not quality parity. |

## 3.2 Remediation changelog (verified code changes)

The campaign made real code changes, not just report edits. The verified changes include:

- `Crawl2RAG`: text/token handling, fallback behavior, honest status, and `page_failures`.
- Meeting-prep fallback search and company official-domain ranking.
- `clean_query` and research scoring.
- Expanded prompt-injection and exfiltration patterns.
- `config.py`: corrected environment-variable handling.
- `src/engine/extract/chunker.py`: corrected chunk start/end offsets.
- `src/engine/search/aggregator.py`: concurrent extraction of candidate documents.
- `src/weblens/extract/passages.py`: `spread_chunks` for tail reachability (uncommitted at audit time).

These changes are useful, but they do not establish the 0.95 quality gates. Some are uncommitted, and the campaign's tests still target legacy modules. Evidence: `docs/changelog/2026-11/05-20-agent-verification-and-remediation/changelog.md` and `git diff --stat`.

## 4. Security: current deployment still fails high-severity checks

I re-tested the actual current revision `weblens-00008-t5p`, not the stale `weblens-00006-l9h` result.

Observed on 2026-11-05T21:31+05:30:

- Unauthenticated MCP `initialize`: **HTTP 200**, server info returned.
- Bogus `Authorization: Bearer bogus-token-not-valid`: **HTTP 200**, server info returned.
- `tools/list`: 10 tools returned: `web_search`, `extract_url`, `crawl_site`, `deep_research`, `company_research`, `market_research`, `market_portfolio`, `meeting_prep`, `sheets_enrich`, `tutorial_101`.
- Stateful tools: `crawl2rag_index`, `crawl2rag_query`, and `research_chat` are **absent**. This is a correct mitigation for the previously found cross-tenant state leak, but it removes functionality rather than isolating tenants.
- 20 unauthenticated `tools/list` calls: **20x200, 0x429**. No application-level rate limit was visible.
- `Strict-Transport-Security`: **missing**.
- `/healthz`: **404**; the root `/` returns the health JSON.

Status: **2 high authentication failures, 1 medium rate-limit finding, 1 low HSTS finding**. The stale v2 audit's findings reproduce on the current revision; they are not fixed.

Evidence: `reports/independent-audit/deployed_security_00007.json` (first test) and `reports/independent-audit/deployed_security_00008.json` (current revision).

Local security tests are real but limited:

- Local audit v2: 38 PASS / 0 FAIL.
- Agent14: 38 injection/sanitization unit tests pass.
- Agent26: 100 parameterized local SSRF tests pass, but they exercise `src.engine` / `src.weblens` local code, not the deployed endpoint, authentication, or live DNS rebinding.

Agent25's "verified tenant compartmentalization" claim is rejected. Hashing a cache key with an authorization header does not create tenant identity on an endpoint that accepts every caller. Agent25's "distroless / minimal Python base" claim is also false: the Dockerfile is `FROM python:3.11-slim` with no `USER` directive.

## 5. Report-by-report integrity findings

The campaign produced many `100% PASS` labels that do not measure what they claim. The decisive examples:

| Report | Claim | Audit status | Reason |
|---|---|---|---|
| agent02 | 100% relevance | **REJECTED** | 7 unit tests; no P@5, nDCG, or Hit@5. V10 P@5 is 0.553. |
| agent03 | performance PASS | **REJECTED** | Measured legacy `src.engine.search.aggregator` p50 3.87 s; canonical probe p50 1.489 s. |
| agent04/05/06/20 | FlashRank / tiered extraction | **REJECTED** | Canonical `weblens` has no FlashRank; only legacy `src/engine/reranker.py` does. |
| agent09/10/11/12 | 100% scalability/quality/efficiency/citations | **REJECTED** | Legacy or lifecycle unit tests; no held-out factual, citation, or throughput measurement. |
| agent13 | 100% zero hallucination | **PARTIAL / REJECTED as 100%** | 10 curated cases; no 10k adversarial suite; Tavily "1/10" comparison has no cited artifact. |
| agent14 | 38 injection tests | **PARTIAL** | Real fixture tests; no hostile live-page corpus. |
| agent15/16 | model access | **VERIFIED (access only)** | Matches independent probe; no model-quality ranking. |
| agent17/18 | model orchestration | **PARTIAL** | Legacy provider path; fallback tests do not measure "100% cited facts". |
| agent19 | 8.23x density, Tavily dominance | **REJECTED** | Different corpus/arena; V10 paired P@5 is negative. The arena artifact was overwritten with a budget-blocked Tavily run. |
| agent20 | 8.23x-18.09x density | **REJECTED** | Legacy extractor; stale arena. |
| agent21 | Tavily crawl/map parity | **REJECTED** | 7 local tests; Tavily crawl/map was never run. |
| agent22 | deep research 61.9 vs 63.0 | **REJECTED** | Cites v14 report with `sources_count: 0` for all 8 WebLens cases. |
| agent23 | applications PASS | **PARTIAL / REJECTED as parity** | 9/9 operational run is real; does not fix 0.263 vs 0.844 coverage or 4/8 vs 8/8 evidence URLs. |
| agent24 | 100% MCP conformance; 5 core tools | **REJECTED for canonical MCP** | Tests import legacy `server.mcp` / `src.server.mcp_server` with `web_map` and `crawl_website`. Canonical core registers 4 tools and uses `crawl_site`. |
| agent25 | tenant isolation, distroless | **REJECTED** | Current 00008 accepts unauthenticated/bogus callers; no rate limit or HSTS; Dockerfile is `python:3.11-slim` with no non-root user. |
| agent26 | 100 SSRF vectors | **PARTIAL** | Local parameterized tests only; no deployed or live DNS-rebinding test. |
| agent27 | 100% performance | **REJECTED** | Legacy `SearchAggregator` burst test; no canonical/deployed baseline or 30% improvement. |
| agent28 | 350 tests collected; 2 arena failures | **PARTIAL / CONFLICTING** | Useful collection and admitted quality gap, but claims fuzz passed in 31.43 s while direct observation showed >4 min; core suites still include legacy/root tests. |
| agent29 | all 30 reports; 46-block chain | **PARTIAL / REJECTED as completeness** | 46-block chain independently verifies, but there are 29 numbered reports plus master synthesis, not 30 independent reports; it ignores the fuzz hang and arena overwrite. |
| master synthesis | final PASS_WITH_LIMITATIONS | **REJECTED as final synthesis** | Stale commit/revision in summary; repeats PASS labels for legacy and unit-test-only claims; admits two arena gate failures. |
| independent agent30 | missing | **NOT RUN** | No independent `agent30_*.md` evidence report exists. |

Additional integrity issue: `arena_report.json` was modified in the working tree. The current artifact shows Tavily `BLOCKED` with `BUDGET_CAP is not positive; Tavily was not called`, while agents 19 and 20 still quote the old live-Tavily density figures. The overwrite is saved at `reports/independent-audit/arena_overwrite.diff`. Those density claims are not reproducible from the current artifact.

## 6. Verified positives

These are real and should not be discarded:

- Nine application workflows passed a live end-to-end run: **9/9**.
- Local security audit v2: **38 PASS / 0 FAIL**.
- V10 provenance is clean: 120 raw records, 107 graded, dataset SHA-256 recorded.
- Canonical search is faster than the legacy aggregator and emits far fewer tokens than Tavily.
- The canonical/root mirror divergence was fixed; the `.py` files are byte-identical at audit time.
- Model-access findings are credible: Mistral Large accessible; GPT-OSS 20B times out; Mistral NeMo 12B is 404; "GPT-OSS 12B" is unsupported.
- The stateful cross-tenant leak was mitigated by removing the stateful tools from the public deployment.

## 7. Remaining blockers

1. Retrieval quality is far below the 0.95 gates (P@5 0.553 local, 0.471 deployed).
2. Deployment authentication, rate limiting, and HSTS remain unresolved on `weblens-00008-t5p`.
3. Dataset scale is 120 queries, not 100k; adversarial scale is 9 cases, not 10k.
4. There is no independent agent30; 29 numbered reports plus a master synthesis only.
5. Fuzz/chaos evidence conflicts: agent28 reports 31.43 s, but direct observation showed the same test still running after more than four minutes despite the 60-second timeout; no clean timeout evidence.
6. No validated held-out corpus exists for extraction completeness, crawl/map accuracy, research claim support, or citation precision/coverage.
7. Tavily parity is not demonstrated for crawl, map, extraction, or deep research; only search has a real 120-query comparison, and WebLens loses it.
8. Agent28 admits two arena quality failures: Engine A average 81.6 < 90, and zero tokens on a recency query. Two working-tree arena artifacts also disagree (81.6 vs 90.8) for the same five cases, and both have Tavily blocked.
9. Model ranking is blocked by upstream timeouts/404s.

## 8. Evidence index

- `reports/three-system-comparison-v10/analysis/analysis.json`
- `reports/three-system-comparison-v10/V10_REPORT.md`
- `reports/tavily-use-cases-v10/results.json`
- `reports/v14/tavily_demo_use_cases_report.json`
- `reports/deployed-security/deployed_security_results_v2.json` (stale 00006)
- `reports/independent-audit/deployed_security_00007.json` (first test)
- `reports/independent-audit/deployed_security_00008.json` (current 00008)
- `reports/independent-audit/canonical_mcp_surface.json`
- `reports/independent-audit/canonical_search_probe.json`
- `reports/independent-audit/static_audit.json`
- `reports/independent-audit/arena_overwrite.diff`
- `reports/independent-audit/report_inventory.json`
- `reports/independent-audit/fuzz_timeout_observation.json`
- `reports/independent-audit/fuzz_rerun_observation.json`
- `reports/independent-audit/github-install-run/RESULTS.md`
- `reports/independent-audit/github-install-run/manifest.json`
- `reports/independent-audit/github-install-review/REVIEW.md`
- `reports/independent-audit/github-install-review/review.json`
- `reports/arena_full_budget_2026-11-05.json`
- `reports/nine_applications_verification.json`
- `evidence/SECURITY-FINDINGS.md`
- `evidence/CLAIM_LEDGER.md`

## 9. Final decision

**`FAIL - NOT ACCEPTED`**

WebLens has genuine strengths, but it does not meet the mandatory quality, security, scale, or evidence gates. The campaign's 100% labels are not acceptable where they test the legacy stack, substitute unit tests for held-out measurements, cite zero-source reports, or quote an overwritten arena artifact.
