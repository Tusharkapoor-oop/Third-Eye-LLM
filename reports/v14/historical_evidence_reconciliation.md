# Historical Evidence Reconciliation

## Sources inspected

- `reports/MASTER-EVALUATION-REPORT.md`
- `reports/WITHDRAWN.md`
- `reports/_withdrawn/`
- `reports/loop/`
- `evidence/loop-state.json`
- `arena_report.json`
- Git history through `f3401c7`

## Findings

The repository itself records that several earlier reports were withdrawn for
unsupported counts, missing raw judgments, contradictory benchmark values,
unverified conformance claims, and a nonexistent 10k dataset. Those withdrawn
documents must not be used as release evidence.

The current README and recent commits describe later V10/V11 and Quality Arena
results, but they concern different stacks and configurations. The detailed
master report explicitly says its subject was the `weblens/` package and notes
that `src/weblens` is a second copy. Therefore historical metrics cannot be
transferred automatically to the root V14 server.

The current `arena_report.json` is a separate root-stack experiment. It has
live Tavily rows when `BUDGET_CAP` is explicitly enabled, but Gemini is blocked
in the current environment. Its deterministic rubric is not equivalent to the
100/200-query F2 benchmark scorer.

## Reconciliation decision

| Claim class | Status |
|---|---|
| Withdrawn V6 “fully certified” claims | **REJECTED / NOT EVIDENCE** |
| Historical fixture test results | **VERIFIED ONLY FOR THEIR FIXTURE RUNS** |
| Historical `weblens/` package test counts | **UNVERIFIED FOR ROOT V14** |
| Historical 3/4-system benchmark results | **PARTIALLY VERIFIED, CONFIGURATION-SCOPED** |
| Current root arena result | **PARTIALLY VERIFIED, LIVE AND VARIABLE** |
| Gemini comparison in current environment | **BLOCKED** |

No historical number is promoted to a V14 release gate without reproducing its
inputs, scorer, stack, and raw artifacts.
