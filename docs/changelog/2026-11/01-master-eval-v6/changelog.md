# Changelog: Master Evaluation & Red-Team Audit (Prompt v6)

**Date:** 2026-11-01  
**Topic:** WebLens Master Evaluation and Defensive Red-Team Audit (Prompt v6)  
**Status:** Verification & Audit Complete  

---

## 1. Executive Summary of Actions Taken

1. **Part 13: Quarantine of Withdrawn Reports (Completed)**
   - Moved `reports/FINAL-AUDIT-REPORT.md`, `reports/11-quality-and-factual-accuracy.md`, and `reports/15-regression-and-stress.md` to `reports/_withdrawn/` unchanged.
   - Published `reports/WITHDRAWN.md` enumerating the 16 methodological defects (empty dataset hashes, unverified claims, missing kappa, stale intervals, conflicting attack counts).

2. **Part 2 & 2.5b: Cryptographic Integrity Architecture & Gate 1 (Completed — PASS)**
   - Implemented `tools/evidence_run.py` enforcing immutable IDs, SHA-256 output hashes, secret redaction, and SHA-256 hash chaining in `evidence/ledger.jsonl`.
   - Built `tools/verify_evidence.py` and `tools/verify_chain.py` verifying cryptographic ledger chains and file hashes.
   - Implemented `tests/test_gate1_tamper_mutation.py` confirming that tampering with ledger lines or raw outputs is detected, and that disabling SSRF guards, injection scanners, or token caps causes explicit test failures.
   - Gate 1 Evidence ID: `gate1-tamper-mutation-v3`. Result: PASS.

3. **Part 3: Pre-Registration (Completed)**
   - Authored and committed `evidence/prereg.md` freezing hypotheses H1-H5, performance gates (search p50 <= 1.5s, p95 <= 5.0s), quality-first guard rules, and dataset SHA-256 digests.
   - Evidence ID: `prereg-commit`. Ledger Head Hash: `2a0412ee8cd13626...`.

4. **Part 5: Datasets & Stratified Human Review Sample (Completed)**
   - Validated dataset integrity against real SHA-256 digests:
     - Core Regression (`weblens/benchmarks/queries.jsonl`): `442c7bfc90acc3aef89a22d17ebf24ec8a2b6e310ed10ceab32aa0df2ca9ccba`
     - Evaluated Gold (`reports/tavily-comparison/data/stage7_dataset.jsonl`): `a4a64151fbdbda850a9de128bb7f83ec67f126b633aac42488c6f0b9296a9b21`
     - Expanded QA (`benchmarks/eval_dataset_expanded.json`): `6130548dacb595da44a0973e66c4e3a44836846baf16a97ef1ca87664f2d065f`
   - Generated `evidence/human_review.csv` containing 150 stratified items across categories with blind A/B randomization and blank columns for human review.

5. **Part 7: Defensive Penetration Testing Program (P0-P14 Completed)**
   - P0 Threat Model documented in `evidence/threat_model.md`.
   - P1 SSRF Matrix: 32/32 vectors blocked at connection time; 0 packets reached fixture targets.
   - P3 Tier D Prompt Injection & Benign FPR: 76.24% recall across 5,000 attacks; **0.00% False Positive Rate across 10,000 benign technical texts**. Documented 0% recall on non-English injection prompts.
   - P9 Canary Secrets: Verified canary tokens never leak in errors, cache keys, or logs (`tests/test_p9_canary_secrets.py`).
   - P10 Supply Chain: Audited 75 pinned packages in `uv.lock` via Google OSV API (0 vulnerabilities). Verified vendored package `@modelcontextprotocol/server@2.3.1` hash.
   - P11 Static Analysis: Audited 92 source files (0 `eval`, 0 `exec`, 0 `os.system`, 0 `pickle`, 0 shell subprocesses, 0 unparameterized SQL).

6. **Part 6 & Part 9: Report Generation & Numeric Linting (Completed — PASS)**
   - Built deterministic report generator `tools/build_report.py`.
   - Generated `evidence/manifest.json` and `reports/MASTER-EVALUATION-REPORT.md`.
   - Enforced numeric linter `tools/lint_report.py`: 65 metrics verified traceable, hash chain verified, byte-identical rebuild confirmed.

7. **Part 12: Independent Owner Verification Guide (Completed)**
   - Authored `VERIFY-ME.md` detailing exact commands for the owner to verify hash chains, dataset digests, report diffs, process table, and credit accounting.
