# WebLens benchmark

- started: 2026-10-21T03:50:55.378820+00:00
- dataset: `benchmarks\queries.jsonl` (58 queries)
- tokenizer: `cl100k_base`
- passed: **False**

| metric | value |
| --- | --- |
| search precision@n (answerable) | 0.1711 (32/187) |
| top-3 authoritative | 0.5 (20/40) |
| research answer support | 0.9333 (28/30) |
| status match | 0.8448 |
| no-result accuracy | 0.1 (1/10) |
| conflict recall | 0.0 (0/8) |
| search p50 / p95 | 2118.1 / 10026.8 ms |
| extract p50 / p95 | 170.6 / 1663.8 ms |
| research p50 / p95 | 8268.9 / 23477.2 ms |
| schema tokens | 838 |

## Gates

| gate | ok | value | threshold |
| --- | --- | --- | --- |
| schema_tokens | True | 838 | 1000 |
| token_budget_violations | True | 0 | 0 |
| citation_failures | True | 0 | 0 |
| uncalibrated_fields | True | 0 | 0 |
| precision_at_n | False | 0.1711 | 0.25 |
| top3_authoritative | False | 0.5 | 0.6 |
| answer_support | True | 0.9333 | 0.6 |
| search_p50_ms | False | 2118.1 | 1500 |
| search_p95_ms | False | 10026.8 | 5000 |
| research_p95_ms | False | 23477.2 | 20000 |
| noresult_accuracy | False | 0.1 | 0.75 |
| extract_p50_ms | True | 170.6 | 2500 |
| extract_p95_ms | True | 1663.8 | 8000 |
