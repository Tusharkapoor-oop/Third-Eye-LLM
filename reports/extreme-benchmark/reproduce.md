# Extreme-Scale Equivalent — Reproduce

This directory is a feasibility/equivalence report, not a 10,000-query run. Reproduce the 108-query campaign with:

```powershell
cd "C:\Users\ACER\Downloads\Broswer for ai agnets\weblens"
uv run python -m benchmarks.stage7_run --phase search --split dev
uv run python -m benchmarks.stage7_run --phase research --split dev
uv run python -m benchmarks.stage7_run --phase search --split test
uv run python -m benchmarks.stage7_run --phase research --split test
uv run python -m benchmarks.stage7_analyze
uv run python -m benchmarks.stage7_security
```

The full command sequence, dataset hash verification, secret-scan check, and paid-call caveat are in:

`../tavily-comparison/REPRODUCE.md`

## Verify the excluded 10,000-row corpus

```powershell
cd "C:\Users\ACER\Downloads\Broswer for ai agnets"
Get-FileHash reports\_archive\prior-run-20261027\extreme-benchmark\datasets\extreme_benchmark_10k.jsonl -Algorithm SHA256
```

Expected whole-file hash:

```text
d1d91fe1e7289affb0a85a0a412c6a9d47dbbde2ea5e994566dcd2aa1ba1c5ba
```

The hash matching is not sufficient. Run the audit in `01-dataset-audit.md` to confirm 5,528 unique query texts, 10,000 placeholder claims, 350 generated-token rows, 2 domain sets, and mismatched partition hashes.

## Do not

- Do not run 10,000 paid queries on the strength of this report.
- Do not treat the synthetic corpus as ground truth.
- Do not describe this as a 10,000-query benchmark.
- Do not publish an unconditional release claim.

## Evidence

- `../tavily-comparison/raw/`
- `../tavily-comparison/data/analysis.json`
- `../tavily-comparison/SECURITY-RESULTS.json`
- `../_archive/prior-run-20261027/` (historical, not evidence)
