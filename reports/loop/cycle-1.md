# Cycle 1 — measure, fix, verify

Generated from `evidence/` (hash-chained ledger). Every number below is tagged with
the ledger evidence id that produced it; nothing here was typed from memory.

## Headline

**Nothing was kept this cycle. One candidate was implemented, measured, and
rejected for violating the pre-registered quality guard.**

That is the correct outcome under the rules, not a failure: the prompt's own stop
rule says "a cycle that keeps nothing is a valid result". The candidate made the
product notably faster and measurably worse at the same time, so shipping it
would have been exactly the kind of fake progress the charter forbids.

## Pre-registered gates (fixed before any data was observed)

From `evidence/prereg.md`:

| Gate | Threshold | Measured (shipped code) | Status |
|---|---|---|---|
| search p50 | ≤ 1500 ms | **739 ms** | PASS |
| search p95 | ≤ 5000 ms | **2062 ms** | PASS |

`n = 40` live queries, shuffled with a fixed seed, 0 empty results, all `status=ok`.
Evidence: `cycle1-final-latency-v2`.

Both gates were **already passing on the shipped code**. Cycle 1 therefore did not
inherit a failing gate — an assumption in the previous session's summary that this
cycle disproved by measurement.

## What was tested (D1–D4 carry-overs from the loop prompt)

- **D1 reconcile.** The ledger-recorded commit `f3401c7` is an ancestor of HEAD
  (`4c99e93`), 16 commits behind. No divergence: no code change contradicts a
  ledger decision.
- **D2 noise floor.** The shipped `tools/calibrate_noise_floor.py` measures the
  *chunker* path (0.079 ms), which is not the path any latency claim is about.
  A/A on the real search path: paired `n=36`, mean difference −112 ms, sd 444 ms,
  median −35 ms. Evidence: `evidence/raw/aa_search_noise.json`. Latency claims in
  this cycle are read against that noise band, not the 0.079 ms figure.
- **D3/D4 fixture discipline.** The one new test file written this cycle carried a
  fixture bug (two fake providers returning identical URLs, so a "collected both"
  assertion saw 2 instead of 4). The fixture was fixed, not the assertion.
- **Gate 1 (mutation).** The first version of the candidate had **no test
  coverage**: mutating its early-stop to `if False:` left the whole suite green.
  A regression test was written and verified to **fail** on the mutant and pass on
  the good build before the measurement proceeded.

## The rejected candidate

**Bounded provider fuse (early stop).** Shipped code awaits `asyncio.gather` over
every provider, so one slow keyless engine sets the latency for every query.
The candidate stopped waiting once `k` distinct URLs had arrived.

| Metric | Δ (bounded − shipped) | CI95 | Guard |
|---|---|---|---|
| P@5 | **−0.070** | [−0.108, −0.035] | **VIOLATED** (limit −0.02) |
| nDCG@5 | −0.073 | [−0.113, −0.038] | worse |
| latency | −1013 ms | [−1332, −781] | faster |

Paired, interleaved on identical queries, `n = 80`. Evidence: `cycle1-paired-fuse-quality`.

The latency win was **bought with relevance**: stopping early returns before the
slower providers can contribute, and those providers were contributing relevant URLs.

### The confound that nearly produced a false KEEP

An unpaired comparison of the same change looked like a large win
(p50 1515 → 664 ms, one run each). But identical *unmodified* code scored
P@5 **0.575, 0.500, 0.485** on three consecutive runs of the same split — search
index drift is bigger than most effects this loop would chase. A single unpaired
run would have declared a win. Only the interleaved paired test separated the real
relevance loss from the noise.

This is recorded in `evidence/rejected/cycle1-bounded-fuse.json` (status REJECTED,
evidence ids attached).

## State of the product

- `weblens/tests`: **770 tests, 0 failures, 0 errors, 1 skipped** (exit 0).
- `tests/` (root stack): **366 tests, 0 failures, 0 errors, 5 skipped** (exit 0).
  The 5 skips are Playwright browser launches blocked by this machine's sandbox
  (`EPERM: mkdtemp`), reported as skips, not passes.
- Canonical tree and `src/weblens` mirror: **byte-identical** (drift guard).
- Ledger: **55 entries, hash chain PASS**, head `4418f1cc2622e9708a238dfa26e89f692c908ac0637528d67c9acfc3df6a7d52`.
- Gates mypy / bandit / ruff / format: clean on the changed files.

## NOT RUN — and why (no substitute claims are made)

| Item | Why not run |
|---|---|
| Tavily head-to-head this cycle | Not needed to reach a decision; credits preserved. Quota checked before spending: plan "Researcher", 1000 credits, 0 used. |
| SearXNG arm (S1) | Not running at `localhost:8080`; enabling it needs your approval to change its config. |
| Docker/WSL2 isolated pen-test environment | Docker daemon present (29.9.2) but no isolated attack container was built this cycle; no attack/fuzz work was performed, so none is claimed. |
| Tier A/B/C/D datasets (10k / 2k / 3k / 5k items) | Dataset holds **107** usable labelled queries (52 dev, 55 heldout). Claims are scoped to n=40 subsets and say so. |
| Gemini comparison (G0–G4) | `GEMINI_API_KEY` is present in `.env` but no Gemini arm was run this cycle; no Gemini number is reported. |
| Private git remote checkpoints | No remote configured; ledger head is printed locally instead. |
| Human review of sampled judgements | Not performed; all relevance labels are mechanically derived from the dataset's `acceptable_sources`. |

## Honest limitations

- n=40 per split, one machine, one network, one day. Search-index drift moves P@5
  by ±0.05 between runs of identical code, which is larger than several effects a
  loop like this would chase; only paired designs are trustworthy here.
- The held-out split has now been looked at once under this cycle's rules. Per the
  single-use rule it becomes dev data; the next scored decision needs fresh items.
- My earlier "both gates PASS" claim was right, but only after measuring: before
  this cycle the p50 gate status was unknown, not passing.
