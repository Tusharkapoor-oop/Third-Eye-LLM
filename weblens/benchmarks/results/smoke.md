# WebLens benchmark

- started: 2026-10-20T17:27:40.964807+00:00
- dataset: `benchmarks\queries.jsonl` (2 queries)
- tokenizer: `cl100k_base`
- passed: **False**

| metric | value |
| --- | --- |
| search precision@n (answerable) | 0.2 (2/10) |
| top-3 authoritative | 1.0 (2/2) |
| research answer support | 1.0 (2/2) |
| status match | 1.0 |
| no-result accuracy | None (0/0) |
| conflict recall | None (0/0) |
| search p50 / p95 | 885.3 / 2320.0 ms |
| extract p50 / p95 | 91.0 / 904.3 ms |
| research p50 / p95 | 2673.0 / 3730.9 ms |
| schema tokens | 838 |

## Gates

| gate | ok | value | threshold |
| --- | --- | --- | --- |
| schema_tokens | True | 838 | 1000 |
| token_budget_violations | True | 0 | 0 |
| citation_failures | True | 0 | 0 |
| uncalibrated_fields | True | 0 | 0 |
| precision_at_n | False | 0.2 | 0.25 |
| top3_authoritative | True | 1.0 | 0.6 |
| answer_support | True | 1.0 | 0.6 |
| search_p50_ms | True | 885.3 | 1500 |
| search_p95_ms | True | 2320.0 | 5000 |
| research_p95_ms | True | 3730.9 | 20000 |
