# Latency & Response Time Benchmark Results

## Evaluation Date
2026-11-01

## Benchmark Conditions
- **Network**: Broadband residential connection, Windows 11 host.
- **Trial Design**: 18 paired interleaved trials.
- **Measurement**: High-precision wall-clock time (`time.perf_counter()`) capturing round-trip duration in milliseconds.

---

## Latency Distribution Summary

| Metric | WebLens Independent | Tavily API | Difference (WL - TV) | Ratio (TV / WL) |
| :--- | :--- | :--- | :--- | :--- |
| **Minimum** | **6.4 ms** | 850.8 ms | -844.4 ms | 132.1x |
| **Median (p50)** | **46.5 ms** | 896.6 ms | -850.1 ms | **19.3x** |
| **p90** | 1,003.0 ms | **920.5 ms** | +82.5 ms | 0.92x |
| **p95** | 1,006.7 ms | **970.0 ms** | +36.7 ms | 0.96x |
| **Maximum** | 1,803.3 ms | 1,945.6 ms | -142.3 ms | 1.08x |
| **Mean** | **519.7 ms** | 956.9 ms | -437.2 ms | **1.84x** |

---

## Latency Analysis

1. **Sub-100ms Responses**:
   - WebLens completed 8 out of 18 queries in less than 50ms due to fast direct index lookups and local in-memory cache hits.
   - Tavily completed 0 queries in less than 850ms, reflecting cloud network transit and proprietary scraping overhead.

2. **Tail Latency (p90 / p95)**:
   - When WebLens executes multi-engine fallback chains (DuckDuckGo -> Wikipedia -> Mwmbl) on cold network queries, latency rises to ~1,000 ms.
   - Tavily maintains a very predictable 850-950 ms band for cloud searches, with occasional spikes to ~1,945 ms on complex queries.

3. **Conclusion**:
   WebLens is substantially faster at median (19x) and on average (1.8x), while Tavily exhibits slightly lower variance at the extreme 95th percentile.

