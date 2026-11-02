# Quality Loop Report — 2026-11-02

## Per-field verdicts

| Field | Baseline evidence | Item pass count | Two-run reproduction | Verdict |
|---|---|---:|---|---|
| F1 | V9B local search | 88/90 | No | OPEN-REMEDIATION |
| F2 | V9B 73/90; corrected rerun 51/90 | 51/90 corrected rerun | No | FAIL / REJECTED CYCLE |
| F3 | No answer/claim artifact | UNSUPPORTED | No | UNSUPPORTED |
| F4 | V9B local traps | 4/10 | No | FAIL |
| F5 | No extraction battery | UNSUPPORTED | No | UNSUPPORTED |
| F6 | No code/table/noise battery | UNSUPPORTED | No | UNSUPPORTED |
| F7 | No PDF/offline battery | UNSUPPORTED | No | UNSUPPORTED |
| F8 | No BM25/hybrid/RRF rollup | UNSUPPORTED | No | UNSUPPORTED |
| F9 | No per-hop research artifact | UNSUPPORTED | No | UNSUPPORTED |
| F10 | No claim citation log | UNSUPPORTED | No | UNSUPPORTED |
| F11 | V9B local latency | 99/100 | No | FAIL |
| F12 | V9B local tokens | 100/100 | No | OPEN-REMEDIATION |
| F13 | No sustained QPM windows | UNSUPPORTED | No | UNSUPPORTED |
| F14 | V9B local credits | 100/100 | No | OPEN-REMEDIATION |
| F15 | V9B local status | 100/100 | No | OPEN-REMEDIATION |
| F16 | Partial security campaign | Not item-complete | No | OPEN-REMEDIATION |
| F17 | Regression capture includes skip | Not item-complete | No | OPEN-REMEDIATION |

## Evidence map

- Per-item verdicts: `evidence/raw/quality-loop-20261102/field_verdicts.jsonl`
- Hashes and provenance: `evidence/raw/quality-loop-20261102/metadata.json`
- State: `evidence/loop-state.json`
- Gap ledger: `GAP-LEDGER.md`
- Baseline raw: `reports/three-system-comparison/raw-v9b-2026-11-02/three_system_results.jsonl`
- Regression/security captures: `evidence/raw/quality-loop-20261102/`

## Blockers

1. Tavily credential currently returns HTTP 401.
2. `BUDGET_CAP` was not provided; this loop spent zero Tavily credits.
3. Search-only V9B data cannot prove F3, F5-F10, or F13.
4. The 100,000-query target is not met; 200 dataset rows exist, 100 baseline rows were measured.
5. Deployed unauthenticated MCP capability discovery is a separate security failure.

## Resume

```powershell
.venv\Scripts\python.exe evidence\quality_loop\derive_quality_fields.py
```

Next field: F2, after an authorized credential and explicit budget cap are supplied.
