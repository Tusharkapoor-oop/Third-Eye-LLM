# Cycle 2 — verify the concurrent writer's changes, close the integrity debt

Generated from `evidence/` (hash-chained ledger). Numbers carry the evidence id
that produced them.

## Headline

Three things completed this cycle, none of them "shipping a feature":

1. **The integrity tooling now passes honestly.** `build_report.py` and
   `lint_report.py` both PASS, after the linter was repaired to understand the
   three ledger schema generations instead of crashing on them.
2. **Gate 1 is real.** 3/3 deliberately broken builds are now caught by the
   suite (SSRF, injection scanner, token ceiling). Before this cycle the
   mutation gate did not exist.
3. **A concurrent writer's changes were measured, not trusted.** Their
   quality-guarded early stop and Stack Exchange supplement are quality-safe but
   currently **inert** — neither ever fires at the shipped defaults.

## Integrity tooling: from crash to PASS

`tools/lint_report.py` crashed with `KeyError: 'id'`, then `KeyError: 'duration_s'`.
It now normalises the three schema generations the inherited chain actually
contains — current (`id`/`started_utc`/`duration_s`), legacy A (`experiment`
instead of `id`), and legacy B (single `utc` stamp, no duration) — and only
flags a record it cannot identify at all.

The ledger was **not edited**. It verifies, so rewriting a record would have
broken the chain. The linter was taught the historical formats instead.

| Gate | Result |
|---|---|
| `build_report.py` | PASS — 13315 bytes, 68 metrics |
| `lint_report.py` | PASS — 68 metrics traceable, chain verified, report reproducible |
| `verify_chain.py` | PASS — 60 entries, head `255a5150c19f…` |

## Gate 1 mutation testing (new)

`tools/gate1_mutation.py` mutates a protection, runs the tests that should
defend it, and reports CAUGHT / SURVIVED.

| Mutant | Result |
|---|---|
| SSRF: metadata + private IP blocklist emptied | **CAUGHT** |
| Injection: `scan_injection` returns `[]` | **CAUGHT** |
| Token: ceiling `min(maximum, requested)` removed | **CAUGHT** |

**3/3 caught, 0 survived.** Two of the three mutants only became valid after
correction: the first SSRF/injection mutant anchored on text that did not exist
(`scan_injection_patterns`, a test file that was never there), and the first
token mutant hit a docstring rather than the clamp. A mutant that does not
actually break the behaviour proves nothing, so both were rewritten against the
real enforcement points.

## D2 noise floor: the right path, finally

`tools/calibrate_noise_floor.py` measured the local chunker (**0.079 ms**) and
that figure was being used to bound search-latency claims it could not describe.
It now has `--path search`, an A/A calibration of the real search path:

| Metric | Value |
|---|---|
| n pairs | 36 |
| median paired diff | **−145.5 ms** |
| sd | **759.9 ms** |
| p95 paired diff | +424.6 ms |

Evidence: `evidence/loop/NOISE_FLOOR_SEARCH.json`. A single-run latency claim
smaller than ~150 ms on this machine is noise. This is exactly why cycle 1's
unpaired "p50 1515 → 664 ms" was misleading and why the paired test reversed it.

## The concurrent writer's changes, measured

Two features landed from another writer during this work. Both were tested
rather than accepted.

### Quality-guarded early stop

Their guard is stricter than cycle 1's rejected candidate: it stops early only
when the pool holds **k+2 distinct URLs across ≥3 registrable domains** inside a
2 s soft deadline.

| Metric | Δ (default − wait-all) | CI95 |
|---|---|---|
| P@5 | +0.0075 | [−0.0125, +0.0275] |
| nDCG@5 | +0.0046 | [−0.0088, +0.0192] |
| latency | −56.9 ms | [−203.0, +66.8] |

Paired, n=80. Evidence: `cycle2-early-stop-quality`.

**Quality guard HELD** — so unlike cycle 1's candidate, this one does not harm
relevance.

> **CORRECTION (later re-analysis).** This section originally concluded the early
> stop was *inert* (`early_stop_fired = 0/80`, no latency gain). That was wrong.
> It rested on an 80-pair run where the guard genuinely did not fire, but a larger
> 4-pair experiment (`evidence/raw/R-20261109-AB5-*`, 4 rounds × 40 queries) shows
> the guard fires on **81 of 160** queries and cuts p50 by **~1.4 s** with P@5
> flat. Paired n=160: P@5 −0.0038 [−0.0175, +0.0100] (guard HELD), latency
> **−1436 ms** [−1568, −1305]. Verdict corrected to **KEPT**. Full record:
> `evidence/raw/cycle3_early_stop_paired.json`.
>
> The lesson is recorded rather than hidden: an "it never fires" conclusion drawn
> from one 80-pair sample was a false negative, and the fix was more data, not a
> looser guard.

### Stack Exchange supplement provider

Direct call works and returns real results (5 hits for "python asyncio tutorial",
all stackoverflow.com). But the supplement pass only runs when the primary pool
is **short of k**, which did not happen in any measured query — so no
`supplement:` warning fired and no supplement URL entered any result set. Verified
inert at defaults.

### Measurement-integrity flag: `auto_include_tavily`

`auto_include_tavily: bool = True` silently prepends Tavily to the provider chain
whenever a Tavily key is configured, even if `search_providers` does not name it.
Verified: with a key the chain becomes `['tavily', 'mwmbl', 'wikipedia', 'bing',
'yahoo']`.

This is defensible as a product default, but it is a trap for benchmarks: a
"keyless" WebLens arm would silently become a Tavily-backed arm. The v11 harness
is already safe because it pins `tavily_api_key=None`. Any future measurement
must do the same, and that requirement is now recorded rather than assumed.

## Verified state

| Gate | Result |
|---|---|
| weblens suite | **787 tests, 0 failures, 0 errors, 1 skipped** |
| root suite | **366 tests, 0 failures, 0 errors, 5 skipped** (361 passed) |
| coverage | **90.91%** (gate 90) |
| mypy | **Success: no issues found in 55 source files** |
| bandit `-ll` | exit 0, 0 medium+ |
| ruff check (`src tests benchmarks`) | **All checks passed** |
| ruff format --check | **127 files already formatted** |
| canonical/mirror drift | **none** (synced 1 file, then guard passes) |

`ruff format --check` was **failing on 3 files** (the concurrent writer's
`router.py`, `test_search_router.py`, `test_stackexchange.py`) — a real CI break.
Formatted; the CI gate is now green.

## NOT RUN — no substitute claims are made

| Item | Why not run |
|---|---|
| Tavily head-to-head | No decision required it; 0 credits spent. Quota before spend: plan "Researcher", 1000 credits, 0 used. |
| SearXNG arm | Not running at `localhost:8080`; enabling needs your approval. |
| Isolated Docker pen-test container | Daemon present (29.9.2); no attack/fuzz work performed, so none claimed. |
| Tier A/B/C/D large datasets | Dataset holds **107** usable labelled queries. Claims scoped to n=40 subsets. |
| Gemini arms (G0–G4) | Key present, no Gemini run this cycle, no Gemini number reported. |
| Private git remote checkpoints | No remote configured. |
| Human review of judgements | Not performed; labels are mechanically derived from `acceptable_sources`. |

## Honest limitations

- The early-stop and supplement conclusions are about **this provider set on this
  network**; a chain whose primary pool is frequently thin would exercise them.
- Held-out split has been looked at twice now across cycles. Under the
  single-use rule it is spent; the next scored decision needs fresh items.
- Cycle 1's rejected candidate and cycle 2's shipped guard differ only in
  strictness — which is the entire point: the guard's extra depth and domain
  requirements are what turn a quality-destroying shortcut into a safe-but-idle
  one.
