# Reproducibility Guide: WebLens vs Tavily Extreme-Scale Evaluation

**Document ID:** `reports/extreme-benchmark/reproduce.md`  
**Execution Date:** 2026-10-27  
**Operating System:** Windows 11 x64 / PowerShell 7+  

---

## 1. Prerequisites and Environment Setup

Ensure Python 3.11+ and Node 20+ are installed:
```powershell
# Verify runtimes
python --version   # Must be >= 3.11 (tested on Python 3.13.15)
node --version     # Must be >= 20.0 (tested on Node 24.19.0)
```

Activate the project virtual environment:
```powershell
# Navigate to repository root
cd "c:\Users\ACER\Downloads\Broswer for ai agnets"

# Activate venv
.\.venv\Scripts\Activate.ps1
```

---

## 2. Step-by-Step Reproduction Commands

### Step 1: Run Full Automated Regression Test Matrix (397 Tests)
```powershell
# Run primary WebIntel engine tests (237 tests)
pytest tests/ -v

# Run WebLens package tests (160 tests)
pytest weblens/tests/ -q
```
*Expected Outcome:* `237 passed` on root suite, `160 passed` on weblens suite. Total 397 passing tests, 0 failures.

---

### Step 2: Execute Hostile Security Red-Team Test Suite (59 Vectors)
```powershell
# Executes SSRF penetration, prompt injection sanitization, cache boundaries, and browser egress
python scripts/run_security_redteam.py
```
*Expected Outcome:* 57 tests PASS, 2 vulnerabilities recorded (SEC-01 and SEC-02) logged to `reports/extreme-benchmark/results/security-test-results.jsonl`.

---

### Step 3: Verify the 10,000 Query Dataset Catalog & Manifest Hashes
```powershell
# Inspect dataset manifest and integrity
python -c "import json; m = json.load(open('reports/extreme-benchmark/datasets/manifest.json')); print(f'Catalog: {m[\"total_unique_queries\"]} queries across {m[\"category_count\"]} categories; SHA256: {m[\"dataset_sha256\"]}')"
```
*Expected Outcome:* `Catalog: 10000 queries across 40 categories; SHA256: d1d91fe1e7289affb0a85a0a412c6a9d47dbbde2ea5e994566dcd2aa1ba1c5ba`.

---

### Step 4: Run Live Head-to-Head Pilot Evaluation
```powershell
# Runs paired live queries across Tavily Direct, WebLens Keyless, and WebLens Router
python scripts/run_live_pilot.py
```
*Expected Outcome:* Produces monotonic timing and token metrics in `reports/extreme-benchmark/results/pilot_live_results.json`.

---

### Step 5: Regenerate Benchmark Results & Evidence Summaries
```powershell
# Aggregates evaluated query instances into per-query JSONL and summary JSON
python scripts/build_results_summary.py
```
*Expected Outcome:* Ingests 429 evaluated query instances and writes `summary.json` with token reduction ratios.

---

### Step 6: Validate Cryptographic Artifact Integrity
```powershell
# Computes and verifies SHA-256 hashes across all audit deliverables
python scripts/verify_artifact_integrity.py
```
*Expected Outcome:* Matches `reports/extreme-benchmark/results/artifact-integrity.json` with zero hash mismatches.
