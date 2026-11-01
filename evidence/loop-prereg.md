# Loop pre-registration (v7)

Written before cycle 1. Deviations must be logged in `evidence/cycles/<n>/deviations.md`.

## Budgets

- Maximum cycles: 10.
- This session: zero Tavily credits; wall-clock budget 2 hours; no browser.
- Any Tavily run requires explicit owner authorization. Until then every Tavily
  comparison is NOT RUN.

## Priority order (owner)

1. No fake accuracy.
2. Answer accuracy.
3. Security.
4. Tokens.
5. Latency.
6. Cost.

## Improvement rule (mechanical)

A change is KEPT only if, on a fresh held-out slice:

(a) the target metric's paired difference has a 95% interval excluding zero in the
good direction, AND every guarded metric is within margin:

- answer-support difference no worse than -2 percentage points;
- false-confidence no more than +1 point;
- p95 latency no more than +10%;
- tokens per call no more than +5%;
- any security-test regression is an automatic reject;

OR

(b) it is a pure efficiency win with quality non-inferior on the same queries.

A rule is applied by `tools/v7_decide.py`; judgement does not override it.

## Stop rules

Stop when any holds: 10 cycles; two consecutive cycles with no kept change; the
time/credit budget is exhausted; an unfixable hard fail; the owner says stop.

## Ratchet

After a kept change the new numbers become the baseline. Gates are never loosened.

## Held-out policy

- Every cycle uses a held-out slice hashed before the code change and never used
  for development.
- The reserve slice is touched only at cycles 5 and 10.
- Each held-out set records how many times it has been evaluated.
- A leakage audit greps source, prompts, caches and fixtures for held-out tokens.

## Scope of this session

Feasible: extraction/passage-selection changes on local fixtures, package tests,
SSRF/cache/injection regression checks, deterministic reports.

Not feasible without authorization or missing tooling: Tavily, live search,
browser, SearXNG, the root stack, large corpora, independent audit, human review.

The nine mandated applications are NOT STARTED in this session. Their status is
NOT RUN, not SHIPPED. No scaffolding is added because an unverified endpoint would
be a fake feature under the directive.

## Complexity budget

MCP schema measured in this pass: 732 cl100k tokens over 4 tools (EXP-006). Budget:
1000 tokens. Any new tool must fit inside the remaining budget or replace an
existing one.

## Cycle 1 target

Measured loss: unqueried extraction of a long page returns only the first four
chunks (EXP-005, large page 0/1 tail fact; reproduced at offsets 0-3743 of a
15933-character document). Hypothesis: selecting evenly spaced chunks, including
the last, fixes tail-fact reachability without changing query-focused selection.

Held-out: 30 freshly generated long pages with unique head and tail markers,
hashed before the baseline run. Target: tail-fact recall. Guard: head-fact recall,
tokens per call, extraction latency, package tests, SSRF matrix.
