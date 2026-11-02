# Latency, Throughput & Performance Results (V9)

## Evaluation Setup
All 15 stratified benchmark queries were evaluated with interleaved, rotating execution order across:
- System 1: Local WebLens MCP
- System 2: Deployed WebLens MCP (Cloud Run)
- System 3: Tavily Direct API

## Latency Distribution (Milliseconds)

| System | p50 (Median) | Mean | p90 | p95 | Max |
|---|---|---|---|---|---|
| **System 1 (Local WebLens)** | **939.5 ms** | **1,119.7 ms** | 1,602.0 ms | 3,464.5 ms | 3,464.5 ms |
| **System 2 (Deployed WebLens)** | 1,115.6 ms | 1,146.3 ms | **1,350.9 ms** | **1,380.2 ms** | **1,380.2 ms** |
| **System 3 (Tavily Direct)** | 3,062.2 ms | 3,246.6 ms | 3,907.9 ms | 4,883.3 ms | 4,883.3 ms |

## Speedup Factors
- **Local WebLens vs Tavily**: **3.26x faster** at p50 (939.5 ms vs 3,062.2 ms).
- **Deployed WebLens vs Tavily**: **2.74x faster** at p50 (1,115.6 ms vs 3,062.2 ms).
- **p95 Latency Stability**: Deployed WebLens exhibited the tightest tail latency at **1,380.2 ms** p95, compared to 4,883.3 ms for Tavily.

