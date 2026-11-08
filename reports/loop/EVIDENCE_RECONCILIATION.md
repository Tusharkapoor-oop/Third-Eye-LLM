# WebLens Historical Evidence Reconciliation

## Date of Reconciliation
2026-11-08 (V7 autonomous engineering continuation)

## Reconciler
Lead agent (sequential specialist mode; only logfare subagent provider available, no parallel coding agents).

## Purpose
Investigate and resolve contradictions identified between historical experiment records, decision JSON files, git commits, and subsequent narrative summary reports. Preserve immutable historical records and establish a sound baseline for V7 work.

---

## 1. Contradiction Resolution: Cycle 1 Tail-Reachability Chunker

### Prior Conflicting Reports
- Earlier narrative reports (e.g. `reports/loop/SUMMARY.md` and the previous `EVIDENCE_RECONCILIATION.md`) asserted that Cycle 1 was "KEPT" with a "+100pp improvement in tail-fact recall".
- Primary source artifact `evidence/cycles/1/decision.json` recorded `verdict: "REJECT"` and `action: "REVERTED"`.

### Ground Truth Investigation
1. **Primary Decision Record**:
   Inspected `evidence/cycles/1/decision.json`:
   ```json
   {
     "verdict": "REJECT",
     "action": "REVERTED",
     "guard_results": {
       "p95_latency_within_10pct": false,
       "tests_ok": false,
       "tokens_within_5pct": true,
       "head_not_worse": true,
       "ssrf_ok": true,
       "fixture_recall_not_worse_2pp": true
     },
     "reject_reasons": ["p95_latency_within_10pct", "tests_ok"],
     "p95_latency_before": 56.79,
     "p95_latency_after": 75.65,
     "candidate_tests_failed": 2,
     "test_failure_cause": "The two new tests used a trailing sentence shorter than the 40-character chunk minimum, so it was dropped before selection; the held-out pages use full sentences. The candidate test result is a test-fixture defect, not a product pass."
   }
   ```
2. **Patch Artifact**:
   The patch file `evidence/cycles/1/rejected.patch` contains the proposed `spread_chunks` function for `weblens/src/weblens/extract/passages.py`.
3. **Current Codebase Verification** (as of HEAD `ccafa81`):
   - Inspection of `src/weblens/extract/passages.py` and `weblens/src/weblens/extract/passages.py` shows that a function named `spread_chunks` is **currently present** (added between baseline `902415d` and HEAD `ccafa81`).
   - This contradicts the previous reconciliation's claim that "spread_chunks is absent".
   - The `decision.json` artifact records a **rejected** Cycle 1, but the codebase today contains the implementation.
4. **Root-Cause Synthesis**:
   - Cycle 1 was **formally rejected and reverted** per the ledger.
   - Later development (presumably post-reversion) **reintroduced the same function** independently, likely by copying it from the rejected patch. This is a new implementation, not the same Cycle 1 candidate.
   - Under the V7 protocol this independent reimplementation receives a new experiment ID and must be re-evaluated; it is not the original Cycle 1.
5. **Conclusion**:
   - **Cycle 1 itself is still REJECTED and REVERTED** in the historical record. That decision is immutable.
   - **Functionality equivalent to Cycle 1 is currently live in HEAD** and requires fresh evaluation under V7 gates before it can be considered accepted.

---

## 2. Contradiction Resolution: Cycles 2 and 3

### Historical Records
- **Cycle 2**: Claimed 70% answer support on a 50-query developmental sample. Modification: added 22 search heuristic keyword tokens to tech markers. Flaw: small (n=50), unblinded, unstratified, and confounded by live engine variance.
- **Cycle 3**: Re-evaluation scored 68% (34/50), below Cycle 2. Marked REJECTED.

### Verification
- The `evidence/ledger.jsonl` does not contain a pre-registered, paired, held-out reproduction of Cycle 2's 70% claim with SHA-256 dataset hashes under identical conditions.
- Subsequent `EXP-V9B-100Q` (100-query held-out benchmark, three-system comparison) reports Tavily Direct support 0.90, local keyless WebLens support 0.80, and deployed WebLens support 0.76.

### Conclusion
- Cycle 2's 70% and Cycle 3's 68% are **UNVERIFIED** under V7 reproducibility standards.
- They remain historical artifacts. Any new improvement must be evaluated against the held-out dataset `benchmarks/eval_dataset_expanded.json` (SHA-256 `6130548dacb595da44a0973e66c4e3a44836846baf16a97ef1ca87664f2d065f`) using a paired design.

---

## 3. Contradiction Resolution: Cycle 1 vs. Live Code

| Artifact | Cycle 1 Verdict | Current HEAD | V7 Status |
|----------|-----------------|--------------|-----------|
| `evidence/cycles/1/decision.json` | REJECT | unchanged | immutable historical record |
| `weblens/src/weblens/extract/passages.py` at `ccafa81` | absent at baseline | `spread_chunks` present | **needs V7 re-evaluation** |
| `src/weblens/extract/passages.py` at `ccafa81` | absent at baseline | `spread_chunks` present | **needs V7 re-evaluation** |

The previous reconciliation incorrectly asserted that `spread_chunks` was "absent" from production code. This statement is **false** in the current HEAD. The previous reconciliation's evidence chain on this point is downgraded to `OUTDATED/INCORRECT`.

---

## 4. Ground-Truth Baseline Matrix

| Feature / Metric | Claimed in Narrative | Ground Truth in Repository | Verification Status |
| --- | --- | --- | --- |
| **Cycle 1 (Tail Chunker)** | KEPT (+100pp) | Decision `REJECT` + later independent reimplementation in HEAD | REJECTED historically; live equivalent needs new eval |
| **Cycle 2 (Heuristics)** | KEPT (70%) | No paired held-out reproduction with hashes | UNVERIFIED |
| **Cycle 3 (Tech markers)** | REJECTED (68%) | Decision `REJECT` | REJECTED |
| **Tavily Independent Parity** | Variously claimed | No 10k+ paired benchmark | UNVERIFIED |
| **Zero Secrets in Git** | 100% clean | Canary tests in ledger; `EXP-008` clean | VERIFIED |
| **MCP Streamable HTTP** | Deployed | Cloud Run endpoint live | VERIFIED |
| **Deployed `/healthz` 404** | Drift finding | Documented in `reports/deployed-security/DEPLOYMENT_DRIFT_2026-11-02.md` | VERIFIED drift |
| **spread_chunks in HEAD** | Previously claimed absent | Present in both `src/` and `weblens/src/` | CORRECTED to PRESENT |

---

## 5. Policy for V7 Execution
1. Treat all prior uncalibrated benchmark numbers as historical artifacts, not verified performance baselines.
2. The independently reintroduced `spread_chunks` functionality is treated as a new candidate requiring V7 gating.
3. Establish fresh, reproducible baselines within the isolated sandbox (`weblens-lab/`) using the held-out dataset.
4. Never modify historical decision records. Historical records remain immutable.
5. Before new feature work, resolve the inconsistency that a formally rejected-and-reverted change is now live in HEAD.

---

## 6. Immediate Actions Required
1. **Reconcile working tree**: current HEAD contains many uncommitted modifications and untracked files; establish a clean checkpoint.
2. **Evaluate `spread_chunks` live version**: run extraction/recall benchmarks to determine whether the candidate satisfies latency, token, and test gate thresholds.
3. **Restore release-gate discipline**: run unit/integration/security tests against the current working tree and record results in the ledger.
4. **Document the corrected reconciliation**: this file supersedes the 2026-11-01 version.
