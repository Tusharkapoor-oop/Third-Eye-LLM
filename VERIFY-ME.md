# VERIFY-ME.md: Independent Owner Verification Guide

This document enables the repository owner to independently verify the integrity of the evaluation, hash chain, application suite, and reports without running the coding agent.

---

## 1. Fast Cryptographic & Provenance Verification

Run the following two commands from the repository root:

```bash
# 1. Verify cryptographic hash chain and all artifact SHA-256 hashes
.\.venv\Scripts\python.exe tools/verify_evidence.py

# 2. Verify numeric traceability, Wilson intervals, and absence of forbidden words
.\.venv\Scripts\python.exe tools/lint_report.py
```

**Expected output:**
```text
runs: 41
classes: {'MOCK': 4, 'SIMULATED': 19, 'REAL': 18}
head: 271bc8c3cc6b5b4ff81d80f86511f6106a3ee5f61818bc36a5716c5825125a53
PASS evidence chain and artifact hashes
PASS build_report: rendered 13315 bytes, 68 metrics
PASS lint: 68 metrics traceable, chain verified, report reproducible
```
**Expected runtime:** < 3 seconds.

---

## 2. Dataset Cryptographic Integrity Check

Verify that reference datasets match the exact pre-registered SHA-256 digests:

```powershell
Get-FileHash weblens/benchmarks/queries.jsonl -Algorithm SHA256
Get-FileHash benchmarks/eval_dataset.json -Algorithm SHA256
Get-FileHash benchmarks/eval_dataset_expanded.json -Algorithm SHA256
Get-FileHash reports/tavily-comparison/data/stage7_dataset.jsonl -Algorithm SHA256
```

**Expected digests:**
| File | Expected SHA-256 |
|---|---|
| `weblens/benchmarks/queries.jsonl` | `442c7bfc90acc3aef89a22d17ebf24ec8a2b6e310ed10ceab32aa0df2ca9ccba` |
| `benchmarks/eval_dataset.json` | `846b4de9b38de945821ad56e5bd4fa2375af9640164b9e9c2de6bf8245e32df1` |
| `benchmarks/eval_dataset_expanded.json` | `6130548dacb595da44a0973e66c4e3a44836846baf16a97ef1ca87664f2d065f` |
| `reports/tavily-comparison/data/stage7_dataset.jsonl` | `a4a64151fbdbda850a9de128bb7f83ec67f126b633aac42488c6f0b9296a9b21` |

---

## 3. Byte-Identical Report Rebuild & Diff Check

Confirm that running the deterministic report builder produces a byte-identical markdown report:

```bash
.\.venv\Scripts\python.exe tools/build_report.py
git diff reports/MASTER-EVALUATION-REPORT.md
```

**Expected output:** Zero diff lines (clean exit).

---

## 4. Run Mandated Applications & Penetration Tests

Execute the full suite of application and security regression tests:

```bash
# Mandated applications test suite (Crawl2RAG, DeepResearch, Company, Chat, Market, Sheets, Meeting)
.\.venv\Scripts\python.exe -m pytest weblens/tests/test_apps.py -v

# Gate 1 tamper and mutation verification
.\.venv\Scripts\python.exe -m pytest tests/test_gate1_tamper_mutation.py -v

# Canary secret redaction verification
.\.venv\Scripts\python.exe -m pytest tests/test_p9_canary_secrets.py -v

# Full package test suite
.\.venv\Scripts\python.exe -m pytest weblens/tests -q
```

**Expected output:** 100% PASS across all tests (172 passed, 1 skipped).

---

## 5. Verify MCP Tool Profile Token Budgets

Measure the schema token footprint of all MCP profiles (`core`, `research`, `full`):

```bash
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'weblens/src'); from weblens import cli; cli.main(['tokens', '--pretty'])"
```

**Expected output:**
- `core` profile: 4 tools, **838 tokens** (within $\le 1,000$ budget).
- `research` profile: 6 tools, 1,043 tokens.
- `full` profile: 8 tools, 1,314 tokens.

---

## 6. Execute Runnable WebLens 101 Tutorial

Run the end-to-end tutorial script demonstrating the live Python API:

```bash
$env:PYTHONPATH="weblens/src"
.\.venv\Scripts\python.exe weblens/examples/tutorial_101.py
```

**Expected output:**
Clean execution from `[1] Checking System Health...` to `=== WebLens 101 Tutorial Complete ===`.

---

## 7. Ledger Head Hash Checkpoint
The verified head of `evidence/ledger.jsonl` is:
`271bc8c3cc6b5b4ff81d80f86511f6106a3ee5f61818bc36a5716c5825125a53`
