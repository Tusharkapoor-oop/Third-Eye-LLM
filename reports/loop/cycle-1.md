# Loop cycle 1

Verdict: **REJECT**. Action: **REVERTED**.

## Target

Unqueried extraction of long pages, tail-fact reachability.

- Before: `0/30` pages found the tail marker.
- After: `30/30` pages found the tail marker.
- Paired difference: `1.000` [95% CI `1.000`, `1.000`].
- McNemar exact p: `1.86e-09`.

## Guards

- `head_not_worse`: `True`
- `tokens_within_5pct`: `True`
- `p95_latency_within_10pct`: `False`
- `fixture_recall_not_worse_2pp`: `True`
- `tests_ok`: `False`
- `ssrf_ok`: `True`

## Why it was not kept

Failed guards: `p95_latency_within_10pct, tests_ok`.

The target effect is real on the held-out set, but the pre-registered rule also
requires the guarded metrics to hold. p95 extraction latency rose from
`56.8 ms` to `75.7 ms` on separate runs, which exceeds the
allowed ten percent. The two candidate test failures were caused by a test
fixture with a trailing sentence below the documented chunk minimum; they are
not a product pass, and they are not hidden.

The candidate patch is preserved at `evidence/cycles/1/rejected.patch`; the
working tree was reverted. The experiment remains in the ledger.

## Measured context

- Tokens per call: `989.8` before, `941.8` after.
- Fixture extraction recall: `0.765` before, `0.824` after.
- Post-revert tests: `162` passed, `0` failed, `1` skipped.
- SSRF matrix: `32` attempts, all blocked: `True`.

## Scope

Held-out pages are synthetic (SIMULATED), n=30. Not live-web evidence. No Tavily
comparison was run. The change is not shipped, so the loss remains.
