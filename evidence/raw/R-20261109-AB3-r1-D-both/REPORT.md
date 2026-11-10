# WebLens-only re-measure (Tavily arm NOT RUN)

- Generated: 2026-11-09T16:28:23Z
- Dataset: `weblens-lab\datasets\eval_benchmark_suite_v10.json` (sha256 `a42d4004fb91208f…`)
- Queries graded: **40** (fixed prefix; exact ids in `results.json`)
- Selection: eligible (is_unanswerable=false, web_search_equivalent=true, >=1 label); heldout first then development, dataset order; fixed prefix of --limit
- k = 5; WebLens: `WebLens.search(query, max_results=5)`, providers `mwmbl,wikipedia,bing,yahoo`, supplements `stackexchange`, mode `fuse`, cache disabled
- Fuse policy: soft deadline 2.0s; early stop needs k+2 distinct hits across >=3 domains (0s = wait for all)
- Per-query timeout 30s, no retries, concurrency 2, sleep 0.5s
- Wall clock: 60.5s

> **Tavily arm: NOT RUN.** No Tavily key was used and no credits were spent.
> The `tavily` block in `results.json` is a skipped-arm placeholder, not a
> measured zero. This file must never be quoted as a WebLens-vs-Tavily
> head-to-head or as evidence that WebLens beat Tavily.

## WebLens results

| Metric | WebLens |
|---|---:|
| Hit@5 | 0.750 |
| P@5 | 0.380 |
| nDCG@5 | 0.390 |
| nDCG@5 (label-capped IDCG, sensitivity) | 0.544 |
| MRR | 0.511 |
| Success rate | 1.000 |
| p50 latency (ms) | 2054.4 |
| p95 latency (ms) | 4656.9 |
| Mean result tokens | 351.4 |
| Mean full-payload tokens | 411.4 |

## 95% bootstrap CIs (2000 resamples, seeded)

| Metric | WebLens mean [CI] |
|---|---|
| P@5 | 0.380 [0.285, 0.475] |
| nDCG@5 | 0.390 [0.287, 0.498] |
| MRR | 0.511 [0.380, 0.642] |

## Anomalies flagged for human review (WebLens side only)

- None.

## What the labels actually measure (read this before quoting anything)

Relevance is domain matching against the dataset's `acceptable_sources`: it rewards
*authoritative sources*, not *correct answers*. A page on the right domain can still
be off-topic, and a perfect answer on an unlabelled domain scores zero. Read this as
an authority / source-selection signal, not a truth benchmark.

## Contamination control

WebLens's author-curated `official_source_urls` hints are disabled.
They must stay off for any honest comparison because the hint list and the dataset
labels share an author.

## Run-to-run stability

Not asserted here. Keyless HTML providers return partly different result sets per call,
so quality metrics wobble between runs. Treat one run as indicative; the CIs above are
the intended uncertainty estimate.

## Caveats

- **This is not a comparison.** No baseline was measured in this run.
- **Labels are domains, not judged documents.**
- **nDCG IDCG convention:** the judged-set size is unknown, so absolute values are conservative.
- **One run, one machine, one network path.** Latency is indicative only; caching is disabled.
- **Providers:** keyless `mwmbl,wikipedia,bing,yahoo` with the Tavily provider explicitly disabled.

