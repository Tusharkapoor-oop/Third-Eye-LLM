# WebLens vs Tavily â€” measured head-to-head (v11)

- Generated: 2026-11-09T09:34:33Z
- Dataset: `weblens-lab\datasets\eval_benchmark_suite_v10.json` (sha256 `a42d4004fb91208fâ€¦`)
- Queries graded: **40** (fixed prefix; exact ids in `results.json`)
- Selection: eligible (is_unanswerable=false, web_search_equivalent=true, >=1 label); heldout first then development, dataset order; fixed prefix of --limit
- k = 5; Tavily `search_depth=basic`, `max_results=5`
- WebLens: `WebLens.search(query, max_results=5)`, providers `ddg,mwmbl,wikipedia`, mode `fuse`, cache disabled, Tavily provider disabled
- Per-query timeout 30s, no retries, concurrency 2, sleep 0.5s
- Wall clock: 47.9s

## Results

| Metric | WebLens | Tavily | Better |
|---|---:|---:|---|
| Hit@5 | 0.525 | 0.600 | Tavily |
| P@5 | 0.315 | 0.190 | WebLens |
| nDCG@5 | 0.326 | 0.202 | WebLens |
| nDCG@5 (label-capped IDCG, sensitivity) | 0.436 | 0.318 | WebLens |
| MRR | 0.395 | 0.379 | WebLens |
| Success rate | 0.975 | 1.000 | Tavily |
| p50 latency (ms) | 1172.8 | 318.1 | Tavily |
| p95 latency (ms) | 3594.7 | 411.7 | Tavily |
| Mean result tokens | 315.6 | 1674.9 | WebLens |
| Mean full-payload tokens | 377.8 | 1740.5 | WebLens |

## 95% bootstrap CIs (2000 resamples, seeded)

| Metric | WebLens mean [CI] | Tavily mean [CI] |
|---|---|---|
| P@5 | 0.315 [0.205, 0.430] | 0.190 [0.135, 0.250] |
| nDCG@5 | 0.326 [0.210, 0.447] | 0.202 [0.143, 0.264] |
| MRR | 0.395 [0.255, 0.536] | 0.379 [0.259, 0.501] |

## Paired comparison (same queries)

- P@5 difference (WebLens âˆ’ Tavily): **+0.125** [+0.015, +0.235]
- nDCG@5 difference: **+0.124** [+0.017, +0.230]
- Win / tie / loss (P@5): **18 / 14 / 8**

## Honest reading

- P@5: WebLens ahead by +0.125 (95% CI +0.015..+0.235, excludes zero).
- nDCG@5: paired difference +0.124 (95% CI +0.017..+0.230).
- Per-query P@5 wins/ties/losses: 18/14/8 over n=40.
- Latency: **WebLens slower** at p50 (1173ms vs 318ms).
- Tail latency: **WebLens slower at p95** (3595ms vs 412ms).
- Result tokens: WebLens returns fewer (316 vs 1675 per query).
- Reliability: **WebLens succeeds less often** (97.5% vs 100.0%).

## Where WebLens loses (explicit)

- Latency: WebLens slower at p50 (1173ms vs 318ms).
- Tail latency: WebLens slower at p95 (3595ms vs 412ms).

Largest per-query P@5 losses (Tavily better):

- `market_research_q01`: WebLens P@5=0.0 vs Tavily P@5=0.6 â€” What were Apple's reported total net sales in its official FY2024 10-K SEC regulatory filing?
- `public_sector_research_q01`: WebLens P@5=0.0 vs Tavily P@5=0.6 â€” What is the mission and core dataset repositories provided by NASA Earthdata?
- `healthcare_information_q01`: WebLens P@5=0.0 vs Tavily P@5=0.6 â€” What are the clinical diagnostic criteria for Type 2 Diabetes according to the American Diabetes Association g
- `industry_research_q01`: WebLens P@5=0.0 vs Tavily P@5=0.4 â€” What are the major commercial AI hardware chip families produced by NVIDIA for data centers?
- `scientific_research_q01`: WebLens P@5=0.0 vs Tavily P@5=0.2 â€” What is AlphaFold 3 capable of predicting beyond protein structures?

## Anomalies flagged for human review

- `general_factual_q01` â€” latency_outlier
- `general_factual_q04` â€” latency_outlier
- `current_events_news_q01` â€” no_relevant_result_from_either, latency_outlier
- `programming_developer_docs_q01` â€” weblens_status=no_reliable_result, weblens_returned_nothing
- `programming_developer_docs_q04` â€” no_relevant_result_from_either
- `academic_research_q01` â€” no_relevant_result_from_either
- `long_document_extraction_q01` â€” no_relevant_result_from_either
- `company_research_q01` â€” no_relevant_result_from_either
- `stock_portfolio_research_q01` â€” no_relevant_result_from_either
- `stock_portfolio_research_q04` â€” no_relevant_result_from_either
- `legal_policy_research_q04` â€” no_relevant_result_from_either
- `healthcare_information_q04` â€” no_relevant_result_from_either
- `structured_data_enrichment_q01` â€” no_relevant_result_from_either
- `website_crawling_q04` â€” no_relevant_result_from_either

## Caveats (read before quoting any number)

- **Labels are domains, not judged documents.** Link relevance is domain matching against `acceptable_sources`; it rewards authoritative sources but does not prove a snippet answers the query.
- **nDCG IDCG convention:** IDCG assumes all k positions could be relevant (the judged-set size is unknown), so absolute nDCG values are conservative. A label-capped sensitivity column is reported.
- **Token comparison is not symmetric by nature.** Headline tokens count only the results array; Tavily's full payload (answer/images/request_id) is reported separately, not compared.
- **One run, one machine, one network path.** Latency is indicative only; no caching on either side (WebLens `cache_enabled=false`; Tavily has no client cache).
- **WebLens used keyless providers only** (`ddg,mwmbl,wikipedia`) with the Tavily provider explicitly disabled, so this is WebLens-independent vs Tavily-hosted.
- **Contamination guard:** WebLens's author-curated `official_source_urls` hints are disabled. `router.py` itself states they must be off for an honest head-to-head, because the dataset labels and the hint list were written by the same author. With hints on, WebLens scores far higher because it injects the very domains the labels reward.
- **Paid vs free:** Tavily is a metered hosted API; WebLens here is keyless scraping/aggregation.

