# WebLens benchmark

- started: 2026-10-21T04:25:30.064360+00:00
- dataset: `benchmarks\queries.jsonl` (28 queries)
- tokenizer: `cl100k_base`
- passed: **False**

| metric | value |
| --- | --- |
| search precision@n (answerable) | 0.1875 (15/80) |
| top-3 authoritative | 0.3333 (6/18) |
| research answer support | 1.0 (18/18) |
| status match | 0.8929 |
| no-result accuracy | 0.8 (8/10) |
| conflict recall | None (0/0) |
| search p50 / p95 | 3360.9 / 3528.6 ms |
| extract p50 / p95 | 940.3 / 1652.4 ms |
| research p50 / p95 | 7923.3 / 13290.5 ms |
| schema tokens | 838 |

## Gates

| gate | ok | value | threshold |
| --- | --- | --- | --- |
| schema_tokens | True | 838 | 1000 |
| token_budget_violations | True | 0 | 0 |
| citation_failures | True | 0 | 0 |
| uncalibrated_fields | True | 0 | 0 |
| precision_at_n | False | 0.1875 | 0.25 |
| top3_authoritative | False | 0.3333 | 0.6 |
| answer_support | True | 1.0 | 0.6 |
| search_p50_ms | False | 3360.9 | 1500 |
| search_p95_ms | True | 3528.6 | 5000 |
| research_p95_ms | True | 13290.5 | 20000 |
| noresult_accuracy | True | 0.8 | 0.75 |
| extract_p50_ms | True | 940.3 | 2500 |
| extract_p95_ms | True | 1652.4 | 8000 |
