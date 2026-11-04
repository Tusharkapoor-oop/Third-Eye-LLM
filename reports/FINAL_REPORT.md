# WebLens V10 — Final Report (Sections A–L)

**Date:** 2026-11-05
**Repo:** `Tusharkapoor-oop/Third-Eye-LLM` (branch `main`)
**Session:** `weblens-v10-2026-11-04`
**Live service:** `https://weblens-fgunqcnrla-uc.a.run.app` (revision `weblens-00006-l9h`)
**Canonical package:** `weblens/src/weblens` (mirrored to `src/weblens`)

Status vocabulary: `PASS`, `FAIL`, `PARTIAL`, `BLOCKED`, `NOT RUN`, `UNSUPPORTED`, `UNVERIFIED`, `REJECTED`. A missing result is never counted as a pass.

---

## A. Project understanding

WebLens is a web-intelligence layer for AI agents. Its core value proposition is compact, citable evidence: bounded search across keyless providers, page extraction with character-span citations, a crawl-to-RAG knowledge base, and nine application workflows, all exposed over a real MCP server (stdio or Streamable HTTP).

The product has two surfaces:

1. **`weblens/src/weblens`** — the canonical package, including the MCP server, providers, extraction, research engine, apps, security, and CLI. This is what the Cloud Run service runs.
2. **Legacy root app** (`config.py`, `server.py`, `model_provider.py`, `benchmarks/`) — an older MyWebEngine demo and the existing model-integration surface. It is not the deployed MCP service. This distinction caused a prior deployment-drift problem and is now explicit in `Dockerfile`.

The evaluation compares three independent retrieval systems on the same queries:

- **Local WebLens** — the real MCP server process on loopback, keyless providers only.
- **Deployed WebLens** — the real Cloud Run MCP endpoint.
- **Tavily direct** — the official `/search` API.

Results are never merged. Tavily-backed WebLens results are never counted as independent WebLens results.

---

## B. Original state

At session start:

- The repo was on `main` at `475a6ff`, with the deployed service live at `weblens-00003-l9q`.
- Prior V9 “PASS” claims were suspect: the deployed tool surface did not match the canonical package, the README claimed “all 13 tools” on a public service, and several benchmark numbers were not reproducible from the evidence on disk.
- The V9 benchmark mixed result-bearing degraded responses with transport errors and did not preserve clean provenance.
- `Crawl2RAG` returned a success status while indexing nothing; its `CrawledPage` shape had changed and the app still read removed fields.
- Company research and meeting prep produced hollow or wrong-domain results on live queries.
- The injection detector missed two real instruction-override patterns.
- The security audit harness treated MCP `isError` structured rejections as crashes and mis-read `extract_url` payload fields, producing false SSRF results.
- The deployed `Dockerfile` still started the legacy root `server.py`, so a source redeploy could silently replace the canonical service with a different product.
- No single document reconciled measured claims, rejected claims, security findings, and blocked work.

---

## C. Bottlenecks found

| Bottleneck | Evidence | Impact |
|---|---|---|
| Result-bearing `partial` responses were counted as failures in earlier harnesses | Prior V9 summaries vs raw records | Understated success; mixed transport and quality |
| No provenance separation between systems | V9 raw files | Risk of merging Tavily-backed results into WebLens scores |
| `Crawl2RAG` indexed empty pages but returned success | Live app run before fix | Product lied about success; RAG queries had no evidence |
| Company/market/meeting searches used long natural-language framing | Live results before `clean_query` | Irrelevant providers results, wrong official domains |
| Injection patterns too narrow | Two curated strings bypassed detection | Real prompt-injection miss |
| Audit parsed `isError` text as JSON | SSRF/unknown-tool/missing-arg checks | False FAILs masked real behavior |
| Deployed listener shared one SQLite store with no tenant identity | Cross-tenant probe on revision `00005` | One caller could read another caller's Crawl2RAG probe |
| Public unauthenticated MCP | Deployed audit | Anyone can call the service; no app-level rate limit observed |
| Dataset target unrealistic for one session | 120 curated vs 100k target | Must report `BLOCKED`, not inflate with paraphrases |
| Model access uneven | NVIDIA probes | Only one model reachable; no ranking possible |
| Full root test suite hung | ~93% then >15 min | Cannot claim a complete green suite |

---

## D. Changes made

### Product and retrieval fixes

| Area | Change | Verification |
|---|---|---|
| `search/router.py` | `clean_query` strips explanatory lead-ins and rewrites “differences between A and B” → “A and B” | Targeted tests; live apps |
| `research/engine.py` | Research scoring uses the cleaned query | Research tests |
| `apps/crawl2rag.py` | `CrawledPage.text/tokens`, defensive fallback, `page_failures`, honest `status`/`no_reliable_result` | Nine-app runner, Crawl2RAG tests |
| `apps/company.py` | Per-field fallback queries, official-domain ranking, aggregator demotion | Nine-app runner |
| `apps/meeting.py` | Shorter fallback queries, deduped sources, fallback search | Nine-app runner |
| `security/injection.py` | Added instruction-override and exfiltration patterns (`email|exfiltrate|share`) | 47-test injection/app set |

### Security and deployment fixes

| Area | Change | Verification |
|---|---|---|
| `mcp_server.py` | `build_server(service, profile=None, *, allow_stateful=True)`; stateful tools register only when allowed | Tool-surface probe |
| `cli.py` | `allow_stateful = loopback or bool(token)`; warning on disable | Loopback 13 tools / public 10 tools |
| `Dockerfile` | Starts `python -m weblens.cli serve ... --profile full` instead of legacy `server.py` | Cloud Build + deployed `tools/list` |
| `.gcloudignore` | Keeps source upload small and secret-free | Cloud Build succeeded |
| `run_security_audit_v2.py` | Parse `isError`; `_message_is_error`; accept 400 + JSON-RPC error; GET root; read `ps[].x`; mark absent stateful tool `UNSUPPORTED` | Deployed audit 18/4/1 |

Both package trees were mirrored so import order cannot change behavior.

### Measured effect of remediation

- Nine applications: **9 PASS / 0 PARTIAL / 0 FAIL** after fixes.
- Local security: **38 PASS / 0 FAIL** after fixes.
- Deployed tools: **10 stateless** on the public listener; **13** on loopback.
- Deployed audit: **18 PASS / 4 FAIL / 1 UNSUPPORTED** on revision `00006`.
- Post-redeploy smoke (10 queries): deployed P@5 **0.80**, nDCG@5 **0.932**, p50 **1,211.5 ms**, **266.4** tokens, success **1.0**. Directional only; n=10.

---

## E. Tavily coverage

### E.1 Official demo use cases (5.1–5.8)

All eight were run through real WebLens MCP tools; Tavily `/search` was the baseline.

| ID | Use case | WebLens tool | WebLens coverage | Tavily coverage |
|---|---|---|---:|---:|
| UC-01 | Company research | `company_research` | 0.25 | 0.75 |
| UC-02 | Financial market research | `market_research` | 0.25 | 1.00 |
| UC-03 | Web-powered assistant | `deep_research` | 0.50 | 1.00 |
| UC-04 | Compliance risk screening | `deep_research` | 0.00 | 0.75 |
| UC-05 | Sales meeting prep | `meeting_prep` | 0.50 | 0.75 |
| UC-06 | Supply chain risk | `deep_research` | 0.00 | 0.75 |
| UC-07 | Underwriting research | `deep_research` | 0.00 | 0.75 |
| UC-08 | Data enrichment | `sheets_enrich` | 0.60 | 1.00 |

Aggregate: WebLens **0.263** coverage, **149.1** tokens, **9,102.4 ms**; Tavily **0.844**, **1,278.6** tokens, **332.3 ms**. WebLens had evidence URLs in 4/8 cases; Tavily in 8/8.

**Status: PARTIAL.** All eight cases ran, but this is a retrieval proxy, not an agent-quality comparison. Tavily `/search` returns snippets; its score is a lower bound. Scoring counts output evidence only; query/input echoes are excluded. WebLens returned `no_reliable_result` for compliance, supply chain, and underwriting (0.00 coverage) and `not_available` for market research, and had thin company/assistant/meeting/enrichment evidence.

**Scoring correction:** the first pass serialized the whole payload, so echo fields (`q`, `searched`) counted as evidence and inflated WebLens coverage to 0.700. The harness now excludes query/input keys; the table above is the corrected evidence-only result.

### E.2 Tavily API capabilities exercised

- `/search` — primary baseline, 120 queries + 8 use cases + 10 smoke queries.
- `extract` / `crawl` — not separately benchmarked in V10; WebLens has its own extraction and crawl paths tested in the nine-app run.
- `map`, `/research` — **NOT RUN**; no validated harness in this session. Do not claim parity.

---

## F. Model evaluation

Probe: `weblens-lab/model_eval/probe_model_access.py` (no key values printed).

| Model | Status | Evidence |
|---|---|---|
| `mistralai/mistral-large-4-1t-a52b` (NVIDIA) | **ACCESSIBLE** | HTTP 200, exact JSON, 21.4 s, 41 prompt + 134 completion tokens (116 reasoning) |
| `openai/gpt-oss-20b` (NVIDIA) | **BLOCKED** | Two attempts (60 s, 150 s) returned `ReadTimeout`; no completion |
| `nv-mistralai/mistral-nemo-12b-instruct` | **BLOCKED** | HTTP 404, not entitled for this account |
| “GPT-OSS 12B” | **UNSUPPORTED** | No such model ID in the available catalog; 12B option is Mistral NeMo 12B, which 404'd |

**Conclusion:** a model-vs-model quality ranking is **BLOCKED**. Only one model produced output; ranking from one demo would be fabricated. One real operational finding: Mistral Large 4 spends most of a small completion budget on reasoning tokens, so `max_tokens` must be set above the visible answer length (a 120-token cap returned empty content; 800 returned the answer).

---

## G. Benchmarks

### G.1 V10 three-system benchmark (120 queries, 107 graded)

Dataset: `weblens-lab/datasets/eval_benchmark_suite_v10.json`, 30 categories × 4, 60 dev / 60 held-out, SHA-256 `a42d4004fb91208f1ae18de89e2337f2ccf5e7cb580a3c600a8ec7d8057d6361`.

| Metric | Local | Deployed | Tavily |
|---|---:|---:|---:|
| Graded | 107 | 107 | 107 |
| Success | 0.900 | 0.942 | 1.000 |
| P@1 | 0.617 | 0.636 | 0.757 |
| P@5 | 0.553 | 0.471 | 0.740 |
| MRR | 0.660 | 0.711 | 0.827 |
| nDCG@5 | 0.669 | 0.729 | 0.777 |
| Hit@5 | 0.729 | 0.832 | 0.935 |
| p50 | 837.0 ms | 1,037.8 ms | 1,537.4 ms |
| p95 | 1,497.3 ms | 1,622.2 ms | 2,673.1 ms |
| Tokens | 182.3 | 206.2 | 1,378.7 |
| Credits | 0 | 0 | 120 |

P@5 95% CIs: local `[0.484, 0.624]`, deployed `[0.411, 0.533]`, Tavily `[0.675, 0.804]`.

Paired comparisons (107 pairs):

| Comparison | Mean Δ | 95% CI | W/T/L |
|---|---:|---|---|
| local − Tavily P@5 | −0.187 | [−0.265, −0.108] | 24/34/49 |
| local − Tavily nDCG@5 | −0.108 | [−0.189, −0.027] | 48/19/40 |
| deployed − local P@5 | −0.082 | [−0.142, −0.024] | 25/36/46 |

**Status: PARTIAL.** The measurement is real and reproducible, but the sample is 120, not 100k; 13 items are excluded from grading; the deployed column is the pre-remediation revision.

### G.2 Post-remediation deployed smoke (10 queries)

| Metric | Local | Deployed `00006` | Tavily |
|---|---:|---:|---:|
| P@5 | 0.62 | 0.80 | 0.92 |
| nDCG@5 | 0.867 | 0.932 | 0.908 |
| Hit@5 | 0.90 | 1.00 | 1.00 |
| p50 | 3,522.4 ms | 1,211.5 ms | 2,324.8 ms |
| Tokens | 206.0 | 266.4 | 1,367.4 |
| Success | 1.00 | 1.00 | 1.00 |

**Status: PARTIAL / directional.** n=10 and not the held-out sample; it does not replace the 120-query table.

### G.3 Dataset reality

- 120 curated queries achieved.
- 100k primary, 250k preferred, 500k stress: **BLOCKED**.
- 10k adversarial cases: **BLOCKED**; 9 curated cases exist.
- No paraphrases, placeholders, or synthetic duplicates were used to inflate counts.

---

## H. Performance and cost

- **Latency:** on V10, local WebLens is 1.8× faster than Tavily at p50 (837 vs 1,537 ms) and 1.8× at p95. On the deep-research use cases, WebLens is much slower (9.1 s vs 0.33 s for Tavily search) because it crawls and synthesizes.
- **Tokens:** local returns ~7.5× fewer tokens than Tavily on the search benchmark (182.3 vs 1,378.7), and ~8.6× fewer on the evidence-only use-case measure (149.1 vs 1,278.6). This is the clearest, consistent advantage.
- **Provider credits:** WebLens used 0 Tavily credits when running keyless providers; Tavily used 120 credits for the 120-query run and 8 for the use-case run. WebLens does not make the search free in absolute terms — Cloud Run compute and provider rate limits remain.
- **Cost caveat:** no dollar figure is claimed. Tavily pricing varies by plan and date; Cloud Run cost depends on traffic. The only hard numbers are credits and tokens.
- **Reliability:** local success 0.900, deployed 0.942, Tavily 1.000 on V10. The local failures are result-bearing `partial`/empty outcomes and a small number of transport errors, recorded separately.

---

## I. Tests actually executed

| Suite | Result |
|---|---|
| `pytest` targeted security/extraction/crawler set | **170 passed** in 16.7 s |
| `pytest tests/test_injection_sanitization.py weblens/tests/test_apps.py` | **47 passed** in 21.1 s |
| `pytest weblens/tests/test_mcp.py test_http_auth.py test_apps.py test_config.py` | **PASS** (selected suite completed) |
| Nine applications live runner | **9 PASS / 0 PARTIAL / 0 FAIL** |
| Local security v2 | **38 PASS / 0 FAIL** |
| Deployed security v2 | **18 PASS / 4 FAIL / 1 UNSUPPORTED** |
| Full root `pytest tests` | **INCOMPLETE** — hung after ~93% for >15 min; terminated. A post-termination process check found `tests/test_04_fuzz_and_chaos.py` still running after ~21 min (174 s CPU, 220 MB). Not a pass. |

The full-suite hang is a reliability finding: at least one live/network test can block indefinitely. It is recorded, not hidden. The earlier 248-pass run predates this session's edits.

---

## J. Security

### J.1 Local (real MCP process)

**38 PASS / 0 FAIL / 0 UNVERIFIED.** Verified:

- SSRF blocking for metadata IP, loopback, RFC1918, IPv6 loopback, `file://`, and redirect-to-private.
- A public control URL still extracts, proving the block is not blanket denial.
- Injection detection on the two previously missed strings; benign controls clean.
- Oversize query rejected.
- Unknown tool and missing argument return structured rejection, not a crash.
- Crawl2RAG real crawl → index → query with spans.

### J.2 Deployed (revision `weblens-00006-l9h`)

**18 PASS / 4 FAIL / 0 UNVERIFIED / 1 UNSUPPORTED.**

Open findings:

1. **Unauthenticated MCP `initialize` succeeds** (high). The service is deployed with public `allUsers` invoker.
2. **A bogus `Bearer` token is accepted** (high). No authorization is enforced.
3. **No application-level rate limit observed** in 20 cheap `tools/list` calls (medium). This was not a load test; Cloud Run may absorb abuse at the edge.
4. **No HSTS header** on the app response (low).

Resolved:

- Oversize query now rejected.
- Crawl2RAG crash fixed.
- **Cross-tenant Crawl2RAG leak (high) found on revision `00005`:** a fresh HTTP client queried a unique probe indexed by another client and received it (`probe_visible_in_other_client: true`). Fixed by not registering `crawl2rag_index`, `crawl2rag_query`, and `research_chat` on a public unauthenticated listener. Deployed `tools/list` now returns 10 stateless tools; loopback returns all 13.

**UNSUPPORTED, not PASS:** cross-tenant isolation as a feature. The shared surface was removed, but there is no per-user identity or per-tenant store. If a token is later enabled, all token holders are still one tenant.

**Not claimed:** “fully hardened”, “10/10 remote checks passed”, “zero trust”, or “multi-tenant”. The old README claimed these; the measured audit contradicts them.

Scope: only the user's local process, the user's Cloud Run service, and the user's Tavily account were tested. No third-party targets, no destructive load, no credential values written.

---

## K. Remaining work

### Blocked

1. **100k / 250k / 500k dataset targets** — `BLOCKED` at 120 curated queries.
2. **10k adversarial cases** — `BLOCKED` at 9 curated cases.
3. **Model comparison** — `BLOCKED`; only Mistral Large 4 produced output. GPT-OSS 20B timed out, Mistral NeMo 12B returned 404, “GPT-OSS 12B” does not exist.
4. **Deployed internal configuration** — `UNVERIFIED`; only gcloud-visible settings and observed behavior were inspected. IAM internals, VPC, and edge policy were not.
5. **Local Docker build** — `BLOCKED`; daemon unavailable. Cloud Build succeeded, so the image was verified remotely, not locally.
6. **Full root test suite** — `INCOMPLETE`; hung after ~93%.

### Open work

1. Decide whether to keep the public unauthenticated deployment or require IAM/token auth; document cost and abuse risk either way.
2. Implement per-user identity and per-tenant stores before claiming multi-tenant isolation.
3. Add `--systems` to the V10 runner and A/B the query-normalization change on the 60-query dev split.
4. Isolate the hanging root test with per-test timeouts from a fresh process.
5. Add human relevance grading or a second independent grader; the current rubric is deterministic domain/fact matching.
6. Run repeated trials for variance; current CIs are bootstrap over queries, not repeated runs.
7. Obtain valid entitlements for GPT-OSS 20B and Mistral NeMo 12B before any model ranking.

---

## L. Final status

| Area | Status | Basis |
|---|---|---|
| Real local WebLens MCP measured | **PASS** | 120 queries through the real subprocess |
| Real deployed WebLens MCP measured | **PASS** | 120 queries against Cloud Run |
| Tavily direct measured | **PASS** | 120 queries, 120 credits |
| Provenance separation | **PASS** | Per-record system, no merged results |
| V10 dataset schema | **PASS** | 120 items, unique, 0 duplicates, hash recorded |
| 100k dataset target | **BLOCKED** | Achieved 120 |
| 10k adversarial target | **BLOCKED** | Achieved 9 |
| Nine product workflows | **PASS** | 9/9 live |
| Local security | **PASS** | 38/38 |
| Deployed security hardening | **FAIL** | 18 PASS / 4 FAIL / 1 UNSUPPORTED |
| Cross-tenant isolation | **UNSUPPORTED** | Surface removed; no tenancy |
| Tavily official use-case coverage | **PARTIAL** | 8/8 run; proxy metrics; WebLens trails coverage |
| Model evaluation | **BLOCKED** | Only one model reachable |
| Benchmark quality vs Tavily | **FAIL** (lower) | P@5 0.553 vs 0.740; paired gap negative |
| Performance / token efficiency | **PASS** (faster, fewer tokens) | 1.8× faster; ~7.5× fewer tokens |
| Tests (targeted) | **PASS** | 170 + 47 |
| Tests (full root suite) | **INCOMPLETE** | Hung after ~93% |
| Deployment revision | **PASS** | `weblens-00006-l9h` live, 10 stateless tools |
| Overall project | **PARTIAL** | Real, reproducible, honest; large targets and deployment hardening remain |

**Bottom line:** WebLens is measurably faster and far more token-efficient than Tavily, and its nine workflows run end-to-end. It is not more relevant than Tavily on this dataset, it is not hardened for public multi-tenant use, and the requested dataset and model-comparison scales were not reached. Every number above is traceable to an artifact in `reports/` or `evidence/`; the blocked items are reported as blocked.

---

## Evidence map

| Claim | Artifact |
|---|---|
| V10 three-system metrics | `reports/three-system-comparison-v10/analysis/analysis.json` |
| Raw per-query records | `reports/three-system-comparison-v10/raw/run_full_v10_120.jsonl` |
| Post-deploy smoke | `reports/three-system-comparison-v10/analysis-post-deploy-smoke/` |
| Tavily use cases | `reports/tavily-use-cases-v10/results.json` |
| Nine apps | `reports/nine_applications_verification.json` |
| Local security | `reports/local-security/local_security_results_v2.json` |
| Deployed security | `reports/deployed-security/deployed_security_results_v2.json` |
| Dataset validation | `reports/three-system-comparison-v10/dataset_validation_v10.json` |
| Claims / rejected claims | `evidence/CLAIM_LEDGER.md` |
| Security findings | `evidence/SECURITY-FINDINGS.md` |
| Experiment registry | `evidence/EXPERIMENT-INDEX.md` |
| Loop state | `evidence/loop-state-v10.json` |
