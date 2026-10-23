# WebLens benchmark

- started: 2026-10-21T04:52:06.667365+00:00
- dataset: `benchmarks\queries.jsonl` (58 queries)
- tokenizer: `cl100k_base`
- passed: **False**

| metric | value |
| --- | --- |
| search precision@n (answerable) | 0.0966 (17/176) |
| top-3 authoritative | 0.3 (12/40) |
| research answer support | 0.8667 (26/30) |
| status match | 0.9483 |
| no-result accuracy | 0.9 (9/10) |
| conflict recall | 0.0 (0/8) |
| search p50 / p95 | 2022.6 / 2520.1 ms |
| extract p50 / p95 | 751.9 / 1754.0 ms |
| research p50 / p95 | 9037.1 / 15428.8 ms |
| schema tokens | 838 |

## Gates

| gate | ok | value | threshold |
| --- | --- | --- | --- |
| schema_tokens | True | 838 | 1000 |
| token_budget_violations | True | 0 | 0 |
| citation_failures | True | 0 | 0 |
| uncalibrated_fields | True | 0 | 0 |
| precision_at_n | False | 0.0966 | 0.25 |
| top3_authoritative | False | 0.3 | 0.6 |
| answer_support | True | 0.8667 | 0.6 |
| search_p50_ms | False | 2022.6 | 1500 |
| search_p95_ms | True | 2520.1 | 5000 |
| research_p95_ms | True | 15428.8 | 20000 |
| noresult_accuracy | True | 0.9 | 0.75 |
| extract_p50_ms | True | 751.9 | 2500 |
| extract_p95_ms | True | 1754.0 | 8000 |
