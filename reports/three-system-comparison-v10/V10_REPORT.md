# WebLens V10 — Three-System Evaluation Report

**Experiment:** `full_v10_120`
**Dataset:** `eval_benchmark_suite_v10.json` / `v10.0.0`
**SHA-256:** `a42d4004fb91208f1ae18de89e2337f2ccf5e7cb580a3c600a8ec7d8057d6361`
**Raw records:** `reports/three-system-comparison-v10/raw/run_full_v10_120.jsonl` (120 queries × 3 systems = 360 records)
**Analysis:** `reports/three-system-comparison-v10/analysis/analysis.json`, `analysis.md`
**Measurement window:** 2026-11-02
**Report status:** PARTIAL — the measurement is real and reproducible, but the dataset-size targets are not met and the deployed system was measured on an older revision.

---

## 1. What was measured

Three systems, independently, using the same 120 queries:

| System key | What it is | How it was reached |
|---|---|---|
| `local_weblens` | The real WebLens **MCP server process** | `python -m weblens.cli serve --http --profile full` subprocess, MCP HTTP client |
| `deployed_weblens` | The real Cloud Run WebLens service | `https://weblens-16131012091.us-central1.run.app/mcp` (same revision as `weblens-fgunqcnrla-uc.a.run.app`) |
| `tavily_direct` | Tavily's hosted search API | `https://api.tavily.com/search`, `search_depth=basic`, 5 results |

No result was merged across systems. Every record carries its own endpoint, provider metadata, response hash, latency, token count, and error field. Provenance checks passed: no Tavily-backed WebLens call is counted as an independent WebLens result.

### Why this report says PARTIAL

- Target dataset sizes were 100k (primary), 250k (preferred), 500k (stress). **Achieved: 120 curated queries.** The 100k target is `BLOCKED`, not passed.
- The adversarial target was 10k cases. **Achieved: 9 curated cases** in the separate `adversarial_suite.json`. `BLOCKED`.
- The deployed revision measured here (`weblens-00003-l9q`) predates the local query-normalization, Crawl2RAG, meeting-prep, and company-research fixes. It is a distinct, older build.
- The local V10 run also predates the query-normalization and app fixes made after measurement. Code-version drift is disclosed below; the numbers are not retroactively attributed to the newer code.
- 13 of 120 queries are intentionally unanswerable/ambiguous/contradictory and are excluded from graded retrieval metrics (107 graded). They are still counted in success-rate and latency.

---

## 2. Metric definitions

- **Success rate** — fraction of queries whose tool call returned a result-bearing response (`ok` or `partial`). `empty`/`error` count as failure. A degraded `partial` response is a successful call, not a crash.
- **P@1, P@3, P@5** — precision of the top-k returned URLs under the V10 deterministic relevance rubric.
- **MRR** — reciprocal rank of the first relevant URL.
- **nDCG@5** — graded relevance at 5, domain match = 2, fact match = 1, decayed by rank.
- **Hit@5** — at least one relevant URL in the top 5.
- **Domain diversity / duplicate rate** — distinct registrable domains and duplicate-URL share in the top 5.
- **Tokens** — returned-content tokens, normalized with `tiktoken` `cl100k_base`, so WebLens compact schemas and Tavily JSON are counted on the same tokenizer.
- **Credits** — Tavily credits reported by the API; WebLens search providers used here (DuckDuckGo, MWMbl, Wikipedia) have no per-query API credit.
- **p50/p95 latency** — end-to-end tool-call wall time, including provider and transport.

Relevance is graded deterministically from each dataset item's declared expected domains and expected facts. It is **not** human grading, and domain matching can over-credit a page that mentions the right domain but not the right fact. This is a metric limitation, not a claim of human-level relevance judgment.

---

## 3. Headline results

| Metric | Local WebLens | Deployed WebLens | Tavily |
|---|---:|---:|---:|
| Queries | 120 | 120 | 120 |
| Graded | 107 | 107 | 107 |
| Success rate | 0.900 | 0.942 | 1.000 |
| Status mix | 37 ok / 71 partial / 12 empty | 84 ok / 29 partial / 7 empty | 120 ok |
| p50 ms | 837.0 | 1037.8 | 1537.4 |
| p95 ms | 1497.3 | 1622.2 | 2673.1 |
| P@1 | 0.617 | 0.636 | 0.757 |
| P@3 | 0.584 | 0.522 | 0.790 |
| P@5 | 0.553 | 0.471 | 0.740 |
| MRR | 0.660 | 0.711 | 0.827 |
| nDCG@5 | 0.669 | 0.729 | 0.777 |
| Hit@5 | 0.729 | 0.832 | 0.935 |
| Mean tokens | 182.3 | 206.2 | 1378.7 |
| Credits | 0 | 0 | 120 |

95% bootstrap CIs for P@5:

- Local: `[0.484, 0.624]`
- Deployed: `[0.411, 0.533]`
- Tavily: `[0.675, 0.804]`

### Honest reading

- **WebLens is faster and dramatically more token-efficient**, but **Tavily is more relevant and more reliable** on this dataset. Do not claim WebLens beats Tavily.
- **Tavily P@5 is 0.187 higher than local** (paired mean delta `-0.187`, 95% CI `[-0.265, -0.108]`, 24 wins / 34 ties / 49 losses). The CI excludes zero.
- **Deployed is 0.082 P@5 below local** (paired delta `-0.082`, CI `[-0.142, -0.024]`), while having a higher Hit@5 and nDCG@5. The deployed build is older and returns more results that are relevant somewhere in the top 5 but ranked worse.
- WebLens returns roughly **7.5× fewer tokens** than Tavily (182 vs 1379, 206 vs 1379). That is a real efficiency advantage, not a quality advantage.

### Paired comparisons

| Comparison | Pairs | Mean delta | 95% CI | W/T/L |
|---|---:|---:|---|---|
| local − Tavily P@5 | 107 | −0.187 | [−0.265, −0.108] | 24/34/49 |
| local − Tavily nDCG@5 | 107 | −0.108 | [−0.189, −0.027] | 48/19/40 |
| deployed − local P@5 | 107 | −0.082 | [−0.142, −0.024] | 25/36/46 |
| local − deployed P@5 | 107 | +0.082 | [+0.024, +0.142] | 46/36/25 |

---

## 4. Where the gaps are

Full per-category table: `analysis/analysis.md`. The largest, consistent gaps are:

- **Crawl2RAG category** — local P@5 `0.00` vs Tavily `0.80`. Root cause was a product bug: `CrawledPage` did not carry `text`/`tokens`, so the benchmark's Crawl2RAG path indexed nothing. This was fixed after the V10 run (`weblens/src/weblens/apps/crawl2rag.py`). The V10 number is the pre-fix baseline.
- **Multilingual queries** — local P@5 `0.25` vs Tavily `0.90`. Provider/query-language handling is the weak point; no multilingual rewriting exists.
- **Healthcare, stock/portfolio, market research** — Tavily's index is stronger on general factual and finance queries; WebLens' DDG/MWMbl/Wikipedia mix is thinner.
- **Conversational research** — local `0.00` vs Tavily `0.30`; the V10 search path does not resolve conversational context the way the app layer does.
- **Adversarial / insufficient-evidence categories** — graded subsets are tiny and the category means are not stable. Treat them as directional only. Local's `1.0` on `adversarial_injection` means its returned pages matched the expected domain/fact rubric, **not** that it resisted injection better; injection resistance is evaluated in the security campaign, not here.

### Latency/token trade-off

WebLens is 1.8× faster at p50 than Tavily (`837 ms` vs `1537 ms`) and 1.8× faster at p95 (`1497 ms` vs `2673 ms`) while returning 7.5× fewer tokens. If the product goal is a compact, citable evidence packet for an agent, that is a meaningful advantage. If the goal is maximum recall on broad factual queries, Tavily wins on this dataset.

---

## 5. Security campaign (separate from the benchmark)

### Local — real MCP process

`weblens-lab/security_lab/run_security_audit_v2.py --skip-deployed`
Result file: `reports/local-security/local_security_results_v2.json`

- **38 PASS / 0 FAIL / 0 UNVERIFIED** after fixes.
- Covered: literal-IP and hostname SSRF policy, redirect/metadata targets, `file://`, formula injection, prompt-injection patterns, real `extract_url` / `crawl_site` / `crawl2rag_index` calls, empty and oversize queries, unknown tool, secret-leak scan of responses.
- Fixes that moved real failures to passes:
  - `security/injection.py`: detected “ignore all instructions”, “previous directions”, “system override”, and exfiltration verbs (`disclose`, `output`, `email`, …).
  - `apps/crawl2rag.py`: no longer returns `status: ok` when every page was blocked; now returns `no_reliable_result` with `page_failures`.
  - Query length is rejected above 2000 chars in `WebLens.search`.
- A public `https://example.com/` extraction control passed, proving SSRF checks are not blocking everything.

### Deployed — measured before the current redeploy

`run_security_audit_v2.py --skip-local`
Result file: `reports/deployed-security/deployed_security_results_v2.json`

- **17 PASS / 5 FAIL / 1 UNVERIFIED** after correcting harness false positives.
- Real findings:
  1. **Unauthenticated MCP initialize succeeds** (high). The service is deployed with public `allUsers` invoker.
  2. **A bogus `Bearer` token is also accepted** (high). Same root cause: no authorization is enforced.
  3. **No application-level rate limit observed** in 20 cheap `tools/list` calls (medium). Cloud Run may still absorb abuse at the edge, but no 429 was visible.
  4. **No HSTS header** on the service root (low). Cloud Run may set transport policy at the edge; the app does not.
  5. **Oversize query is accepted** by the older deployed build (low). The current local build rejects >2000 chars.
- **UNVERIFIED:** cross-tenant Crawl2RAG isolation. The deployed old build returns `Error executing tool crawl2rag_index`, so the test could not create state to compare.
- **Correction to the first v2 run:** private-URL extraction was reported as FAIL. Raw inspection shows the deployed server returns a structured `isError` with `non-public destination` and no page content. **SSRF blocking works**; the first result was a harness parsing bug, now fixed. The same applies to unknown-tool and missing-argument cases (MCP `isError` is a valid structured rejection, not a crash).

Authorization/scope: only the user's local process, the user's Cloud Run service, and the user's Tavily key were tested. No third-party targets, no destructive load, no credential values written to reports.

---

## 6. Product workflows — nine applications

Evidence: `reports/nine_applications_verification.json`

**9 PASS / 0 PARTIAL / 0 FAIL**, each with assertions on real outputs:

1. Deep research — findings with URL + exact span.
2. Company researcher — fields populated with citations, wrong-domain fallbacks rejected.
3. Chat answer engine — citations, follow-up resolves prior topic.
4. Crawl2RAG — crawl → index → query returns passages with spans.
5. Market researcher — sourced metrics from disclosures + disclaimer.
6. Sheets enricher — rows returned, formula injection defanged, verified values sourced.
7. Meeting prep — attendee profile, sources, company context, privacy notice.
8. Tutorial 101 — all 9 steps executed and passed.
9. Persistent research chat — messages persisted, session reopened, topic and sources survive export.

The Crawl2RAG, meeting-prep, and company-research workflows were failing or hollow before this session and were fixed; the nine-app runner now requires real crawl/index/query and real persistence rather than status strings.

---

## 7. Model access — real probe, not a ranking

Probe: `weblens-lab/model_eval/probe_model_access.py` (no key values printed).

| Model | Result | Evidence |
|---|---|---|
| `mistralai/mistral-large-4-1t-a52b` (Mistral Large 4, NVIDIA) | **ACCESSIBLE** | HTTP 200, exact JSON `{"city":"Paris","country":"France","confidence":0.9}`, 21.4 s, 41 prompt + 134 completion tokens, of which 116 were reasoning tokens |
| `openai/gpt-oss-20b` (GPT-OSS 20B, NVIDIA) | **BLOCKED** | Two attempts (60 s and 150 s) returned no response (`ReadTimeout`). Endpoint accepted the request; no completion arrived. |
| `nv-mistralai/mistral-nemo-12b-instruct` (12B) | **BLOCKED** | HTTP 404: function not found for this account. Not entitled. |
| GPT-OSS 12B | **UNSUPPORTED / NOT RUN** | No such model ID is present in the available NVIDIA catalog; “12B” corresponds to Mistral NeMo 12B, which returned 404. |

**Conclusion:** only one of the requested models was reachable. A model-vs-model quality comparison is **BLOCKED**; reporting a ranking would be fabricated. The one real observation worth carrying forward is operational: Mistral Large 4 spends most of a small completion budget on reasoning tokens, so callers must budget `max_tokens` above the visible answer length (a 120-token cap returned empty content; 800 returned the answer).

---

## 8. Changes made after the V10 measurement

These are **not** reflected in the V10 numbers above. They are separately verified by tests and the nine-app run.

| File | Change | Why |
|---|---|---|
| `weblens/src/weblens/search/router.py` | `clean_query` strips explanatory lead-ins and rewrites “differences between A and B” → “A and B” | Provider queries were polluted by natural-language framing |
| `weblens/src/weblens/research/engine.py` | Research scoring uses the cleaned query | Consistency with search |
| `weblens/src/weblens/apps/crawl2rag.py` | `CrawledPage.text/tokens`, defensive text fallback, `page_failures`, honest `no_reliable_result`/`partial` status | Crawl2RAG indexed nothing and lied about success |
| `weblens/src/weblens/apps/company.py` | Per-field fallback queries, official-domain ranking, aggregator demotion | Generic/incorrect company fields |
| `weblens/src/weblens/apps/meeting.py` | Shorter fallback queries, deduped sources | Empty meeting briefs |
| `weblens/src/weblens/security/injection.py` | Broader injection/exfiltration patterns | Two real prompt-injection misses |
| `weblens-lab/security_lab/run_security_audit_v2.py` | Parse MCP `isError` before JSON; accept 400 + JSON-RPC error; GET root; read `ps[].x`; `_message_is_error` | Removed false positives that masked real results |
| `Dockerfile` | CMD runs `python -m weblens.cli serve ... --profile full` instead of the legacy root `server.py` | The deployed service is the `weblens` package; the root app is a different, older product |
| `.gcloudignore` | Excludes reports/evidence/tests/labs from source upload | Smaller, secret-free Cloud Build upload |

Both `weblens/src/weblens/**` and the editable-install `src/weblens/**` were kept identical so import order cannot change behavior.

---

## 9. Tests actually executed

| Suite | Result | Notes |
|---|---|---|
| `pytest tests/test_injection_sanitization.py tests/test_03_security_boundaries.py tests/test_security.py tests/test_ssrf_penetration.py tests/test_crawler.py tests/test_crawler_traps.py tests/test_extract.py` | **170 passed** in 16.7 s | Security/extraction/crawler regression set |
| `pytest tests/test_injection_sanitization.py weblens/tests/test_apps.py` | **47 passed** in 21.1 s | Includes Crawl2RAG lifecycle |
| Full `pytest tests` | **INCOMPLETE** | The full run progressed past ~93% then hung on a remaining test for >15 min and was terminated. It is not reported as a pass. Earlier in the session the same suite completed 248 passed; that result predates these edits. |
| Nine applications runner | **9 PASS / 0 FAIL** | `reports/nine_applications_verification.json` |
| Local security v2 | **38 PASS** | `reports/local-security/local_security_results_v2.json` |
| Deployed security v2 | **17 PASS / 5 FAIL / 1 UNVERIFIED** | Pre-redeploy revision |

The full-suite hang is itself a reliability finding: at least one live/network test can block indefinitely instead of timing out. It is recorded, not hidden.

---

## 10. Limitations and blocked work

1. **100k / 250k / 500k datasets** — `BLOCKED`. 120 curated queries were produced with 30 categories × 4, 60 dev / 60 held-out, unique IDs, 0 duplicates. Inflating with paraphrases or placeholders would have made the number meaningless.
2. **10k adversarial cases** — `BLOCKED`. 9 curated cases exist; broad adversarial generation needs a separate labeled corpus.
3. **Deployed internal configuration** — `UNVERIFIED`. Client-side gcloud visibility and observed behavior only; IAM internals, VPC, and edge policy are not inspected.
4. **Model comparison** — `BLOCKED` for GPT-OSS 20B, Mistral NeMo 12B, and GPT-OSS 12B. Only Mistral Large 4 was reachable.
5. **Human relevance grading** — not performed. Deterministic domain/fact rubric only.
6. **Repeated trials / variance** — one run per query. No confidence interval over repeated runs, only bootstrap over queries.
7. **Code-version drift** — V10 numbers are the pre-fix baseline; the post-fix local system was not re-run across all 120 queries in this report.
8. **Deployed revision** — measured pre-redeploy. A post-redeploy smoke benchmark is recorded separately if the redeploy succeeded; it does not retroactively change the V10 table.

---

## 11. Bottom line

WebLens V10 is a **real, reproducible three-system measurement**, not a claim of victory:

- It is **faster** and **far more token-efficient** than Tavily.
- It is **less relevant and less reliable** than Tavily on this 120-query dataset; the paired P@5 gap is statistically clear.
- Security on the local system is strong after fixes (38/38). The deployed service has real exposure (public unauthenticated MCP, no visible rate limit, no HSTS) and an older, broken Crawl2RAG tool.
- Nine product workflows pass end-to-end with evidence.
- Dataset-size and multi-model targets are **not met** and are reported as `BLOCKED`, not passed.
