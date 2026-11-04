# WebLens Evidence-Backed Claim Ledger — V10 (authoritative as of 2026-11-04)

This ledger supersedes earlier claim tables where they conflict. Old claims are retained only in the “Corrected legacy claims” section so the correction is auditable. A claim is never marked PASS because code exists; it needs an executed artifact.

## Status vocabulary

| Status | Meaning |
|---|---|
| **Verified** | Reproduced from a named artifact in this repository. |
| **Partially verified** | True on the measured subset/environment; known gaps remain. |
| **Blocked** | Cannot be measured because a required external resource is unavailable. |
| **Unsupported** | No valid artifact supports the claim. |
| **Rejected** | Measured and contradicted by evidence. |
| **Not run** | Planned or possible, but not executed in this session. |

---

## 1. V10 measurement claims

| ID | Claim | Status | Evidence |
|---|---|---|---|
| CLM-V10-001 | The V10 dataset contains 120 unique curated queries, 30 categories × 4, 60 dev / 60 held-out, with SHA-256 `a42d4004fb91208f1ae18de89e2337f2ccf5e7cb580a3c600a8ec7d8057d6361`. | **Verified** | `weblens-lab/datasets/eval_benchmark_suite_v10.json`, `manifest_v10.json`, `reports/three-system-comparison-v10/dataset_validation_v10.json` |
| CLM-V10-002 | The 100k primary / 250k preferred / 500k stress query targets were met. | **Rejected / Blocked** | Achieved 120. Manifest and report state BLOCKED; no synthetic inflation was used. |
| CLM-V10-003 | Local WebLens was measured as a real MCP server process, not an in-process service import. | **Verified** | `run_v10_benchmark.py` starts `python -m weblens.cli serve --http --profile full`; raw records carry the endpoint. |
| CLM-V10-004 | Deployed WebLens was measured at its real Cloud Run endpoint. | **Verified** | `reports/three-system-comparison-v10/raw/run_full_v10_120.jsonl`, deployed records; service `weblens-00003-l9q`. |
| CLM-V10-005 | Tavily was measured directly through its own API, not through WebLens. | **Verified** | `tavily_direct` records; 120 credits; `search_depth=basic`, 5 results. |
| CLM-V10-006 | Local WebLens P@5 = 0.553, nDCG@5 = 0.669, Hit@5 = 0.729 on 107 graded queries. | **Verified** | `analysis/analysis.json`, `analysis.md` |
| CLM-V10-007 | Deployed WebLens P@5 = 0.471, nDCG@5 = 0.729, Hit@5 = 0.832 on 107 graded queries. | **Verified** | Same |
| CLM-V10-008 | Tavily P@5 = 0.740, nDCG@5 = 0.777, Hit@5 = 0.935 on the same 107 graded queries. | **Verified** | Same |
| CLM-V10-009 | Local P@5 is 0.187 below Tavily (paired mean −0.187, 95% CI [−0.265, −0.108], 24/34/49 W/T/L). | **Verified** | `analysis.md` paired table |
| CLM-V10-010 | Deployed P@5 is 0.082 below local (paired mean −0.082, CI [−0.142, −0.024]). | **Verified** | Same |
| CLM-V10-011 | Local p50 = 837.0 ms, deployed = 1037.8 ms, Tavily = 1537.4 ms. | **Verified** | `analysis.json` |
| CLM-V10-012 | Local mean tokens = 182.3, deployed = 206.2, Tavily = 1378.7 (`cl100k_base`). | **Verified** | `analysis.json`; tokenizer documented in runner |
| CLM-V10-013 | Success rate: local 0.900, deployed 0.942, Tavily 1.000; `partial` counts as a result-bearing success, `empty`/`error` do not. | **Verified** | `analysis.json`; status mix 37/71/12, 84/29/7, 120/0/0 |
| CLM-V10-014 | 13 of 120 queries are intentionally unanswerable/ambiguous/contradictory and are excluded from graded retrieval metrics. | **Verified** | `unanswerable` count; 107 graded per system |
| CLM-V10-015 | WebLens returns ~7.5× fewer tokens than Tavily on this dataset. | **Verified** | 182.3/1378.7 and 206.2/1378.7 |
| CLM-V10-016 | WebLens beats Tavily on relevance/reliability for this dataset. | **Rejected** | Paired P@5 CI is entirely below zero; Tavily also has higher success and Hit@5. |

---

## 2. Product workflow claims

| ID | Claim | Status | Evidence |
|---|---|---|---|
| CLM-V10-020 | All nine WebLens applications execute end-to-end: deep research, company researcher, chat, Crawl2RAG, market researcher, sheets enricher, meeting prep, tutorial, persistent chat. | **Verified** | `reports/nine_applications_verification.json`: 9 PASS / 0 PARTIAL / 0 FAIL, with per-app assertions |
| CLM-V10-021 | Crawl2RAG performs a real crawl → index → query cycle with passage spans, not just a status string. | **Verified** | Same: 2 pages / 43 passages indexed, 3 query hits, spans present |
| CLM-V10-022 | Persistent research chat survives reopening the session and exporting Markdown. | **Verified** | Same: 2 persisted messages, topic and 3 sources exported |
| CLM-V10-023 | The tutorial executes all nine steps. | **Verified** | Same: `steps_executed=9`, `passed_steps=9` |

---

## 3. Security claims

| ID | Claim | Status | Evidence |
|---|---|---|---|
| CLM-V10-030 | Local security audit v2 passes 38/38 checks after fixes. | **Verified** | `reports/local-security/local_security_results_v2.json` |
| CLM-V10-031 | SSRF blocking works on both local and deployed `extract_url` for metadata, loopback, RFC1918, IPv6 loopback, and `file://`. | **Verified** | Local: `local_extract_blocks_*` PASS. Deployed raw probe: structured `isError` with `non-public destination`, no page content. |
| CLM-V10-032 | The deployed MCP endpoint accepts unauthenticated `initialize` and a bogus Bearer token. | **Verified** | `reports/deployed-security/deployed_security_results_v2.json`; raw probe |
| CLM-V10-033 | No application-level rate limit was observed in 20 cheap `tools/list` calls. | **Verified observation** (not a load test) | Same: all HTTP 200, no 429 |
| CLM-V10-034 | The deployed service returns no HSTS header. | **Verified** | Same: `strict-transport-security: null` |
| CLM-V10-035 | The old deployed build accepts an oversize (~7.7k char) query. | **Verified** | Same: `status=no_reliable_result`; current local build rejects >2000 chars |
| CLM-V10-036 | Cross-tenant Crawl2RAG/chat data is isolated between clients on the public deployment. | **Unsupported (surface removed)** | Revision `00006` does not register stateful tools on an unauthenticated public listener; `deployed_cross_tenant_crawl2rag` is `UNSUPPORTED`, not PASS. True multi-tenant isolation was not implemented. |
| CLM-V10-036a | The pre-fix deployment leaked Crawl2RAG state across clients. | **Verified; Fixed** | Revision `00005` audit: a fresh client retrieved another client's unique probe (`probe_visible_in_other_client: true`). |
| CLM-V10-036b | The public deployment exposes 10 stateless tools and omits `crawl2rag_index`, `crawl2rag_query`, `research_chat`. | **Verified** | Deployed `tools/list`: 10 names; local loopback: 13 names including all three stateful tools. |
| CLM-V10-030a | The deployed v2 audit yields 18 PASS / 4 FAIL / 1 UNSUPPORTED on revision `00006`. | **Verified** | `reports/deployed-security/deployed_security_results_v2.json` |
| CLM-V10-037 | The deployment is fully hardened. | **Rejected** | Auth and rate limiting are not enforced; internal IAM/VPC was not inspected. |
| CLM-V10-038 | Prompt-injection detector misses “ignore all instructions … disclose keys” and “ignore previous directions … output confidential text”. | **Fixed; Verified** | Before/after `scan_injection` probe; `weblens/src/weblens/security/injection.py`; local audit PASS |
| CLM-V10-039 | Crawl2RAG reported `status: ok` with zero indexed pages. | **Fixed; Verified** | `apps/crawl2rag.py`; now returns `no_reliable_result` / `partial` |

---

## 4. Model access claims

| ID | Claim | Status | Evidence |
|---|---|---|---|
| CLM-V10-040 | Mistral Large 4 (`mistralai/mistral-large-4-1t-a52b`, NVIDIA) is reachable with the configured key. | **Verified** | HTTP 200; exact JSON response; 21.4 s; 41 prompt + 134 completion tokens (116 reasoning) |
| CLM-V10-041 | GPT-OSS 20B (`openai/gpt-oss-20b`) is usable. | **Blocked** | Two probes (60 s, 150 s) returned `ReadTimeout` with no completion. |
| CLM-V10-042 | Mistral NeMo 12B (`nv-mistralai/mistral-nemo-12b-instruct`) is usable. | **Blocked** | HTTP 404: function not found for this account. |
| CLM-V10-043 | “GPT-OSS 12B” was evaluated. | **Unsupported / Not run** | No such model ID is available; the 12B option is Mistral NeMo 12B, which returned 404. |
| CLM-V10-044 | Model A is better than model B on WebLens research tasks. | **Unsupported** | Only one model produced a completion; a ranking would be fabricated. |

---

## 5. Test-execution claims

| ID | Claim | Status | Evidence |
|---|---|---|---|
| CLM-V10-050 | 170 targeted root tests passed (security, SSRF, injection, crawler, extraction). | **Verified** | `pytest tests/test_injection_sanitization.py tests/test_03_security_boundaries.py tests/test_security.py tests/test_ssrf_penetration.py tests/test_crawler.py tests/test_crawler_traps.py tests/test_extract.py` → 170 passed in 16.7 s |
| CLM-V10-051 | 47 injection + app tests passed (including Crawl2RAG lifecycle). | **Verified** | `pytest tests/test_injection_sanitization.py weblens/tests/test_apps.py` → 47 passed in 21.1 s |
| CLM-V10-052 | The full root test suite passes in the current tree. | **Unsupported / Incomplete** | The run reached ~93% then hung for >15 min and was terminated; exit was non-zero. Earlier 248-pass result predates the edits. |
| CLM-V10-053 | The V10 dataset and raw records are reproducible from the runner. | **Verified** | `run_v10_benchmark.py --resume`; dataset SHA; 120 records |
| CLM-V10-054 | 10k adversarial cases were evaluated. | **Blocked** | 9 curated cases exist in `adversarial_suite.json`. |

---

## 6. Performance / cost claims

| ID | Claim | Status | Evidence / caveat |
|---|---|---|---|
| CLM-V10-060 | Local WebLens is 1.8× faster at p50 than Tavily on this dataset. | **Verified** | 837.0 vs 1537.4 ms |
| CLM-V10-061 | WebLens search used $0 provider credits (DDG/MWMbl/Wikipedia). | **Verified for provider credits** | `credits=0`; Cloud Run infrastructure cost is not included |
| CLM-V10-062 | Tavily consumed 120 credits for 120 queries. | **Verified** | `credits=1.0` per record |
| CLM-V10-063 | WebLens is cheaper per completed task overall. | **Partially verified** | Provider credits are zero; infrastructure/engineering cost was not measured |

---

## 7. Corrected legacy claims

| Legacy ID | Old assertion | Correction |
|---|---|---|
| CLM-003 | “Prompt injection scanner blocks 35/35 with 0% false positives.” | **Partially verified.** Curated suites pass after fixes; no universal 0% guarantee. Two real misses existed before SEC-V10-001. |
| CLM-004 | “Deployed Cloud Run instance blocks 10/10 remote penetration probes (SSRF, metadata, auth bypass).” | **Rejected.** SSRF blocks, but unauthenticated initialize and bogus Bearer succeed. Auth bypass is not blocked. |
| CLM-006 | Deployed p50 1,094.0 ms vs Tavily 2,001.1 ms. | **Superseded.** V10: deployed 1,037.8 ms vs Tavily 1,537.4 ms. Same direction, different dataset/settings. |
| CLM-007 | 87% answer support across 100 queries. | **Superseded / Unsupported for V10.** V10 measures retrieval P@5/nDCG/Hit, not claim-level answer support. No V10 answer-support artifact exists. |
| CLM-009 | 425.5 mean tokens vs Tavily 1,486.6. | **Superseded.** V10: local 182.3, deployed 206.2, Tavily 1,378.7. |
| CLM-010 | “All 9 apps execute against synthetic fixtures (18/18), `--mock-offline`.” | **Superseded.** V10 uses the live runner; 9/9 real workflow assertions pass. |
| CLM-018 | “Zero API keys leaked in git commits or log files.” | **Partially verified.** SEC-V9-001 records a live Tavily key in two committed reports; redacted, but it remains in git history until rotation. |

---

## 8. What remains unverified

- Human relevance judgments and inter-rater agreement.
- Repeated-trial variance (one run per query).
- Internal Cloud Run IAM/VPC/edge policy.
- Deployed cross-tenant isolation (blocked by the old Crawl2RAG error).
- GPT-OSS 20B / Mistral NeMo 12B / “GPT-OSS 12B” quality.
- 100k-query and 10k-adversarial dataset targets.
- Claim-level citation correctness under independent human review.
