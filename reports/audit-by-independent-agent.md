# Independent Audit and Adversarial Evaluation Report

**Target Document:** `reports/MASTER-EVALUATION-REPORT.md`  
**Manifest Target:** `evidence/manifest.json`  
**Ledger Target:** `evidence/ledger.jsonl`  
**Auditor Role:** Independent Release Auditor & Adversarial Evaluator  
**Audit Date:** 2026-11-01  
**Audit Environment:** Read-Only Analysis Shell (Python 3.14.0 / Windows 11 AMD64)

---

## 1. Executive Summary

An adversarial audit was conducted on the WebLens evaluation artifacts, cryptographic evidence ledger, report generator, and empirical claims.

### Overall Auditor Verdict: **CONDITIONAL PASS WITH SEVERE METROLOGICAL DEFECTS**
* **Cryptographic Hash Chain:** **PASS.** The ledger chain hashes, block linkage (`prev_hash`), and file payload SHA-256 digests verify completely.
* **Linter & Rebuild Determinism:** **FAIL.** `tools/lint_report.py` fails when executed in an auditor's read-only environment due to in-place file write operations, and fails on byte-reproducibility due to uncommitted ledger mutations (drift between frozen report at 31 runs vs current ledger).
* **Tone & Absolutist Language Policy:** **PASS.** Zero instances of forbidden phrases ("certified", "production ready", "zero vulnerabilities", "fully secure", "guaranteed", "hallucination-free", "impenetrable") were detected.
* **Tavily Accounting Reconciliation:** **PASS.** Reconciled with raw telemetry in `reports/tavily-comparison/raw/usage_final.json`.
* **Adversarial Falsification:** **MULTIPLE CLAIMS FALSIFIED.** Critical discrepancies were proven:
  1. **Dataset Misattribution:** `benchmarks/eval_dataset.json` item count and SHA-256 are falsified in the report (claimed 58 items and hash `442c7bfc...`; actual file contains 50 items and hash `846b4de9...`).
  2. **Runtime Python Version Misrepresentation:** Report claims Python `3.13.15`, whereas the actual execution environment logged across raw outputs and ledger records is Python `3.14.0`.
  3. **Phantom "Live Credential" Panic in `.env.example`:** The security warning urging rotation of a supposed non-placeholder key in `.env.example` is an artifact of a regex parser bug in `exp_08_secrets.py` that swallowed newlines and matched the adjacent key name (`EXA_API_KEY=`). The key was actually empty.
  4. **Mutation Score Inflation:** The 100% mutation detection rate (`4/4`) fraudulently counts the unmutated baseline control (`clean_copy_verifies`) as a detected mutation.
  5. **Contaminated Latency Metric:** The extraction latency calculation mixes three `0.0 ms` non-network budget-slicing passes into network latency averages, artificially diluting the mean.

---

## 2. Cryptographic Chain & Ledger Verification

The verification script `tools/verify_evidence.py` was executed directly against `evidence/ledger.jsonl` and all output files in `evidence/raw/`.

### Findings:
1. **Initial Verification Check:**
   * Runs inspected: `31`
   * Class distribution: `{'MOCK': 4, 'SIMULATED': 11, 'REAL': 16}`
   * Ledger Head Hash: `281f029e5ab8a0a00efb27eda6f3954c22bb755bf8910e3d9d59ed18e2e70a35`
   * Verdict: **PASS evidence chain and artifact hashes**
2. **Subsequent Ledger Mutation During Audit:**
   * The ledger was dynamically appended with additional experimental cycles (EXP-100, EXP-101, EXP-100b, EXP-101b, EXP-101c, EXP-104), advancing the ledger to 38 runs with head hash `1fa81096ecca0fdba9dd20905e16a9ae12307555fde9311aa849b6edbfbdd734`.
   * Re-running `python tools/verify_evidence.py` confirmed the extended chain maintained strict cryptographic integrity (`PASS evidence chain and artifact hashes`).
3. **Artifact Integrity:**
   * Every file referenced in `evidence/ledger.jsonl` exists on disk.
   * Every SHA-256 payload matches the canonical digest recorded in the ledger entry.

---

## 3. Linter Execution & Rebuild Reproducibility

Executing `python tools/lint_report.py` produced an immediate failure:

```
PermissionError: [Errno 13] Permission denied: 'C:\\Users\\ACER\\Downloads\\Broswer for ai agnets\\evidence\\manifest.json'
```

### Analysis of Linter Defects:
1. **Destructive Rebuild in Audit Mode:** `tools/lint_report.py` invokes `build_report.build()`, which unconditionally executes `OUT_MANIFEST.write_text(...)` and `OUT_REPORT.write_text(...)`. In an independent auditor's environment (or any non-writable CI runner), this raises `PermissionError` and breaks the lint pipeline.
2. **Ledger Drift Failure:** When `Path.write_text` was stubbed in memory to simulate a dry-run check, `lint_report.py` failed with:
   ```
   FAIL report is not byte-identical to a fresh rebuild
   FAIL manifest differs from a fresh rebuild
   FAIL 2 lint problem(s)
   ```
   * The report on disk was built at `2026-11-01 13:34:49 UTC` pinned to ledger head `281f029e...` (31 runs).
   * Because subsequent experiments were appended to `evidence/ledger.jsonl`, a fresh deterministic rebuild produces a report reflecting 36+ runs and a new ledger head. The document on disk is stale relative to the active ledger.

---

## 4. Independent Re-Derivation of Numeric Tokens

An independent Python analysis was executed directly against raw JSON records in `evidence/raw/` and datasets in `benchmarks/`. Below are 52 re-derived numeric tokens compared against `reports/MASTER-EVALUATION-REPORT.md` and `evidence/manifest.json`.

| # | Metric / Token Description | Raw Evidence Source | Re-Derived Value | Report Claim | Manifest Value | Status |
|---|---|---|---|---|---|---|
| 1 | Test cases collected | `EXP-001b/result.json` | 163 | 163 | 163 | PASS |
| 2 | Test cases passed | `EXP-001b/result.json` | 162 | 162 | 162 | PASS |
| 3 | Test cases failed | `EXP-001b/result.json` | 0 | 0 | 0 | PASS |
| 4 | Test cases skipped | `EXP-001b/result.json` | 1 | 1 | 1 | PASS |
| 5 | Test cases executed (pass+fail) | `EXP-001b/result.json` | 162 | 162 | 162 | PASS |
| 6 | Test suite exit code | `EXP-001b/result.json` | 0 | 0 | 0 | PASS |
| 7 | SSRF variants attempted | `EXP-002/result.json` | 32 | 32 | 32 | PASS |
| 8 | SSRF variants blocked | `EXP-002/result.json` | 32 | 32 | 32 | PASS |
| 9 | SSRF packets to fixture | `EXP-002/result.json` | 0 | 0 | 0 | PASS |
| 10 | SSRF block percentage | Wilson score (32/32) | 100.0% | 100.0% | 100.0% | PASS |
| 11 | SSRF block CI lower | Wilson score (32/32) | 89.3% | 89.3% | 0.8927 | PASS |
| 12 | SSRF block CI upper | Wilson score (32/32) | 100.0% | 100.0% | 1.0 | PASS |
| 13 | Injection attacks tested | `EXP-003/result.json` | 64 | 64 | 64 | PASS |
| 14 | Injection attacks flagged | `EXP-003/result.json` | 48 | 48 | 48 | PASS |
| 15 | Injection detection rate (%) | Wilson score (48/64) | 75.0% | 75.0% | 75.0% | PASS |
| 16 | Injection detection CI lower | Wilson score (48/64) | 63.2% | 63.2% | 0.6318 | PASS |
| 17 | Injection detection CI upper | Wilson score (48/64) | 84.0% | 84.0% | 0.8403 | PASS |
| 18 | Benign injection controls | `EXP-003/result.json` | 64 | 64 | 64 | PASS |
| 19 | Benign false positives | `EXP-003/result.json` | 1 | 1 | 1 | PASS |
| 20 | Injection FP rate (%) | Wilson score (1/64) | 1.6% | 1.6% | 1.6% | PASS |
| 21 | Injection FP CI lower | Wilson score (1/64) | 0.3% | 0.3% | 0.0028 | PASS |
| 22 | Injection FP CI upper | Wilson score (1/64) | 8.3% | 8.3% | 0.0833 | PASS |
| 23 | Cache test cases | `EXP-004b/result.json` | 11 | 11 | 11 | PASS |
| 24 | Cache cases passed | `EXP-004b/result.json` | 11 | 11 | 11 | PASS |
| 25 | Cache pass rate (%) | Wilson score (11/11) | 100.0% | 100.0% | 100.0% | PASS |
| 26 | Cache pass CI lower | Wilson score (11/11) | 74.1% | 74.1% | 0.7412 | PASS |
| 27 | Cache pass CI upper | Wilson score (11/11) | 100.0% | 100.0% | 1.0 | PASS |
| 28 | Extraction fixture pages | `EXP-005/result.json` | 14 | 14 | 14 | PASS |
| 29 | Extraction planted facts found | `EXP-005/result.json` | 13 | 13 | 13 | PASS |
| 30 | Extraction planted facts total | `EXP-005/result.json` | 17 | 17 | 17 | PASS |
| 31 | Pages with full recall | `EXP-005/result.json` | 6 | 6 | 6 | PASS |
| 32 | Pages with zero recall | `EXP-005/result.json` | 3 | 3 | 3 | PASS |
| 33 | Fact recall rate (%) | Wilson score (13/17) | 76.5% | 76.5% | 76.5% | PASS |
| 34 | Fact recall CI lower | Wilson score (13/17) | 52.7% | 52.7% | 0.5273 | PASS |
| 35 | Fact recall CI upper | Wilson score (13/17) | 90.4% | 90.4% | 0.9045 | PASS |
| 36 | Extraction latency sample count | `EXP-005` rows | 14 | 14 | 14 | PASS |
| 37 | Extraction latency mean (ms) | `EXP-005` row mean | 92.8 | 92.8 | 92.82 | PASS |
| 38 | Extraction budget checks count | `EXP-005` rows count | 14 | 14 | 14 | PASS |
| 39 | Static article facts recovered | `EXP-005` row 0 | 5/5 | 5/5 | 5/5 | PASS |
| 40 | Table page facts recovered | `EXP-005` row 1 | 3/3 | 3/3 | 3/3 | PASS |
| 41 | Malformed HTML facts recovered | `EXP-005` row 2 | 1/1 | 1/1 | 1/1 | PASS |
| 42 | Non-UTF8 facts recovered | `EXP-005` row 3 | 0/2 | 0/2 | 0/2 | PASS |
| 43 | Large page facts recovered | `EXP-005` row 4 | 0/1 | 0/1 | 0/1 | PASS |
| 44 | SPA shell facts recovered | `EXP-005` row 5 | 0/1 | 0/1 | 0/1 | PASS |
| 45 | MCP schema tokens total | `EXP-006/result.json` | 732 | 732 | 732 | PASS |
| 46 | MCP tools count | `EXP-006/result.json` | 4 | 4 | 4 | PASS |
| 47 | Mutation test cases count | `EXP-007b/result.json` | 4 | 4 | 4 | PASS |
| 48 | Mutation cases detected | `EXP-007b/result.json` | 4 | 4 | 4 | PASS |
| 49 | Mutation detection rate (%) | Wilson score (4/4) | 100.0% | 100.0% | 100.0% | PASS |
| 50 | Files scanned for secrets | `EXP-008/result.json` | 454 | 454 | 454 | PASS |
| 51 | Secret pattern tree hits | `EXP-008/result.json` | 3 | 3 | 3 | PASS |
| 52 | **Core benchmark items** | `benchmarks/eval_dataset.json` | **50** | **58** | **58** | **DISCREPANCY (FALSIFIED)** |

---

## 5. Tavily Credit Accounting Reconciliation

Verification of `reports/tavily-comparison/raw/usage_final.json`:
* **Campaign ID:** `stage7-20261028-a4a64151`
* **Account Usage Before:** `170`
* **Account Usage After:** `551`
* **Credits Consumed:** `381` (calculated: `551 - 170 = 381`, exact match)
* **Plan Limit:** `1000`, **Remaining:** `449` (`1000 - 551 = 449`)
* **Hard Stop Safety Threshold:** `200` (Safety condition satisfied: `449 >= 200`)
* **Key-Level vs Account-Level Discrepancy:** The endpoint reported Key Usage = `520` vs Account Usage = `551` (difference of 31 credits). The telemetry explicitly flags that the account-level usage is authoritative.
* **Master Report Alignment:** `MASTER-EVALUATION-REPORT.md` lists Tavily comparison systems (S2, S3, S4) as **NOT RUN** for the current evaluation pass due to absence of credit authorization in this session. The historical run files remain archived from the earlier campaign.

---

## 6. Forbidden Absolutist Language Audit

A full case-insensitive regex scan was executed across `reports/MASTER-EVALUATION-REPORT.md` for prohibited marketing or absolutist terms:

| Prohibited Term | Matches Found | Compliance Status |
|---|:---:|---|
| "certified" | 0 | PASS |
| "production ready" / "production-ready" | 0 | PASS |
| "zero vulnerabilities" | 0 | PASS |
| "fully secure" | 0 | PASS |
| "impenetrable" | 0 | PASS |
| "guaranteed" | 0 | PASS |
| "hallucination-free" | 0 | PASS |

The report adheres strictly to the required epistemic modesty rules.

---

## 7. Adversarial Findings & Falsification of Claims

### Finding 1: Core Benchmark Dataset Metadata Falsification (CRITICAL)
* **Claim:** Line 69 of `MASTER-EVALUATION-REPORT.md` asserts:
  `| benchmarks/eval_dataset.json | 58 | 442c7bfc90acc3aef89a22d17ebf24ec8a2b6e310ed10ceab32aa0df2ca9ccba | Frozen, English-only lookup set |`
* **Empirical Fact:**
  * `benchmarks/eval_dataset.json` contains exactly **50** items, not 58.
  * Its true SHA-256 hash is `846b4de9b38de945821ad56e5bd4fa2375af9640164b9e9c2de6bf8245e32df1`.
* **Root Cause:** In `evidence/prereg.md`, a completely different file—`weblens/benchmarks/queries.jsonl`—was recorded with 58 lines and hash `442c7bfc...`. The report generator `tools/build_report.py` (lines 158-159) hardcoded `58` and `"442c7bfc..."` into the manifest under the dataset name `benchmarks/eval_dataset.json`. The report's claim that *"No number is typed by hand"* is directly falsified.

### Finding 2: False Representation of Python Runtime Version (PROVENANCE DEFECT)
* **Claim:** Line 52 of `MASTER-EVALUATION-REPORT.md` claims:
  `WebLens version 0.1.0, loaded from weblens, on Python 3.13.15, pytest 9.1.1.`
  Manifest metric `subject.python` is recorded as `3.13.15`, citing evidence `EXP-000`.
* **Empirical Fact:**
  * In `evidence/raw/EXP-000/result.json` (line 108), the recorded executable environment is:
    `"python": "3.14.0 (main, Nov 19 2025, 22:43:52) [MSC v.1944 64 bit (AMD64)]"`.
  * In `evidence/ledger.jsonl`, every single run records `"python": "3.14.0"`.
* **Root Cause:** In `tools/build_report.py` line 153, the builder hardcodes:
  `m_map["subject.python"] = reg_val("subject.python", "3.13.15", ev=["EXP-000"])`.
  The evaluation was executed on Python 3.14.0, but falsely reported as Python 3.13.15.

### Finding 3: Phantom "Live Secret" Alert in `.env.example` Induced by Regex Bug (HIGH)
* **Claim:** Lines 27-31 and 185-188 warn of a critical finding requiring owner action:
  *".env.example contains a non-empty TAVILY_API_KEY value that is not tvly- shaped and is not a placeholder (False / False)... Rotate it if it is a live credential."*
* **Empirical Fact:**
  * Line 16 of `.env.example` is: `TAVILY_API_KEY=` (completely empty).
  * There was never a secret in `.env.example`.
* **Root Cause:** In `evidence/experiments/exp_08_secrets.py` line 71:
  `match = re.search(r"^TAVILY_API_KEY\s*=\s*(.*)$", text, re.M)`
  In Python regex, `\s` includes newline characters (`\n`). When `TAVILY_API_KEY=` had an empty value, `\s*` matched the trailing newline and consumed through to the beginning of the next line, capturing `"EXA_API_KEY="` into group 1. Because `"EXA_API_KEY="` is 12 characters, does not start with `tvly-`, and does not match the placeholder whitelist regex, the scanner reported a non-placeholder secret of length bucket `"1-20"`. The authors misinterpreted their own buggy scanner output as a security incident.

### Finding 4: Artificial Mutation Score Inflation (METHODOLOGICAL FLAW)
* **Claim:** Lines 171-172 claim:
  `4 of 4 mutations were detected (4/4 (100.0% [51.0%, 100.0%]))`
* **Empirical Fact:**
  * Inspecting `evidence/raw/EXP-007b/result.json` reveals the 4 evaluated cases:
    1. `clean_copy_verifies` (detail: `"problems=[]"`, detected: `true`)
    2. `ledger_record_tamper`
    3. `raw_artifact_tamper`
    4. `broken_build_ssrf_guard_off`
* **Defect:** Case 1 is the unmutated negative control, not a mutation. Including a control test that verifies the unmutated state as a "detected mutation" artificially inflates the mutation count from 3 to 4 and inflates the claimed detection rate.

### Finding 5: Extraction Latency Metric Skewed by 0.0 ms Non-Network Operations
* **Claim:** Line 147 reports:
  `Latency over fixture calls: 92.8 ms [15.8, 233.1] (n=14)`
* **Empirical Fact:**
  * In `evidence/raw/EXP-005/result.json`, rows 11, 12, and 13 (`budget_200`, `budget_500`, `budget_1200`) do not make HTTP requests; they are token slicing budget tests with latency `ms = 0.0`.
  * Row 0 (`static_article`) exhibited an extreme outlier latency of `974.567 ms`, while rows 1–10 took between 15.0 ms and 35.7 ms.
* **Defect:** Combining three zero-millisecond non-network tests into the denominator (n=14) artificially suppresses the mean latency from `118.1 ms` (across the 11 actual HTTP fixture calls) down to `92.8 ms`.

### Finding 6: Silent Suppression of the 245-Test Root Test Suite
* **Claim:** Line 85 claims:
  `The root tests/ suite and the root stack were not run, so no combined regression count is reported.`
* **Empirical Fact:**
  * The root test suite was executed at `2026-11-01 18:57`, as recorded in `evidence/raw/tests-root-suite/stdout.log`.
  * The output confirms: `245 passed in 203.69s (0:03:23)`.
  * Passing tests in the root suite explicitly verified SSRF redirect blocking (`test_redirect_to_private_blocked PASSED`) and headless browser fallback protection (`test_headless_browser_fallback_blocks_unsafe_url PASSED`).
* **Defect:** The report claims these capabilities and the root suite were "NOT RUN", discarding 245 validated passing tests from the evaluation record.

---

## 8. Recommendations for Release

1. **Fix `benchmarks/eval_dataset.json` Metadata:** Update `build_report.py` to calculate item counts and SHA-256 dynamically from the actual target dataset rather than hardcoding stale values from `queries.jsonl`.
2. **Correct Environment Reporting:** In `build_report.py`, derive `subject.python` dynamically from `sys.version` or `EXP-000` payload (`3.14.0`) rather than hardcoding `"3.13.15"`.
3. **Patch Regex in `exp_08_secrets.py`:** Replace `\s*=\s*(.*)$` with `[^\S\r\n]*=[^\S\r\n]*(.*)$` to prevent multi-line bleeding into subsequent environment variable names, and rescind the false security advisory regarding `.env.example`.
4. **Segregate Controls from Mutation Counts:** In `EXP-007b`, report mutation score as `3/3 (100%)` with the clean control reported as a separate validation gate.
5. **Sanitize Latency Metric Samples:** Separate pure string budget slicing tests from HTTP fixture extraction latencies in `EXP-005`.
6. **Make Linter Read-Only Capable:** Modify `tools/lint_report.py` and `tools/build_report.py` to support an in-memory verification mode (`--dry-run` or checking byte equality without attempting disk writes).
7. **Re-synchronize Report with Ledger Head:** Rebuild `reports/MASTER-EVALUATION-REPORT.md` and `evidence/manifest.json` against the latest ledger head before final sign-off.
