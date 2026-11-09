# Addendum — cross-model verification, agent team, harness inventory

**Date:** 2026-11-08 · **Commit:** `4e0885d` (working tree dirty) · **Supersedes:** nothing — this extends `reports/MASTER-VERIFICATION-REPORT-2026-11-05.md`

**Scope of this addendum:** Qwen/Gemma provider support, a strict cross-model battery, an executable agent team, and a factual inventory of what this harness can import.

---

## 1. Bottom line

| Item | Result | Evidence |
|---|---|---|
| Qwen provider route | Implemented, unit-tested, **BLOCKED** in this environment (no key/gateway) | `tests/test_model_provider_gateway.py` (7 passed); `reports/cross-model/battery_20261108T184520.json` |
| Gemma provider route | Implemented, unit-tested, **BLOCKED** (NVIDIA returns `403 Authorization failed`) | same battery; raw log `reports/cross_model_run2.log` |
| Mistral (NVIDIA) | **BLOCKED** (same `403`) — previously worked, credential now rejected | raw probe output in this file's §3 |
| Gemini | **PASS** on the full 10-check battery at 2026-11-08T18:51Z; now **BLOCKED** by free-tier daily quota (20 req/day) | `reports/cross-model/battery_20261108T185128.json` |
| Agent team | Runs end-to-end; **6/8 roles PASS, `quality` FAIL, `models` BLOCKED**, team verdict FAIL | `reports/team/20261108T190230/report.md`, `reports/team/quality_gate_2026-11-08/report.md` |
| Full suite (357 tests) | **356 passed, 1 failed, exit 1** — the single failure is the arena score gate on a real 87.0 < 90.0 score | `reports/full_suite_2026-11-08.log` |
| Harness/plugin inventory | Written from live code | `reports/harness-plugin-inventory.md` |

Nothing in this addendum upgrades a blocked model to a pass. The team and battery both exit `2` for BLOCKED precisely so a missing credential cannot read as green.

---

## 2. Product changes

| # | Change | Why | Verification |
|---|---|---|---|
| 1 | `ModelProvider.QWEN` / `GEMMA`; `model_family()`; `_generate_openai_compatible()`; `model_readiness()` | Qwen and Gemma were not addressable at all. Readiness is credential-based and separate from live reachability, so "configured" is never reported as "working" | 7 mocked unit tests |
| 2 | Qwen route honours `QWEN_BASE_URL`/`QWEN_API_KEY`/`QWEN_MODEL` (falls back to `DASHSCOPE_API_KEY`) | Works with any OpenAI-compatible gateway without inventing one | `test_qwen_routes_to_gateway_with_its_own_key` |
| 3 | Gemma route uses its own host/key and skips the generic NVIDIA retry | The generic route duplicated a known 403 against the same host | `test_gemma_uses_gemma_host_and_skips_generic_nvidia_route` |
| 4 | Gemini SDK calls bounded by `HttpOptions(timeout=20_000)` | A stalled request kept its default-executor thread alive; interpreter shutdown then blocked ~300 s (`RuntimeWarning: The executor did not finishing joining its threads within 300 seconds`) | battery wall clock 300 s+ → 48 s; `reports/cross_model_run3.log` vs `run4.log` |
| 5 | Deterministic research fallback table no longer prints `https://…...` as link text | Produced malformed citation targets, which the citation-integrity check correctly flagged | `test_research_fallback_emits_no_malformed_url` |
| 6 | `model_readiness()` exposes per-model blocked reasons | Blocked states must be explainable, not silent fallbacks | `test_readiness_requires_key_and_gateway` |

## 3. Cross-model battery (`scripts/cross_model_verification.py`)

Layers, top to bottom, for every model: credential → live reachability (the **requested** model must answer; a fallback is BLOCKED) → exact instruction → JSON contract → usage accounting → latency ceiling → determinism at temperature 0 → citation integrity (all sources cited, no invented URLs) → no fabricated sources on empty evidence → engine e2e (`server.web_search` → `server.extract_url` → synthesis over real extracted text).

**Gemini full pass** (`battery_20261108T185128.json`):

| Check | Status | Detail |
|---|---|---|
| reachability | PASS | HTTP 200 via gemini, 4402 ms |
| exact_instruction | PASS | `'PONG'` |
| usage_accounting | PASS | prompt 18 / completion 2 / model_name match |
| latency_ceiling | PASS | 5348 ms ≤ 30000 ms |
| json_contract | PASS | `{"status":"ok","count":3}` |
| determinism_temp0 | PASS | `'Red'` == `'Red'` |
| citation_integrity | PASS | 0 missing, 0 invented |
| no_fabrication_empty_evidence | PASS | 0 URLs with no evidence |
| e2e_search | PASS | 3 results |
| e2e_extract | PASS | 1668 chars |
| e2e_synthesis | PASS | 6045 chars via gemini |

**Qwen / Gemma / Mistral** — blocked with exact causes:

- Qwen: no `QWEN_BASE_URL`/`QWEN_API_KEY`; the account's NVIDIA catalogue (84 models) contains no Qwen entry.
- Gemma: `POST /v1/chat/completions` with `google/gemma-4-31b-it` → `403 {"status":403,"detail":"Authorization failed"}`; fallback answered as `gemini-3.5-flash`, which the battery rejects as not-Gemma.
- Mistral: `mistralai/mistral-large-4-1t-a52b` → `403 Authorization failed` (regression versus the earlier cycle where it answered; the key is still accepted by `GET /v1/models`, so this is an entitlement change on the account, not a code fault).

To unblock, supply either a valid NVIDIA entitlement for those model IDs, or an OpenAI-compatible Qwen gateway:

```bash
QWEN_BASE_URL=https://<gateway>/v1
QWEN_API_KEY=<key>
QWEN_MODEL=qwen/qwen3-235b-a22b-instruct
# optional: GEMMA_BASE_URL / GEMMA_API_KEY / GEMMA_MODEL
```

## 4. Agent team (`.freebuff/agents/team.json` + `scripts/agent_team.py`)

Seven sequential roles, each owning one strict gate; the runner stores per-role logs and refuses to upgrade a result (0 → PASS, 2 → BLOCKED, else FAIL).

| # | Role | Gate | Result |
|---|---|---|---|
| 1 | architect | compile + import smoke | PASS (23.15 s) |
| 2 | security | 59-vector red-team | PASS (10.05 s) |
| 3 | contract | static/deps + MCP protocol | PASS (112.09 s) |
| 4 | correctness | search/extract/crawl/cache/failure-injection — 115 tests | PASS (278.86 s) |
| 5 | applications | apps + adversarial grounding + v14 — 43 tests | PASS (43.04 s) |
| 6 | performance | concurrency/leak/RAM gates | PASS (9.44 s) |
| 7 | quality | arena score/compression gates on the latest arena artifact | **FAIL** (4.14 s) — `arena_report.json` holds 87.0 < 90.0 |
| 8 | models | cross-model battery | **BLOCKED** (81.28 s) |

Team verdict on the first full run: **BLOCKED** (6 PASS, 1 BLOCKED — `quality` was added to the team afterwards). With `quality` included the team verdict is **FAIL**, because the recorded arena score genuinely misses its ≥ 90 gate. Both outcomes are produced by the runner's own rules (0 → PASS, 2 → BLOCKED, else FAIL); neither is overridden by hand.

Usage: `python scripts/agent_team.py`, `--list`, `--only <role>`, `--keep-going`.

Because this harness has no sub-agent tool, the team is a sequential role pipeline with handoff — not parallel agents. That is stated in the team file itself.

## 5. Harness / plugin inventory

Summarised in `reports/harness-plugin-inventory.md`: harness surfaces (tools, skill catalog, `npx skills`, no sub-agents) and the seven repository extension points (MCP tools, model providers, search providers, extraction tiers, reranking/chunking, applications, agent team) with their registration sites and enabling env vars.

## 6. Full-suite regression after these changes

`python -m pytest tests -q -p no:cacheprovider` → `reports/full_suite_2026-11-08.log`

```
1 failed, 356 passed in 513.66s (0:08:33)
EXIT=1
```

The 357 tests are the previous 350 plus the 7 new provider-route tests. The single failure is `tests/test_07_live_quality_arena.py::test_arena_benchmark_score_gate`, which grades the most recent `arena_report.json`:

```
assert avg_score >= 90.0, f"Engine A average score {avg_score} must be >= 90.0/100"
E  AssertionError: Engine A average score 87.0 must be >= 90.0/100
```

That is the same GAP-001 arena variance already reported in the master report (90.8 / 81.6 / 87.0). It is **not** a regression from this session's changes: the two other tests in that file pass, and the code paths this addendum touched (provider routing, Gemini timeout, fallback table formatting) are covered by the 7 new passing tests. The gate is left failing on purpose — lowering the threshold or pinning the artifact would hide a real quality shortfall.

Note the structural weakness this exposes: the gate reads whatever the last local `quality_arena.py` run left in the repo root, so its result depends on external model availability. A durable fix is to have the arena write a versioned artifact and have the gate grade a pinned baseline plus the current run; that is a test-infrastructure change and is listed as an open item, not done here.

## 7. Remaining blockers (unchanged verdict: PASS WITH LIMITATIONS)

1. **Model access** — Qwen has no credential; Gemma/Mistral return 403; Gemini free-tier quota resets in ~18 h. Re-run `python scripts/cross_model_verification.py` and the `models` role once a credential works.
2. **Arena quality gate** — still unstable at n=5 (90.8 / 81.6 / 87.0 vs ≥ 90).
3. **Tavily head-to-head** — not re-run (14.0 credits preserved).
4. **SEC-V9-001** — committed key still in git history until rotated.
