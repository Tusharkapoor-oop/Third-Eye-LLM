# Extreme-Scale Equivalent — Performance, Load, and Cost

**Scale:** 108 queries, 6 load cells, 4 crawl/map operations, 10 extraction targets  
**Evidence:** `../tavily-comparison/PERFORMANCE-RESULTS.json`, `COST-AND-TOKEN-RESULTS.json`

This is not a production capacity test. Load is six queries per cell at concurrency 1/2/5.

---

## 1. Search latency

Combined successful paired queries (`n=70`):

| System | Mean | p50 | p90 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| Direct Tavily | 1,637.3 ms | 1,544.5 ms | 2,116.7 ms | 2,531.4 ms | 3,014.1 ms |
| WebLens keyless | **886.8 ms** | **753.0 ms** | **1,158.3 ms** | 2,513.8 ms | 3,650.0 ms |
| WebLens-Tavily | 901.1 ms | **339.0 ms** | 2,287.1 ms | 2,539.9 ms | 4,004.7 ms |

Keyless is faster in the mean and median, but its p95 is essentially tied with Tavily direct. WebLens-Tavily has the best median and the worst p99.

Pre-registered operational gate: search p95 ≤ 5,000 ms. All three pass on this run. That is not a guarantee for other networks or larger result sets.

## 2. Research latency

Combined (`n=70`):

| System | Mean |
|---|---:|
| WebLens keyless | **3,399.7 ms** |
| WebLens-Tavily | 4,329.1 ms |

WebLens-Tavily is slower by `929.4 ms` mean on paired answerable rows (`n=70`; `[384.2, 1480.7]`). Across all 108 research records the means are `3,586.3 ms` (keyless) and `4,017.2 ms` (WebLens-Tavily). Research p95 is under the 20,000 ms gate for both on this run; the exact research p95 values are in `PERFORMANCE-RESULTS.json`.

## 3. Load probe

Six queries per cell.

| Provider | Concurrency | Wall time | Mean latency | p95 | Statuses |
|---|---:|---:|---:|---:|---|
| Keyless | 1 | 8,860.9 ms | 1,474.2 ms | 2,201.4 ms | 3 `ok`, 3 `partial` |
| Keyless | 2 | 8,432.3 ms | 2,569.0 ms | 3,332.9 ms | 6 `partial` |
| Keyless | 5 | 4,178.1 ms | 3,022.9 ms | 4,176.1 ms | 6 `partial` |
| WebLens-Tavily | 1 | 2,640.8 ms | 440.0 ms | 937.8 ms | 6 `ok` |
| WebLens-Tavily | 2 | 1,053.6 ms | 348.3 ms | 395.3 ms | 6 `ok` |
| WebLens-Tavily | 5 | 940.1 ms | 563.3 ms | 932.1 ms | 6 `ok` |

Observations:

- WebLens-Tavily stayed `ok` at all three levels.
- Keyless degraded to `partial` at all levels, including concurrency 1.
- Wall time is not monotonic because provider responses and cache state differ; this is a small probe, not a throughput curve.

No production capacity conclusion is supported.

## 4. Browser and crawl/map

### Browser fixture

- Static: HTTP and browser `ok`.
- JavaScript: HTTP `no_reliable_result`; browser `ok` at 2,756.8 ms, one proxy request.
- Injection: both `ok`; injection flagged; text retained.

### Crawl/map

| Operation | Direct Tavily | WebLens keyless |
|---|---:|---:|
| Map latency | 1,683.4 ms | 12,506.5 ms |
| Map results | 10 | **0** |
| Crawl latency | 2,042.8 ms | 6,932.7 ms |
| Crawl results | 3 | **0** |

Keyless returned `ok` with zero results. This is a functional failure, not merely a speed difference.

## 5. Cost and tokens

### Tavily credits

| Item | Value |
|---|---:|
| Plan | Researcher |
| Limit | 1,000 |
| Usage before | 170 |
| Usage after | 551 |
| Remaining | 449 |
| Campaign delta | 381 |
| Campaign cap | 420 |
| Hard stop | 200 remaining |

The cap and stop were respected. Final usage check: `2026-10-28T10:25:24Z`.

Observed paid calls: 375 search, 10 extract, 1 map, 1 crawl. Meter deltas: 376 search, 4 extract, 1 map, 0 crawl. The one-credit search difference is unreconciled.

No invoice or per-credit USD price was available. Incremental USD cost is **not verified**. Do not quote a dollar figure as measured.

### Tokens

`cl100k_base` counts of delivered JSON, not billed model tokens.

| Mode | Mean search payload tokens | Mean research payload tokens |
|---|---:|---:|
| Direct Tavily | 1,034.1 | — |
| WebLens keyless | **505.3** | 532.8 |
| WebLens-Tavily | 891.2 | 595.7 |

Extraction text tokens:

- Tavily: 12,214 mean.
- WebLens full: 2,421 mean.
- WebLens query-focused: 433 mean.

The token reduction is large, but extraction support is lower (`0.7` vs `1.0`). Token efficiency is not quality.

## 6. Verdict

- Keyless is faster and lighter in the typical case.
- Tavily direct has the best p99 on this run (`3,014.1 ms`); all modes pass the 5 s p95 gate.
- WebLens-Tavily is fast for search but slower for research.
- Keyless load behavior is poor (`partial` statuses).
- Crawl/map keyless is functionally broken (0 results).
- Cost is 381 credits; USD cost is unverified.

No production-scale performance claim is supported.
