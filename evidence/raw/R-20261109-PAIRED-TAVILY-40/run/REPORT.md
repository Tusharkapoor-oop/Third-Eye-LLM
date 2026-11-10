# WebLens vs Tavily — measured head-to-head (v11)

- Generated: 2026-11-09T12:38:40Z
- Dataset: `weblens-lab\datasets\eval_benchmark_suite_v10.json` (sha256 `a42d4004fb91208f…`)
- Queries graded: **40** (fixed prefix; exact ids in `results.json`)
- Selection: eligible (is_unanswerable=false, web_search_equivalent=true, >=1 label); heldout first then development, dataset order; fixed prefix of --limit
- k = 5; Tavily `search_depth=basic`, `max_results=5`
- WebLens: `WebLens.search(query, max_results=5)`, providers `mwmbl,wikipedia,bing,yahoo`, mode `fuse`, cache disabled, Tavily provider disabled
- Per-query timeout 30s, no retries, concurrency 2, sleep 0.5s
- Wall clock: 105.9s

## Results

| Metric | WebLens | Tavily | Better |
|---|---:|---:|---|
| Hit@5 | 0.550 | 0.600 | Tavily |
| P@5 | 0.325 | 0.180 | WebLens |
| nDCG@5 | 0.336 | 0.196 | WebLens |
| nDCG@5 (label-capped IDCG, sensitivity) | 0.446 | 0.311 | WebLens |
| MRR | 0.412 | 0.380 | WebLens |
| Success rate | 0.975 | 1.000 | Tavily |
| p50 latency (ms) | 3121.0 | 1080.9 | Tavily |
| p95 latency (ms) | 6196.9 | 3242.1 | Tavily |
| Mean result tokens | 316.4 | 1666.1 | WebLens |
| Mean full-payload tokens | 381.7 | 1731.5 | WebLens |

## 95% bootstrap CIs (2000 resamples, seeded)

| Metric | WebLens mean [CI] | Tavily mean [CI] |
|---|---|---|
| P@5 | 0.325 [0.215, 0.440] | 0.180 [0.125, 0.235] |
| nDCG@5 | 0.336 [0.220, 0.455] | 0.196 [0.139, 0.258] |
| MRR | 0.412 [0.272, 0.555] | 0.380 [0.261, 0.505] |

## Paired comparison (same queries)

- P@5 difference (WebLens − Tavily): **+0.145** [+0.035, +0.255]
- nDCG@5 difference: **+0.140** [+0.034, +0.248]
- Win / tie / loss (P@5): **19 / 14 / 7**

## Honest reading

- P@5: WebLens ahead by +0.145 (95% CI +0.035..+0.255, excludes zero).
- nDCG@5: paired difference +0.140 (95% CI +0.034..+0.248).
- Per-query P@5 wins/ties/losses: 19/14/7 over n=40.
- Latency: **WebLens slower** at p50 (3121ms vs 1081ms).
- Tail latency: **WebLens slower at p95** (6197ms vs 3242ms).
- Result tokens: WebLens returns fewer (316 vs 1666 per query).
- Reliability: **WebLens succeeds less often** (97.5% vs 100.0%).

## Where WebLens loses (explicit)

- Latency: WebLens slower at p50 (3121ms vs 1081ms).
- Tail latency: WebLens slower at p95 (6197ms vs 3242ms).

Largest per-query P@5 losses (Tavily better):

- `market_research_q01`: WebLens P@5=0.0 vs Tavily P@5=0.6 — What were Apple's reported total net sales in its official FY2024 10-K SEC regulatory filing?
- `public_sector_research_q01`: WebLens P@5=0.0 vs Tavily P@5=0.6 — What is the mission and core dataset repositories provided by NASA Earthdata?
- `scientific_research_q01`: WebLens P@5=0.0 vs Tavily P@5=0.4 — What is AlphaFold 3 capable of predicting beyond protein structures?
- `industry_research_q01`: WebLens P@5=0.0 vs Tavily P@5=0.4 — What are the major commercial AI hardware chip families produced by NVIDIA for data centers?
- `long_document_extraction_q04`: WebLens P@5=0.0 vs Tavily P@5=0.2 — Which article of the United States Constitution establishes the judicial branch?

## Anomalies flagged for human review

- `current_events_news_q01` — no_relevant_result_from_either
- `programming_developer_docs_q01` — weblens_status=no_reliable_result, weblens_returned_nothing
- `programming_developer_docs_q04` — no_relevant_result_from_either
- `academic_research_q01` — no_relevant_result_from_either
- `long_document_extraction_q01` — no_relevant_result_from_either
- `stock_portfolio_research_q01` — no_relevant_result_from_either
- `stock_portfolio_research_q04` — no_relevant_result_from_either
- `legal_policy_research_q04` — no_relevant_result_from_either
- `healthcare_information_q04` — no_relevant_result_from_either
- `structured_data_enrichment_q01` — no_relevant_result_from_either
- `website_crawling_q04` — no_relevant_result_from_either

## What the labels actually measure (read this before quoting anything)

Both systems are scored only on whether their ranked URLs land on the dataset's
`acceptable_sources` domains. That rewards *authoritative sources*, not *correct answers*:
a page on the right domain can still be off-topic, and a perfect answer on an unlabelled
domain scores zero. Read this as an authority / source-selection signal, not a truth benchmark.

## Contamination control (why the curated hints are off)

WebLens ships an author-curated `official_source_urls()` hint list that injects deterministic
primary-source URLs for well-known topics. Its own `router.py` comment says these must be
disabled for an honest head-to-head, because the hint list and the dataset labels share an
author.

**This report only ever states the configuration it was produced with.** To quantify the
hint effect or run-to-run stability, run the script twice with `--hints` on/off and compare
the two `results.json` files — the numbers are intentionally *not* baked into the template,
because hardcoded tables cannot be audited against the artifacts they claim to summarise.

Measured effect when both runs are done on the same provider chain (from this project's
v11 comparison, `reports/weblens-vs-tavily-v11/README.md`):

| Run | WebLens P@5 | WebLens nDCG@5 | WebLens MRR | WebLens Hit@5 |
|---|---:|---:|---:|---:|
| hints OFF (this report's setting) | 0.325 | 0.336 | 0.412 | 0.550 |
| hints ON (label-contaminated, separate run) | see that run's own results.json | — | — | — |

The curated hints are known to inflate WebLens P@5 substantially on these queries. Any
WebLens-vs-Tavily figure produced with hints enabled is measuring label leakage, not
retrieval quality.

## Run-to-run stability

Not asserted here. Keyless HTML providers (mwmbl/bing/yahoo) return partly different result
sets per call, so quality metrics wobble between runs; Tavily itself was observed to vary
between runs too (its P@5 and p50 changed between the two v11 runs). Treat a single run as
indicative and re-run to confirm any close call. The 95% CIs above are the intended
uncertainty estimate.

## Caveats (read before quoting any number)

- **Labels are domains, not judged documents.** Link relevance is domain matching against `acceptable_sources`; it rewards authoritative sources but does not prove a snippet answers the query.
- **nDCG IDCG convention:** IDCG assumes all k positions could be relevant (the judged-set size is unknown), so absolute nDCG values are conservative. A label-capped sensitivity column is reported.
- **Token comparison is not symmetric by nature.** Headline tokens count only the results array; Tavily's full payload (answer/images/request_id) is reported separately, not compared.
- **One run, one machine, one network path.** Latency is indicative only; no caching on either side (WebLens `cache_enabled=false`; Tavily has no client cache).
- **WebLens used keyless providers only** (`mwmbl,wikipedia,bing,yahoo`) with the Tavily provider explicitly disabled, so this is WebLens-independent vs Tavily-hosted.
- **Contamination guard:** WebLens's author-curated `official_source_urls` hints are disabled. `router.py` itself states they must be off for an honest head-to-head, because the dataset labels and the hint list were written by the same author. With hints on, WebLens scores far higher because it injects the very domains the labels reward.
- **Paid vs free:** Tavily is a metered hosted API; WebLens here is keyless scraping/aggregation.

