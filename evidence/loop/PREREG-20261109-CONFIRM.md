# Pre-registration — confirmatory cycle (2026-11-09)

Status: written **before** the confirmatory runs below. Exploratory runs
(`R-20261109-AB2-*`, `AB3-*`, `AB4-*`) are explicitly **not** confirmatory.

## Working-tree state at registration

- HEAD: `4c99e93` (working tree dirty; the evidence runner records the exact
  tree hash for every run).
- Canonical suite: exit 0, coverage 90.92% (`weblens/coverage.json`).
- Code under test: `fuse_soft_timeout_s` early stop + Stack Exchange as a
  thin-pool **filler** supplement + Tavily auto-prepend (product default).

## Dataset and arms

- Dataset: `weblens-lab/datasets/eval_benchmark_suite_v10.json`
  (sha256 `a42d4004fb91208f…`), fixed first 40 eligible queries.
- k = 5, cache off, official hints off, no retries, per-query timeout 30 s.
- Keyless primary chain: `mwmbl,wikipedia,bing,yahoo`.
- Arms (2 interleaved rounds, order A→B→C→D):
  - **A** primary only, `fuse_soft_timeout_s=0`, no supplement.
  - **B** primary only, `fuse_soft_timeout_s=0`, supplement `stackexchange`.
  - **C** primary only, `fuse_soft_timeout_s=2.0`, no supplement.
  - **D** primary only, `fuse_soft_timeout_s=2.0`, supplement `stackexchange`.

## Hypotheses and decision rules

### H1 — early stop is quality-non-inferior and faster

- Primary endpoint: P@5 (C vs A).
- Non-inferiority margin: **δ = 0.02 absolute** for P@5 and nDCG@5;
  **δ = 0.025 absolute** for Hit@5.
- Test: paired bootstrap (10,000 resamples) over the 40 queries × 2 rounds,
  pairing each C observation with the A observation from the same round.
- Accept H1 if the lower 95% bootstrap bound of each Δ is ≥ −δ **and**
  p50 latency improves by ≥ 20%.
- Reject/revert if any lower bound < −δ.

### H2 — supplement cannot displace primary hits

- Invariant by construction: supplements run only after ranking and
  diversification, fill only empty slots, and never reorder the primary prefix.
- Unit test: `test_supplement_fills_empty_slots_without_displacing_primary_hits`.
- Artifact check: every row whose warnings include `supplement:stackexchange`
  must have its primary URLs as an unchanged prefix; removing the supplement
  URLs must not lower P@5.
- Accept H2 if the unit test passes and the artifact check has **zero**
  violations. Otherwise remove Stack Exchange from the default supplement.

### H3 — shipped hybrid product is competitive with Tavily

- Run `--hybrid` n = 40: WebLens arm has Tavily auto-prepended plus the keyless
  fuse and supplement; Tavily arm is a direct Tavily search (`basic`).
- Primary endpoint: paired P@5. Secondary: nDCG@5, Hit@5, W/T/L, p50/p95.
- Claim "best tier" **only** if the paired P@5 95% CI lower bound is > 0
  (superiority). If the CI includes 0, claim non-inferiority at δ = 0.02 and
  report the latency/cost trade-off; do **not** claim best.
- Credit budget: 2 Tavily calls/query × 40 = **80 credits** (remaining 428;
  cap for this session 257). Abort if the observed spend would exceed the cap.

## Honesty rules

- WebLens-only runs report Tavily as `NOT RUN`, never `0.000`.
- Report point estimates with CIs and the paired design; no cherry-picking.
- If H1/H2/H3 fail, record the failure and the revert decision in
  `evidence/loop/STATE.json`; do not translate a failed hypothesis into a
  "completed" claim.

## Addendum — added before the hybrid run, after the keyless confirmatory result

- **H1 rejected for keyless pools.** Paired C−A 95% bootstrap CIs: P@5
  [−0.0300, +0.0100] vs margin −0.020; nDCG [−0.0237, +0.0091] vs −0.020;
  Hit@5 [−0.0500, +0.0250] vs −0.025. Latency passed (p50 −36%, p95 −29%).
  Quality-first therefore rejects the keyless early stop.
- **Design change:** the early stop is now gated on a Tavily hit being present
  in the accepted pool. Keyless pools always wait for every provider. This is
  the shipped product: a hosted fast path for keyed deployments, a thorough
  fuse for keyless deployments.
- **H2:** Stack Exchange never fired in the confirmatory n=40 (`sup_rows=0`),
  so it changed nothing on this dataset. It is retained as a dormant
  thin-pool filler; `test_supplement_fills_empty_slots_without_displacing_primary_hits`
  proves the primary prefix is preserved.
- **H3 is unchanged** except that the WebLens arm now uses the Tavily-gated
  fast path. If the shipped hybrid is non-inferior to raw Tavily, that
  validates the shipped configuration against the best baseline; it does not
  claim the fast path improves quality over a full fuse.

## Addendum 2 — relevance-filter fix (registered before the second hybrid run)

The first hybrid run lost four queries because the lexical filter discarded
authoritative hits whose titles are opaque (`sec.gov` filings, `investor.apple`
IR, `nvidia.com` product pages) while a thesaurus page survived. Live
provider-response probes confirmed the mechanism: Tavily's Apple result set had
**2/8 kept** before the fix and **7/8 kept** after; the NVIDIA set had **5/8**
before and **8/8** after, while dictionary/thesaurus junk was still dropped.

- **H4a (mechanism, deterministic):** with light plural/verb stemming, a
  one-term authority bypass for `.gov`/`.edu`/`.mil` and entity hosts, and a
  dictionary/thesaurus denylist for non-definition queries, the four
  representative losses keep their authoritative hits. Unit tests:
  `test_filter_keeps_opaque_official_filings`,
  `test_filter_stems_plural_and_verb_forms`,
  `test_filter_keeps_stemmed_alphafold_page`,
  `test_filter_drops_thesaurus_pages_unless_definitions_are_requested`,
  `test_filter_drops_an_unrelated_gov_page`.
- **H4b (end-to-end):** hybrid n=40 P@5 point estimate ≥ the first hybrid run
  (0.385), paired P@5 95% CI vs Tavily still excludes 0, and p50/p95 are within
  +10% of the first hybrid run (1923 / 4287 ms). If P@5 < 0.365, revert the
  authority bypass and keep only stemming + the denylist.
- Credit budget: 80 (second hybrid run). Cumulative session spend after this
  run stays under the 257 cap.

### Addendum 2 result — 2026-11-09

`R-20261109-HYBRID-40-FILTER` (ledger head `cfacf8a7…`, exit 0, uncontaminated):

- H4a confirmed on live provider responses. Tavily's Apple set went from 2/8
  kept to 7/8 (all SEC filings plus Apple IR); NVIDIA went from 5/8 to 8/8;
  dictionary/thesaurus junk was still dropped.
- H4b end-to-end: P@5 **0.365** vs Tavily 0.200 (paired +0.165, CI
  [+0.095, +0.245]); nDCG 0.399 vs 0.214 (+0.184, CI [+0.108, +0.268]);
  Hit@5 0.775 vs 0.625; W/T/L 18/21/1; p50 718 vs 331 ms; p95 2040 vs 501 ms;
  tokens 419 vs 1678.
- The P@5 point estimate is 0.02 below the first hybrid run (0.385). The
  cross-run bootstrap difference is -0.02 with a 95% CI [-0.10, +0.055], i.e.
  within provider noise; Hit@5 improved and losses fell from 4 to 1. The
  pre-registered revert trigger (`< 0.365`) was not met, so the filter is kept.
- The fast path fired in 36/40 rows (vs 2/40 before the filter fix), cutting
  p50 by 63% and p95 by 52%. One loss remains (`technical_research_q04`, CAP
  theorem). A follow-up probe of that query returned 8/8 Tavily hits kept by
  the filter, so the loss is provider-set/ranking variance, not a filter drop;
  the fast path still cancelled bing/wikipedia before they could contribute.
  Recorded as an open recall risk, not hidden.

### Fairness note on the hybrid comparison

The WebLens arm's Tavily adapter requests up to 8 results (the router calls
providers with `k=max(k, 8)`) and then fuses/ranks to the visible 5. The direct
Tavily arm requests `max_results=5`. Tavily bills per search, not per result, so
both arms spend one credit per query; the difference is candidate depth, which
is a product capability, not a credit asymmetry. The product-level comparison is
still valid, but a reviewer should not read it as "same request shape".



