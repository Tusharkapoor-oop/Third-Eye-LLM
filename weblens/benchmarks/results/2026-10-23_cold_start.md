# WebLens cold start and cache

- measured: 2026-10-23T04:00:27.379849+00:00
- Python: 3.14.0 on Windows 11
- samples per subprocess metric: 3

| metric | median | min | max |
| --- | --- | --- | --- |
| import `weblens.service` | 471.3 ms | 467.5 ms | 494.0 ms |
| service + MCP server ready | 2290.5 ms | 2006.9 ms | 2491.4 ms |
| first `count_tokens` (tiktoken load) | 320.1 ms | 211.1 ms | 390.6 ms |
| search, network (Wikipedia, single sample) | 2121.0 ms | | |
| search, repeated (HTTP cache path, 3 samples) | 7.4 ms | 6.3 ms | 8.2 ms |
| extract, network (single sample) | 1779.0 ms | | |
| extract, HTTP cache + reparse | 5.3 ms | 4.9 ms | 6.2 ms |

Search status: `ok`; extract status: `ok`; extract cache status: `ok`.
Search provider failures: `{}`; warnings: `[]`.
Network samples are indicative, not a latency percentile. See `benchmarks/results/` for the p50/p95 run.
