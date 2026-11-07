# MASTER VERIFICATION REPORT — WebLens / webintel engine

**Deliverable:** `reports/MASTER-VERIFICATION-REPORT-2026-11-05.md`
**Report revision:** 2026-11-06 (final, post-remediation)
**Repository:** `C:\Users\ACER\Downloads\Broswer for ai agnets`
**Branch / commit:** `main` @ `4e0885d` (working tree dirty — all changes in §10 are uncommitted)
**Environment:** Windows 11, Python 3.13.15, pytest 9.1.1, pytest-timeout (thread method), `--timeout=60` from `pyproject.toml`
**Machine-readable summary:** §12 below and `reports/master_verification_summary_2026-11-06.json`

Every number in this report is tied to an artifact on disk. Status vocabulary is fixed:
`PASS` / `FAIL` / `PARTIAL` / `BLOCKED` / `UNVERIFIED`. Nothing is rounded up, and no failing gate is reported as passing.

---

## 1. Executive summary and acceptance verdict

**Verdict: PASS WITH LIMITATIONS.**

The engine is releasable for local / private-network MCP use. The full test suite is green for the first time in this audit — **350 passed, 0 failed, 0 errors, exit code 0** (`reports/full_suite_final.log`) — after fixing the causes of three separate classes of failure rather than relaxing any gate: an interpreter teardown hang, a per-request TLS-context construction cost, and test fixtures that stubbed the wrong layer (one of which reached a live Gemini endpoint and exceeded the suite's own 60 s timeout).

What is *not* claimed:

- The 5-case quality arena does **not** reliably clear its own ≥90 target. Three runs of the same code scored 90.8 (pass), 81.6 (fail), 87.0 (fail). This report records the gate as **FAIL** with a variance explanation (§6.3) — the last run is the one attached as current evidence.
- Tavily parity was **not re-measured in this cycle** (budget cap 0, 14.0 of 50.0 credits remain, by instruction). The parity numbers in §6.2 are from the earlier `stage7-20261028-a4a64151` campaign and are cited as prior-cycle evidence.
- RAG retrieval, deep-research sub-question coverage, and citation-integrity batteries remain **STRUCTURAL / UNSUPPORTED** (GAP-LEDGER F8, F9, F10) — no compatible raw artifacts exist for them.
- A live Tavily key committed in `1c11ac3` remains recoverable from git history until the key is rotated (SEC-V9-001, High).

### Headline results

| Gate | Result | Evidence |
|---|---|---|
| Full test suite | **PASS** — 350 passed, exit 0, 577.85 s | `reports/full_suite_final.log` |
| Security red-team (59 vectors) | **PASS** — 59/59, 0 vulnerabilities | `reports/redteam_after_sslfix.log` |
| Static analysis (bandit, 5 touched modules) | **PASS** — High 0, Medium 0, Low 18 (baseline-equal) | §8.2 |
| Concurrency latency (15 parallel extracts) | **PASS** — 5.83 s → 0.13 s | `reports/perf_ssl_context_after.txt` |
| Suite wall clock | **PASS** — 12:57 → 9:37 | `reports/full_suite_run1_1fail.log` vs final |
| Quality arena ≥ 90 | **FAIL** — 87.0 latest run (81.6 / 90.8 / 87.0 across three) | `reports/arena_local_2026-11-06.log` |
| Tavily head-to-head, this cycle | **BLOCKED** — budget cap 0 | §6.3 |
| RAG / deep-research / citation batteries | **UNSUPPORTED** — structural | `evidence/GAP-LEDGER.md` F8–F10 |

---

## 2. Scope, environment, and method

**Systems under test**

- `weblens/` (packaged library + MCP server, 13 tools locally) and the root-level engine modules (`server.py`, `security.py`, `search_pipeline.py`, `extractor.py`, `event_store.py`, `research_engine.py`, `crawl_engine.py`).
- `src/engine/` (the "Engine A" local search/extract stack used by the arena).
- `tests/` — 37 files, 350 collected tests.

**Method**

- Evidence-first: every claim below names a file under `reports/` or `evidence/`.
- Root cause over symptom: each of the eight fixes in §10 changes product or fixture behaviour; no assertion was weakened, no test skipped, no `--timeout` value raised, no suppression added.
- Honest status: intermediate failing/timing-out runs are preserved next to the final green run (`reports/full_suite_run1_1fail.log`, `reports/full_suite_run2_timeout.log`).
- Subagent limitation, restated: the 30 "workstreams" were executed as sequential role passes by one agent, not by 30 parallel subagents (recorded in `reports/domination/domination_summary.json` → `workstreams.execution_mode = "sequential_role_based"`).

---

## 3. Workstream evidence register (30 workstreams)

Each workstream has a standalone report with its own measured artifacts. Verdicts as recorded in `reports/domination/domination_summary.json`.

| # | Workstream | Verdict | Report |
|---|---|---|---|
| 01 | Architecture audit | PASS | `reports/domination/agent01_architecture_audit.md` |
| 02 | Search relevance | PASS | `reports/domination/agent02_search_relevance.md` |
| 03 | Search performance | PASS | `reports/domination/agent03_search_performance.md` |
| 04 | Retrieval & reranking | PASS | `reports/domination/agent04_retrieval_reranking.md` |
| 05 | Extraction accuracy | PASS | `reports/domination/agent05_extraction_accuracy.md` |
| 06 | Extraction performance | PASS | `reports/domination/agent06_extraction_performance.md` |
| 07 | Crawl engine | PASS | `reports/domination/agent07_crawl_engine.md` |
| 08 | Site mapping | PASS | `reports/domination/agent08_site_mapping.md` |
| 09 | Crawl scalability | PASS | `reports/domination/agent09_crawl_scalability.md` |
| 10 | Deep-research quality | PASS | `reports/domination/agent10_deep_research_quality.md` |
| 11 | Deep-research efficiency | PASS | `reports/domination/agent11_deep_research_efficiency.md` |
| 12 | Citation verification | PASS | `reports/domination/agent12_citation_verification.md` |
| 13 | Hallucination & abstention | PASS | `reports/domination/agent13_hallucination_abstention.md` |
| 14 | Prompt injection | PASS | `reports/domination/agent14_prompt_injection.md` |
| 15 | GPT-OSS 12B provider | NOTED (no verdict) | `reports/domination/agent15_gpt_oss_12b.md` |
| 16 | GPT-OSS 20B provider | NOTED (no verdict) | `reports/domination/agent16_gpt_oss_20b.md` |
| 17 | Mistral Large provider | PASS | `reports/domination/agent17_mistral_large.md` |
| 18 | Model orchestration | PASS | `reports/domination/agent18_model_orchestration.md` |
| 19 | Tavily search parity | PASS | `reports/domination/agent19_tavily_search.md` |
| 20 | Tavily extract parity | PASS | `reports/domination/agent20_tavily_extract.md` |
| 21 | Tavily crawl/map parity | PASS | `reports/domination/agent21_tavily_crawl_map.md` |
| 22 | Tavily deep-research parity | PASS | `reports/domination/agent22_tavily_deep_research.md` |
| 23 | Tavily applications parity | PASS | `reports/domination/agent23_tavily_applications.md` |
| 24 | MCP / API correctness | PASS | `reports/domination/agent24_mcp_api_correctness.md` |
| 25 | Security architecture | PASS | `reports/domination/agent25_security_architecture.md` |
| 26 | Penetration testing | PASS | `reports/domination/agent26_penetration_testing.md` |
| 27 | Performance & reliability | PASS | `reports/domination/agent27_performance_reliability.md` |
| 28 | Test infrastructure | PASS WITH LIMITATIONS | `reports/domination/agent28_test_infrastructure.md` |
| 29 | Evidence reproducibility | PASS | `reports/domination/agent29_evidence_reproducibility.md` |
| 30 | Master synthesis | PASS WITH LIMITATIONS | `reports/domination/master_domination_report.md` |

Workstream 28's "PASS WITH LIMITATIONS" was the correct verdict at the time: the suite did not reach a clean exit. After the §10 fixes, that limitation is discharged by the 350/350 green run; the report itself is left unedited so the historical record stays intact.

---

## 4. Test-suite evidence (before → after)

| File | Before (`reports/test_fresh_full_2026-11-05.log`) | After (`reports/full_suite_final.log`) |
|---|---|---|
| `test_04_fuzz_and_chaos.py` | EXIT=1, 281.31 s, hung after summary | PASS, exit 0 (`reports/repro_test04_fixed.log`, 81.98 s) |
| `test_06_performance_stress.py` | EXIT=1, gate breached at 14.31 s, hung at exit | PASS, 3 tests, 10.61 s, exit 0 (`reports/repro_test06_fixed3.log`) |
| `test_apps.py` | EXIT=2 (collection error) | 12 passed |
| `test_adversarial_grounding.py` | EXIT=2 (collection error) | 13 passed (25 passed in 6.74 s for the pair — `reports/repro_apps_fixed.log`) |
| `test_v14_crawl_and_research_lifecycle.py` | passed, but `test_research_job_lifecycle_and_document_export` made a live Gemini call | 4 passed in 11.38 s, offline (`reports/repro_v14_crawl2.log`) |
| Whole suite | 33 files exit 0, 2 exit 1, 2 exit 2 | **350 passed, 0 failed, EXIT=0, 577.85 s** |

Intermediate runs, kept on purpose:

- `reports/full_suite_run1_1fail.log` — 349 passed, 1 failed (`test_apps.py::test_persistent_research_chat`, a fixture mocking one layer too low; fixed in §10.8), 777.10 s, exit 1.
- `reports/full_suite_run2_timeout.log` — timeout in the `test_04` autouse fixture teardown at test 21; not reproducible in 3/3 targeted reruns (`reports/repro_t03_t04_stab1.log`, `stab2.log`, `repro_t03_t04b.log` — 17 passed each, exit 0). Shutdown is now bounded (§10.1), so a stuck close can no longer hang the run.

Suite wall clock improved 12:57 → 9:37 (−25.8%) across the same 350 tests on the same machine, a direct consequence of the shared TLS context (§5).

---

## 5. Performance: measured before/after

### 5.1 TLS context construction (root cause of the extraction latency floor)

`security.safe_fetch_url()` built `ssl.create_default_context(cafile=certifi.where())` once **per request**. That call costs ~0.38 s and blocks the event loop, so 15 concurrent extracts serialised onto it.

| Measurement | Before | After | Change | Artifact |
|---|---|---|---|---|
| `ssl.create_default_context` cost | 0.380 s each; 15× = 5.745 s | built once at import | 15× removed | `reports/perf_ssl_context_before.txt` |
| 15 concurrent `extract_url` (mocked transport, batch 1) | 5.827 s | 0.132 s | **44× faster (−97.7%)** | before / after files |
| 15 concurrent `extract_url` (batch 2) | 5.424 s | 0.079 s | **68× faster (−98.5%)** | before / after files |
| DNS resolution (`getaddrinfo`, 15×) | 0.018 s | unchanged | not the bottleneck | probe log |

Implementation: `security.shared_ssl_context()` returns one module-level context (threading-locked creation, `verify_mode=CERT_REQUIRED`, `set_alpn_protocols(["http/1.1"])`), passed as `verify=` at all three `httpx.AsyncClient` sites (`security.py`, and both clients in `search_pipeline.py`). Verification mode was **not** relaxed.

### 5.2 Suite-level effects

| Signal | Before | After |
|---|---|---|
| `test_06` performance gate (`<5 s` concurrent workload) | FAIL at 14.31 s | PASS, file total 10.61 s |
| `test_04` fuzz module | 281.31 s + exit hang | 81.98 s, exit 0 |
| Full suite | did not exit cleanly | 577.85 s, exit 0 |

### 5.3 Not claimed

No p50/p95 latency improvement is claimed for live web search in this cycle — the shared context removes a fixed per-call cost, and the only current end-to-end latency evidence is the arena's per-case `latency_s` (§6.3), which is dominated by live provider response times, not by TLS setup.

---

## 6. Tavily parity and capability matrix

### 6.1 Capability matrix

| Capability | WebLens | Tavily | Status / note |
|---|---|---|---|
| Web search (keyless) | Yes (multi-provider: SearXNG, DuckDuckGo, Brave, Startpage, Yahoo) | Yes (API key) | WebLens is keyless-first; Tavily needs a paid key |
| Web search (Tavily-backed) | Yes (opt-in provider) | Yes | WebLens-Tavily is an optimisation layer, not an independent engine |
| Extract | Yes, with verbatim `[start,end]` char spans | Yes (snippets) | Span anchoring is the differentiation |
| Crawl | Yes (`crawl_website`, link graph) | Yes | Comparable surface |
| Map | Yes (`web_map`) | Yes | Comparable surface |
| Deep research | Yes (`deep_research`, dossier + bibliography) | Yes | Different scoring profile, see below |
| Browser rendering | Yes (Playwright tier-2) | No | WebLens-only |
| MCP server | Yes (13 tools local, 10 stateless deployed) | No | WebLens-only |
| Document export | Yes (DOCX/PDF/XLSX/MD, validated) | No | WebLens-only |
| Token budget control | Yes (`max_tokens` envelopes) | Partial | Weblens-only in this stack |

### 6.2 Prior-cycle measured comparison (`stage7`, 108-row dataset, 81 dev / 27 test)

Source: `reports/tavily-comparison/QUALITY-RESULTS.json`, `PERFORMANCE-RESULTS.json`, `COST-AND-TOKEN-RESULTS.json`.

| Metric (dev split, n=53 answerable) | WebLens keyless | Tavily direct | Winner |
|---|---|---|---|
| Precision@5 | 0.1686 | 0.2571 | Tavily |
| Precision@5 (WebLens + Tavily hybrid) | 0.2429 | 0.2571 | comparable |
| Support rate | 0.9623 (Tavily) vs keyless (lower) | — | Tavily on strict support |
| Search latency p50 | 763 ms | 1545 ms | WebLens (2× faster) |
| Search payload tokens (mean) | 577 | 1023 | WebLens (−44%) |

Declared caveats from that campaign (verbatim in the artifact): precision uses strict labelled-domain membership, not human relevance; recall@5/10 is **not estimable** because no exhaustive relevant-URL set exists; nDCG is binary rather than graded.

The widely-quoted 145.36 vs 17.66 "facts per 1,000 tokens" (8.23×) and the 93.0 vs 77.0 arena score come from rubric-judged arena runs, **not** from an independent human panel. They are labelled local-only and are not used as a parity gate here.

### 6.3 Fresh arena attempt, this cycle — gate not met

`BUDGET_CAP=0 ARENA_TRIALS=3 python quality_arena.py` → `reports/arena_local_2026-11-06.log`

- Engine A average **87.0** against a **≥ 90.0** target → **FAIL**, `ARENA_EXIT=1`.
- Engine B (Tavily) **BLOCKED** by the budget cap; only 14.0 of 50.0 credits remain and spending them without a fresh request is out of scope.
- Engine C (Gemini grounding) returned HTTP 429 on all three flash models during the run — recorded in the log, not hidden.

Same-code variance across three runs: **90.8** (`reports/arena_a_quiet2_2026-11-05.log`), **81.6** (`reports/arena_full_budget_2026-11-05.json`), **87.0** (`reports/arena_local_2026-11-06.log`), mean **86.5**. The gate is therefore unstable at n=5 cases; the honest verdict is FAIL for the gate, with variance — not a silent pass.

---

## 7. Hallucination and citation integrity

Evidence base: `evidence/GAP-LEDGER.md` (quality loop 2026-11-02), `reports/CITATION_INTEGRITY_REPORT.md`, `reports/FACTUAL_RELIABILITY_REPORT.md`, `reports/domination/agent12_*`, `agent13_*`.

| Check | Result | Status |
|---|---|---|
| Citation span precision (verbatim spans re-checked against source text) | 11/11 | PASS |
| Abstention on unanswerable prompts | 10/10 | PASS |
| Trap-question abstention (F4) | 4/10 | **OPEN** — 6 false-confidence answers |
| Unsupported-claim rate (F3) | No answer artifact | **STRUCTURAL** |
| Citation fidelity + SHA-256 integrity battery (F10) | Not executed | **STRUCTURAL** |
| Search hit in top-5 (F1) | 88/90 | OPEN (2 misses) |
| Supported answer (F2) | 51/90 corrected rerun | OPEN — no causal isolation of the regression |
| Evidence ledger chain | 46 blocks, head `191f1345…`, chain valid | PASS |

The behaviour that matters for agents is implemented and tested: when evidence is absent the pipeline emits `no_reliable_result` with explicit gap codes rather than synthesising an answer (covered by the abstention tests and by the research engine's evidence guard). Trap abstention is the honest weak spot: 6 of 10 adversarial prompts extracted a confident answer.

---

## 8. Security and resilience

### 8.1 Red-team (post-fix)

`python scripts/run_security_redteam.py` → `reports/redteam_after_sslfix.log`

- 59 attack vectors executed, **59 passed, 0 vulnerabilities**.
- Coverage: SSRF (RFC1918, link-local/metadata, IPv6 ULA, DNS rebinding via connection pinning), prompt injection (invisible Unicode, instruction-override, HTML-comment smuggling, canary exfiltration), path traversal, Windows device names, CRLF header injection, oversized payloads.
- SSRF penetration suite: **100/100 blocked** (prior cycle, `reports/ssrf_penetration`).

### 8.2 Static analysis

`bandit -r security.py search_pipeline.py server.py event_store.py extractor.py` → **High 0, Medium 0, Low 18** — identical to the pre-fix baseline; the SSL change introduced no new findings.

### 8.3 Residual risks

| ID | Severity | Status |
|---|---|---|
| SEC-V9-001 — live Tavily API key committed in `1c11ac3` (redacted in working tree, still in history) | High | **OPEN** — requires key rotation by the owner; code cannot revoke it |
| Cloud Run revision `weblens-00008-t5p` public unauthenticated ingress | High | **OPEN** (deployment config, outside this audit's change scope) |
| No HSTS header | Medium | **OPEN** (deployment config) |
| Container runs as root | Low | **OPEN** |

Local/private deployments are unaffected by the last three; they block public exposure only.

---

## 9. MCP and client compatibility

| Check | Result | Status |
|---|---|---|
| MCP protocol conformance (JSON-RPC 2024-11-05) | 8/8 | PASS |
| Tool surface, local | 13 tools registered | PASS |
| Tool surface, unauthenticated public listener | 10 stateless tools (stateful `crawl2rag`, `chat` correctly withheld) | PASS |
| Transports | stdio + Streamable HTTP | PASS |
| End-to-end MCP client tests | `tests/test_mcp_e2e.py`, `test_mcp_protocol.py`, `test_mcp_stress.py` all green | PASS |
| Third-party client matrix (Claude Desktop / Cursor / generic SDK) | Executed in prior cycle | PASS with caveat: version drift untested |

---

## 10. Remediation changelog (this revision)

| # | Fix | Root cause | Files | Verification |
|---|---|---|---|---|
| 1 | `shutdown_services()` closes every SQLite-backed singleton; each close is now bounded (`asyncio.wait_for`, 10 s) and logs a warning instead of hanging | aiosqlite worker threads are non-daemon and cache connections were never closed, so the interpreter hung after the pytest summary | `server.py` | zero aiosqlite threads after shutdown; `test_04` 281.31 s + hang → 81.98 s exit 0 |
| 2 | Shared module-level TLS context | `ssl.create_default_context(cafile=certifi.where())` rebuilt per request (0.38 s, blocking) | `security.py` | 5.83 s → 0.13 s for 15 concurrent extracts |
| 3 | Same shared context at both pipeline HTTP clients | Same per-call context cost in SearXNG / DuckDuckGo paths | `search_pipeline.py` | suite green; latency probe above |
| 4 | `weblens/src` appended to `sys.path` in test bootstrap | `weblens.apps` not importable from repo root → 2 collection errors | `tests/conftest.py` | `test_apps.py` 12 passed; `test_adversarial_grounding.py` green |
| 5 | Fuzz fixture uses `shutdown_services()` | ad-hoc closes missed pipeline/geo caches | `tests/test_04_fuzz_and_chaos.py` | exit 0, no hang |
| 6 | Stress test uses `shutdown_services()` | same | `tests/test_06_performance_stress.py` | 3 passed, 10.61 s |
| 7 | Research-lifecycle test stubs the model client (`synthesize_research_report`) | test made a **live Gemini call**, violating the suite's mock-only rule and exceeding the 60 s timeout | `tests/test_v14_crawl_and_research_lifecycle.py` | 4 passed in 11.38 s, offline |
| 8 | Research-chat test stubs `service.research.research` (returns a real `ResearchOutcome` + `Finding`) | test stubbed `service.search`/`service.extract`, which the deep-research path never calls → 0 citations | `tests/test_apps.py` | 12 passed; `total_sources` now ≥ 1 for the right reason |

No test was skipped, no assertion loosened, no timeout raised, no lint/type suppression added. Fixes 7 and 8 remove live network calls from a suite that is required to be mock-only.

---

## 11. Remaining gaps and known limitations

| ID | Gap | Severity | Disposition |
|---|---|---|---|
| GAP-001 | Arena quality gate unstable at n=5 (90.8 / 81.6 / 87.0 vs ≥90) | Medium | OPEN — needs a larger case set and a fixed-seed replay |
| GAP-002 | Cloud Run ingress unauthenticated | High | OPEN (deployment) |
| GAP-003 | No HSTS | Medium | OPEN (deployment) |
| GAP-004 | Container runs as root | Low | OPEN (deployment) |
| GAP-005 | GPT-OSS 20B ReadTimeout > 60 s | Low | OPEN — fallback works, provider slow |
| GAP-006 | CI pipeline not executed live | Low | OPEN |
| GAP-007 | Tavily Engine B blocked by budget cap (14.0 credits left) | Medium | BLOCKED pending fresh authorisation |
| SEC-V9-001 | Committed Tavily key still in git history | High | OPEN — rotate key |
| F1 / F2 / F4 / F11 / F17 | Search recall 88/90; supported answers 51/90; trap abstention 4/10; one >2.4 s outlier; no independent re-derivation | Medium | OPEN |
| F8 / F9 / F10 / F13 | RAG Recall@5, deep-research coverage, citation battery, sustained throughput | Medium | STRUCTURAL — no compatible artifacts exist |
| — | 30 workstreams executed sequentially, not as parallel subagents | Process | DISCLOSED |

Declared non-claims: no sustained-throughput (QPM) measurement; no human-panel quality judging; no live Tavily head-to-head this cycle; no claim that the arena score generalises beyond its 5 cases.

---

## 12. Machine-readable summary

Also written to `reports/master_verification_summary_2026-11-06.json`.

```json
{
  "report": "MASTER-VERIFICATION-REPORT-2026-11-05.md",
  "revision_date": "2026-11-06",
  "git_commit": "4e0885d",
  "git_branch": "main",
  "working_tree": "dirty",
  "environment": {"os": "Windows 11", "python": "3.13.15", "pytest": "9.1.1", "pytest_timeout": 60},
  "verdict": "PASS_WITH_LIMITATIONS",
  "gates": {
    "full_test_suite": {"status": "PASS", "passed": 350, "failed": 0, "errors": 0, "exit_code": 0, "duration_s": 577.85, "artifact": "reports/full_suite_final.log"},
    "security_redteam": {"status": "PASS", "vectors": 59, "passed": 59, "vulnerabilities": 0, "artifact": "reports/redteam_after_sslfix.log"},
    "bandit": {"status": "PASS", "high": 0, "medium": 0, "low": 18, "baseline_equal": true},
    "concurrency_latency": {"status": "PASS", "before_s": 5.827, "after_s": 0.132, "improvement_x": 44.1, "artifacts": ["reports/perf_ssl_context_before.txt", "reports/perf_ssl_context_after.txt"]},
    "quality_arena": {"status": "FAIL", "latest": 87.0, "target": 90.0, "runs": [90.8, 81.6, 87.0], "artifact": "reports/arena_local_2026-11-06.log"},
    "tavily_head_to_head_this_cycle": {"status": "BLOCKED", "reason": "BUDGET_CAP=0, 14.0/50.0 credits remaining"},
    "rag_retrieval": {"status": "UNSUPPORTED", "ref": "GAP-LEDGER F8"},
    "deep_research_coverage": {"status": "UNSUPPORTED", "ref": "GAP-LEDGER F9"},
    "citation_integrity_battery": {"status": "UNSUPPORTED", "ref": "GAP-LEDGER F10"},
    "mcp_protocol": {"status": "PASS", "conformance": "8/8", "tools_local": 13, "tools_public": 10}
  },
  "remediation": {"fixes_applied": 8, "fixes_verified": 8, "fixes_regressed": 0},
  "test_deltas": {
    "test_04_fuzz_and_chaos": {"before": "EXIT=1 281.31s hang", "after": "PASS 81.98s exit 0"},
    "test_06_performance_stress": {"before": "EXIT=1 14.31s gate breach", "after": "PASS 3 tests 10.61s exit 0"},
    "test_apps": {"before": "EXIT=2 collection error", "after": "12 passed"},
    "test_adversarial_grounding": {"before": "EXIT=2 collection error", "after": "PASS"},
    "full_suite_wall_clock": {"before_s": 777.10, "after_s": 577.85, "delta_pct": -25.6}
  },
  "open_gaps": ["GAP-001", "GAP-002", "GAP-003", "GAP-004", "GAP-005", "GAP-006", "GAP-007", "SEC-V9-001", "F1", "F2", "F4", "F11", "F17", "F8", "F9", "F10", "F13"],
  "disclosures": [
    "30 workstreams ran sequentially, not as parallel subagents",
    "Tavily parity figures are prior-cycle (stage7 campaign), not re-measured",
    "Arena figures are rubric-judged at n=5 and do not generalise",
    "Live Tavily key remains in git history until rotated"
  ],
  "verdict_rationale": "All locally executable gates pass with clean exits; the two unmet gates (arena quality at n=5, fresh Tavily comparison) and the committed-key finding are disclosed rather than waived."
}
```

---

## 13. Reproduction

```bash
# Full suite (green: 350 passed, exit 0)
python -m pytest tests -q -p no:cacheprovider

# Security red-team (59 vectors)
python scripts/run_security_redteam.py

# Static analysis
python -m bandit -r security.py search_pipeline.py server.py event_store.py extractor.py

# Per-module repros used in §4
python -m pytest tests/test_04_fuzz_and_chaos.py -q
python -m pytest tests/test_06_performance_stress.py -q
python -m pytest tests/test_apps.py tests/test_adversarial_grounding.py -q
python -m pytest tests/test_v14_crawl_and_research_lifecycle.py -q

# Quality arena, local-only (no Tavily credits)
BUDGET_CAP=0 ARENA_TRIALS=3 python quality_arena.py

# Prior Tavily campaign evidence
python -m json.tool reports/tavily-comparison/QUALITY-RESULTS.json
```

---

## 14. Final acceptance verdict

**PASS WITH LIMITATIONS.**

Acceptance is granted for local and private-network MCP deployments, on the strength of a fully green 350-test suite with a clean process exit, a 59/59 red-team result, unchanged static-analysis findings, a measured 44× reduction in concurrent extraction latency, and complete traceability from every claim to an artifact.

Acceptance is withheld for the following, and they are the conditions for a full PASS:

1. **Arena quality gate** — replace the 5-case arena with a fixed-seed set large enough to make ≥90 decidable, then clear it (current: 87.0/81.6/90.8).
2. **Fresh Tavily head-to-head** — requires explicit authorisation to spend the remaining 14.0 credits.
3. **SEC-V9-001** — rotate the Tavily key that remains in git history.
4. **Deployment hardening** — authenticated ingress, HSTS, non-root container, for any public exposure.
5. **Structural batteries** — RAG Recall@5, deep-research coverage, citation integrity, and sustained throughput (GAP-LEDGER F8/F9/F10/F13).

None of these is hidden behind a passing check; each is recorded with its current status above.
