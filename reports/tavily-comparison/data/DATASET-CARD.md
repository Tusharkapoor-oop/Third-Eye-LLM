# Stage 7 frozen dataset card

- Version: `stage7-v1`
- Frozen at: `2026-10-28T02:55:40.638013+00:00`
- Code commit: `902415d49f8da502b9de0e1c78da7f5777a1d2f8`
- Dataset: `reports/tavily-comparison/data/stage7_dataset.jsonl`
- SHA-256: `a4a64151fbdbda850a9de128bb7f83ec67f126b633aac42488c6f0b9296a9b21`
- Rows: 108 (81 dev / 27 sealed test)
- Categories: {'docs': 28, 'current_facts': 20, 'niche_technical': 22, 'unanswerable': 20, 'conflicting': 18}
- Answerable: 70; unanswerable: 20; conflict-labelled: 18

## Provenance

- 58 rows from `weblens/benchmarks/queries.jsonl` (WebLens regression labels).
- 50 rows from `benchmarks/eval_dataset.json` (independent human-written
  ground-truth answers and acceptable domains).
- No query is present in both sources. Labels were frozen before any Stage 7
  provider request.

## Exclusions

The 10,000-row synthetic corpus at
`reports/_archive/prior-run-20261027/extreme-benchmark/datasets/extreme_benchmark_10k.jsonl`
is excluded. Its SHA-256 matches the published card, but the file has only
5,528 unique `query_text` values for 10,000 rows, all 10,000
`required_factual_claims` values are placeholder strings such as
`Claim-cat01_current_news-0`, 350 query texts contain generated
`system_component_N` tokens, only 2 distinct `acceptable_domains` sets exist,
and the dev/val/sealed_test partition hashes do not match the manifest. It
cannot support honest quality scoring.

## Limitations

This is 108 English-centric queries, not 500. The categories are broad
(`docs`, `current_facts`, `niche_technical`, `unanswerable`, `conflicting`) and
do not cover multilingual retrieval, adversarial web pages, JavaScript-heavy
pages, or all 30 requested scenarios. Those scenarios are handled by the
separate security/extraction/load tests and are labelled as such; they are not
mixed into the quality denominator. Domain labels are strict and are not
human-judged relevance.
