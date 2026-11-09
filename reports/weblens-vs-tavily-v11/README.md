# WebLens vs Tavily — measured comparison and remediation log (v11)

Two independent runs, both on the **same 40 held-out queries** from
`weblens-lab/datasets/eval_benchmark_suite_v10.json`
(sha256 `a42d4004fb91208f1ae18de89e2337f2ccf5e7cb580a3c600a8ec7d8057d6361`),
`k=5`, both systems scored with identical relevance rules against each query's
`acceptable_sources` domain labels. Nothing is cherry-picked: the query set is a
deterministic ordered slice and the ids are in every results file.

## The contamination finding (most important)

WebLens has an author-curated table (`weblens/src/weblens/urls.py`,
`official_source_urls()`) that injects deterministic "primary source" URLs for
~40 well-known topics. The dataset's relevance labels are **also**
author-curated. Leaving the hints enabled therefore measures **label leakage**,
not retrieval quality.

Measured on the same 40 queries:

| Hints | WebLens P@5 | WebLens nDCG@5 | WebLens MRR |
|---|---:|---:|---:|
| **ON** (contaminated) | 0.805 | 0.835 | 0.935 |
| **OFF** (honest) | 0.315 | 0.326 | 0.395 |

Hints inflate P@5 by **+0.49 absolute**. The earlier repo claim of
"P@5 0.867 / nDCG 1.000" was this artifact. A new setting,
`Settings.use_official_source_hints`, now makes the switch explicit, and the
benchmark runner defaults it **OFF** and stamps the value into `results.json`.

## Run 1 — baseline (default provider chain `ddg,mwmbl,wikipedia`)

`reports/weblens-vs-tavily-v11/results.canonical.json`

| Metric | WebLens | Tavily | Better |
|---|---:|---:|---|
| Hit@5 | 0.525 | **0.600** | Tavily |
| P@5 | **0.315** | 0.190 | WebLens |
| nDCG@5 | **0.326** | 0.202 | WebLens |
| MRR | **0.395** | 0.379 | WebLens |
| Success rate | 0.975 | **1.000** | Tavily |
| p50 latency | 1173 ms | **318 ms** | Tavily |
| p95 latency | 3595 ms | **412 ms** | Tavily |
| Mean payload tokens | **316** | 1675 | WebLens |

Paired P@5 **+0.125**, 95% CI **[+0.015, +0.235]**, W/T/L **18 / 14 / 8**.

**Diagnosis:** DuckDuckGo was the first provider in the default chain and it
timed out on **every** query from this network (connect timeout, all three DDG
endpoints), so WebLens silently ran on two weak providers (mwmbl + wikipedia).
Five queries returned fewer than five results, one returned zero.

## Run 2 — final (product default provider chain `mwmbl,wikipedia,bing,yahoo`)

`reports/weblens-vs-tavily-v11/results.json` — this is the current, reproducible run.

| Metric | WebLens | Tavily | Better |
|---|---:|---:|---|
| Hit@5 | **0.775** | 0.600 | WebLens |
| P@5 | **0.410** | 0.210 | WebLens |
| nDCG@5 | **0.416** | 0.232 | WebLens |
| MRR | **0.523** | 0.423 | WebLens |
| Success rate | 1.000 | 1.000 | tie |
| p50 latency | 3057 ms | **295 ms** | Tavily |
| p95 latency | 6391 ms | **344 ms** | Tavily |
| Mean payload tokens | **367** | 1680 | WebLens |

Paired P@5 **+0.200**, 95% CI **[+0.110, +0.295]**, W/T/L **22 / 12 / 6**.
WebLens P@5 CI `[0.315, 0.515]`; Tavily P@5 CI `[0.150, 0.275]`.

Every quality metric improved and all 40 queries now return five results. The
cost is latency (the added HTML providers are slower than the dead DDG path
that was being skipped anyway).

## What changed in the code as a result

1. **`Settings.search_providers` default** → `mwmbl,wikipedia,bing,yahoo`.
   A single keyless provider that blocks a whole network must not silently
   collapse the chain. The router already tracks per-provider health and skips
   a failing endpoint for a cooldown window.
2. **`Settings.use_official_source_hints`** (default `True` for product use,
   forced `False` by the benchmark) so contamination can never be accidental.
3. **`diversify(..., strict=True)`** — the old implementation returned
   `capped + surplus`, so a `[:k]` slice could be filled entirely by one domain
   (measured: 55% redundant slots). Strict mode enforces the cap; the router
   pads back to `k` when the diverse pool is short and emits
   `diversity_padded:<n>` so padding is never silent.
4. Regression tests: `weblens/tests/test_result_diversity_and_hints.py`.

## Honest verdict

After the provider-chain fix, WebLens is ahead of Tavily on **every quality
metric** on this benchmark: Hit@5 0.775 vs 0.600, P@5 0.410 vs 0.210, nDCG@5
0.416 vs 0.232, MRR 0.523 vs 0.423 — the paired P@5 difference is +0.200 with a
95% CI of [+0.110, +0.295] that excludes zero, and it emits **~4.6× fewer
tokens** while returning five results for all 40 queries. Tavily remains
**~10× faster** at p50 (295 ms vs 3057 ms).

WebLens still **loses specific queries** where Tavily surfaces the labelled
domain and WebLens does not — 6 outright losses out of 40.

This is **not** a claim of world-class retrieval. It is one dataset, one
machine, one network path, domain-level labels rather than judged answers, and
a paid hosted API compared against keyless scraping. Latency in particular is
not a controlled measurement, and Tavily's own numbers varied between runs.

## Reproduce

```bash
python weblens-lab/evaluations/run_weblens_vs_tavily_v11.py --limit 40
python weblens-lab/evaluations/run_weblens_vs_tavily_v11.py --limit 40 --hints   # contaminated baseline
python -m pytest weblens-lab/evaluations/test_v11_metrics.py -q                   # metric unit tests
```
