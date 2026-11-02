# WebLens Quality Loop — Next Action (2026-11-02)

## Current blocker

The frozen F1-F17 registry is not satisfied. The supplied V9B artifacts are a
single 100-row search benchmark; the dataset contains 200 rows. Tavily direct
currently returns HTTP 401, and no `BUDGET_CAP` was supplied, so this loop spent
zero Tavily credits.

## Resume command

```powershell
.venv\Scripts\python.exe evidence\quality_loop\derive_quality_fields.py
```

## Required next measurement

1. Set an authorized Tavily credential without printing it and record an explicit
   `BUDGET_CAP` before any external calls.
2. Run F2 first: the same 100-item slice, real MCP-backed local/deployed
   adapters, per-item answer/citation evidence, cold and warm runs, and rotated
   execution order.
3. Make only one retrieval/routing change after recording the F2 baseline.
4. Run regression and security checks; keep only a change that preserves every
   hard gate and is reproduced in a second independent run.

Do not deploy, rewrite the dataset, or treat the historical aggregate reports as
PASS-100 evidence.
