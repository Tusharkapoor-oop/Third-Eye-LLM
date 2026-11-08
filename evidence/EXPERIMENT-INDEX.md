# WebLens Experiment Index (V7 Continuation)

## Ledger Head
- **Current HEAD:** `ccafa81`
- **Best-Known-Good Commit:** `902415d49f8da502b9de0e1c78da7f5777a1d2f8`
- **Last Verified Test Run:** 2026-11-08T09:15Z

## Recent Experiments

### V7-Reconciliation
| ID | Timestamp | Commit | Command | Result | Evidence |
|---|---|---|---|---|---|
| V7-RECON-001 | 2026-11-08T14:14Z+0530 | ccafa81 | `git log --oneline -20` | Confirmed HEAD is `ccafa81` and baseline is `902415d` | Git output |
| V7-RECON-002 | 2026-11-08T14:18Z+0530 | ccafa81 | `git diff 902415d HEAD -- src/weblens/extract/passages.py | Select-String "spread_chunks"` | Confirmed `spread_chunks` was added after baseline | Git diff |
| V7-RECON-003 | 2026-11-08T14:20Z+0530 | ccafa81 | Read `evidence/cycles/1/decision.json` | Cycle 1 formally REJECTED and REVERTED | Decision record |
| V7-RECON-004 | 2026-11-08T14:24Z+0530 | ccafa81 | Hash `src/weblens/extract/passages.py` and `weblens/src/weblens/extract/passages.py` | Files identical; SHA-256 `3E1857A560902FEE547064B523557F01300D6934EFC53BC242B8CC7DBE9C8753` | File hash |

### V7-Verification
| ID | Timestamp | Commit | Command | Result | Evidence |
|---|---|---|---|---|---|
| V7-TEST-001 | 2026-11-08T14:46Z+0530 | ccafa81 | `pytest weblens/tests/test_apps.py -v` | 12 passed in 11.77s | Console output |
| V7-TEST-002 | 2026-11-08T14:49Z+0530 | ccafa81 | `pytest weblens/tests/ -v` | 397 passed in 94.97s | Console output |
| V7-PERF-001 | 2026-11-08T14:52Z+0530 | ccafa81 | Micro-benchmark `select_passages(text=None, max_passages=5)` on 200-sentence synthetic text | 4 passages returned, latency 32.354 ms, tail hit True | Console output |
| V7-PERF-002 | 2026-11-08T14:53Z+0530 | ccafa81 | `pytest weblens/tests/test_passages.py -v` | 14 passed in 3.88s | Console output |

## Status
- The live implementation of `spread_chunks` passes all existing unit tests.
- The micro-benchmark latency (32.35 ms) is well below the Cycle 1 rejection threshold of +10% on a 56.79 ms baseline (i.e., >62.47 ms would fail).
- However, the original Cycle 1 formal decision remains `REJECT`: the current code is an independent reimplementation, not a re-evaluation of Cycle 1.
- Next stage: restore full root test suite (`tests/`) and security regression suite under the same environment.
