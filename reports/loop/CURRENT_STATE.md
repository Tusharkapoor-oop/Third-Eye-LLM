# WebLens Continuous Improvement Loop — Current State (2026-11-02 Quality Checkpoint)

## Status: OPEN-REMEDIATION — not release-ready
- **Quality registry**: Frozen F1-F17; current V9B evidence is one 100-row run, not a two-run 100% proof.
- **Dataset**: `benchmarks/eval_dataset_expanded.json`, SHA-256 `6130548dacb595da44a0973e66c4e3a44836846baf16a97ef1ca87664f2d065f`; 200 rows available, first 100 measured by EXP-V9B-100Q.
- **Current field**: F2 answer support; corrected rerun measured 51/90 local answerable items, below the prior 73/90 report.
- **Tavily**: zero credits spent by this loop; current credential returned HTTP 401 and `BUDGET_CAP` is unset.
- **Cloud Run deployment**: live endpoint verified separately; unauthenticated capability discovery remains a security failure.

---

## Historical / current evidence

1. **Quality-loop checkpoint**:
   - State: `evidence/loop-state.json`.
   - Per-item verdicts: `evidence/raw/quality-loop-20261102/field_verdicts.jsonl`.
   - Metadata and hashes: `evidence/raw/quality-loop-20261102/metadata.json`.
   - Gap ledger: `GAP-LEDGER.md`.
   - Append-only ledger entry: `evidence/ledger.jsonl` (`QL-V9B-20261102-BASELINE`).

2. **Isolated Testing Sandbox (`weblens-lab/`)**:
   - Boundary tests: PASSED.
   - Resource limits: Configured (2.0 CPUs, 2048MB RAM, 128MB cache).
   - Containerization: `Dockerfile` and `docker-compose.yml` authored and verified.
   - Zero-secrets verification: Passed across git history and sandbox templates.

3. **Full Product Implementation (All 9 Workflows)**:
   - Deep Research: Implemented & tested.
   - Company Researcher: Implemented & tested.
   - Chat / Answer Engine: Implemented & tested.
   - Crawl2RAG: Implemented & tested.
   - Market Researcher: Implemented & tested.
   - Sheets Enricher: Implemented & tested (formula injection defense active).
   - Meeting Prep: Implemented & tested (privacy boundary defense active).
   - WebLens 101: Implemented & tested.
   - Research Agent Chat (Workflow 9): Implemented & tested with SQLite session persistence.
   - **App Test Suite**: 11 passed in 7.31s (100%).

4. **Paired Benchmark Pilot (WebLens Independent vs Tavily)**:
   - Queries evaluated: 18 paired, interleaved.
   - WebLens median latency: **46.5 ms** (vs Tavily 896.6 ms).
   - WebLens Mean Precision@5: **0.496** (vs Tavily 0.367).
   - WebLens Mean Tokens: **387.2 tokens** (vs Tavily 1,432.4 tokens).
   - WebLens Cost: **$0.00** (vs Tavily $0.09).
   - Full evaluation report suite written under `reports/tavily-weblens-comparison/`.

5. **Security & Red-Team Verification**:
   - Total automated security tests: **184 tests passed (0 failures)**.
   - SSRF & IP encoding tests: 80 passed.
   - Prompt injection tests: 50 passed.
   - Canary secrets & crawler traps: 20 passed.
   - Token boundary tests: 18 passed.
     - Fixed SEC-V8-001 (deep research continuous text token blowout).

6. **Fresh assertion-level application run**:
   - 9/9 workflows returned PASS with 0 partial and 0 fail.
   - Evidence: `evidence/raw_results/nine_apps/nine_apps_verification_20261102T172245Z.json`.
   - This does not close F1-F17; several application assertions do not measure claim-level correctness.

## Resume command

```powershell
.venv\Scripts\python.exe evidence\quality_loop\derive_quality_fields.py
```

The next authorized measurement requires a valid Tavily credential and an
explicit `BUDGET_CAP`, then a fresh two-run F2/F1 benchmark with answer and
citation artifacts. Do not treat any aggregate in this file as a PASS-100 gate.

## V9 Continuation Checkpoint (2026-11-02)
- **SEC-V9-001 fixed**: live Tavily key redacted from 2 committed reports; rotation by owner still required (key remains in git history of `1c11ac3`).
- **Deployed System 2 verified live**: root 200 healthy, MCP init 200, 10 tools listed; drift documented (`reports/deployed-security/DEPLOYMENT_DRIFT_2026-11-02.md`): `/healthz` 404 remotely though code exists at HEAD, deployed image predates `a9bd964`.
- **Scaled benchmark EXP-V9B-100Q executed**: 100 held-out queries × 3 systems; Tavily wins quality (P@5 0.756, support 0.90), local WebLens wins speed (922.7 ms p50) and cost ($0); see `reports/three-system-comparison/THREE_SYSTEM_100Q_EXTENSION_2026-11-02.md`.
