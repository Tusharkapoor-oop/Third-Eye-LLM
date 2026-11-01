# WebLens Historical Evidence Reconciliation

## Date of Reconciliation
2026-11-01

## Purpose
Investigate and resolve contradictions identified between historical experiment records, decision JSON files, git commits, and subsequent narrative summary reports.

---

## 1. Contradiction Resolution: Cycle 1 Chunker Modification

### Prior Conflicting Reports
- Narrative report in `reports/loop/SUMMARY.md` and an earlier `EVIDENCE_RECONCILIATION.md` asserted that Cycle 1 was "KEPT" with a "100pp improvement in tail-fact recall".
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
     "patch": "evidence/cycles/1/rejected.patch"
   }
   ```
2. **Patch Artifact**:
   The patch file `evidence/cycles/1/rejected.patch` contains the proposed `spread_chunks` function for `weblens/src/weblens/extract/passages.py`.
3. **Current Codebase Verification**:
   Inspection of `weblens/src/weblens/extract/passages.py` confirmed that `spread_chunks` is **absent**.
4. **Conclusion**:
   Cycle 1 was **REJECTED and REVERTED** due to a +33.2% p95 latency regression (exceeding the +10% regression margin) and 2 test failures. The previous narrative claim that Cycle 1 was "KEPT" was erroneous. Cycle 1 remains REVERTED.

---

## 2. Contradiction Resolution: Cycles 2 and 3

### Historical Records
1. **Cycle 2**:
   - Evaluated on a 50-query developmental sample.
   - Claimed answer support increased from 40% (16/40 answerable) to 70% (35/50).
   - Modification: Added 22 search heuristic keyword tokens to `tech_markers` in `src/engine/search/aggregator.py`.
   - Flaw: The sample was small (n=50), unblinded, and unstratified. Live engine provider variance accounted for substantial variance.
2. **Cycle 3**:
   - Re-evaluation scored 68% (34/50), below the Cycle 2 checkpoint.
   - Status: Correctly marked **REJECTED** in decision logs.
3. **Conclusion**:
   Neither Cycle 2 nor Cycle 3 demonstrated statistically robust, pre-registered held-out generalizability. Under v8 protocol, all prior performance claims are classified as **UNVERIFIED** until reproduced under the isolated, paired evaluation sandbox.

---

## 3. Ground-Truth Baseline Matrix

| Feature / Metric | Claimed in Narrative | Ground Truth in Repository | Verification Status |
| :--- | :--- | :--- | :--- |
| **Cycle 1 (Tail Chunker)** | KEPT (+100pp) | REJECTED & REVERTED (`decision.json`, `rejected.patch`) | REVERTED (Not in production code) |
| **Cycle 2 (Heuristics)** | KEPT (70%) | Present in `src/engine/search/aggregator.py` | UNVERIFIED (n=50, high variance) |
| **Cycle 3 (Tech markers)** | REJECTED (68%) | REJECTED in logs | REJECTED |
| **Tavily Independent Parity** | Variously claimed | No paired 10,000+ benchmark executed | UNVERIFIED |
| **Zero Secrets in Git** | 100% clean | Verified via automated regex across history | VERIFIED |
| **MCP Streamable HTTP** | Deployed | Live on Cloud Run (`https://weblens-16131012091.us-central1.run.app`) | VERIFIED |

---

## 4. Policy for V8 Execution
1. Treat all prior uncalibrated benchmark numbers as historical artifacts, not verified performance baselines.
2. Establish fresh, reproducible baselines within the isolated sandbox (`weblens-lab/`).
3. Maintain cryptographic ledger chain integrity. Never alter historical decision records.
