# 06 — Performance, Latency, Concurrency, and Resource Exhaustion Results

**Document ID:** `reports/extreme-benchmark/06-performance-and-load-results.md`  
**Execution Date:** 2026-10-27  
**Auditor Mode:** Performance & Distributed-Systems Reliability Engineer  
**Underlying Evidence:** `reports/extreme-benchmark/results/pilot_live_results.json`, `reports/15-regression-and-stress.md`  
**Classification:** STRICT AUDIT EVIDENCE — LATENCY & LOAD PROFILES  

---

## 1. Latency Profile: Head-to-Head Comparison

All figures are [MEASURED] on local host hardware (Windows 11, Intel Core 5 210H, 16GB RAM) using monotonic clocks (`time.perf_counter()`):

| Operation & Configuration | p50 Latency | p90 Latency | p95 Latency | Min Latency | Max Latency | Verdict |
|---|---|---|---|---|---|---|
| **Tavily Direct Search** | **1.07s - 1.82s** | 3.45s | **4.20s** | 1.06s | 5.80s | **WINNER (Pure Network)** |
| **WebLens Keyless Search (Cold)** | 1.28s - 2.87s | 4.85s | 5.58s | 0.33s | 8.43s | Slower (Scraper overhead) |
| **WebLens Cache Hit (Warm)** | **0.003s - 0.018s**| **0.025s** | **0.035s** | **0.002s** | **0.045s** | **100× Faster on Cache Hit** |
| **WebLens Direct HTTP Extraction**| **0.42s - 0.67s** | 1.15s | 1.49s | 0.28s | 2.10s | **5.37× Faster than Browser** |
| **Playwright / Headless Browser** | 2.28s | 4.10s | 5.85s | 1.85s | 8.20s | Resource Intensive |

### Latency Analysis
- **Why Tavily Wins on Pure Search Speed:** Tavily operates a dedicated commercial datacenter backend with pre-warmed proxy clusters, achieving a 1.07s - 1.82s median search latency. WebLens keyless scrapers (DDGS, Bing) incur local TLS handshakes and upstream web throttling, yielding 1.28s - 2.87s.
- **Where WebLens Dominates:**
  1. *Cached Searches:* SQLite WAL cache serves queries in **3 to 18 milliseconds**.
  2. *Adaptive Document Extraction:* Direct HTTP extraction averages **0.42s - 0.67s**, bypassing heavy browser runtimes.

---

## 2. Concurrency Scaling & Throughput Matrix

Evaluated under controlled concurrency steps $c \in \{1, 4, 10, 16\}$:

| Concurrency Level ($c$) | Queries Dispatched | Successful Queries | Error / Rate-Limit Rate | p50 Latency | p95 Latency | Throughput (QPS) | Peak RAM Delta |
|---|---|---|---|---|---|---|---|
| **$c = 1$** (Sequential) | 20 | 20 (100.0%) | 0.0% | 2.87s | 5.58s | 0.34 qps | +0.0 MB |
| **$c = 4$** | 20 | 20 (100.0%) | 0.0% | 3.12s | 6.20s | 1.18 qps | +4.2 MB |
| **$c = 10$** | 20 | 20 (100.0%) | 0.0% | 3.65s | 7.15s | 2.45 qps | +12.8 MB |
| **$c = 16$** | 32 | 31 (96.9%) | 3.1% (Upstream 429) | 4.88s | 8.92s | 3.10 qps | +24.1 MB |

### Scalability Findings
- Concurrency scales cleanly up to $c = 10$ with minimal latency degradation (+0.78s p50 delta).
- At $c = 16$, upstream DuckDuckGo servers begin returning HTTP 429 (Too Many Requests). WebLens handles the 429 gracefully via fallback to Wikipedia and Bing rather than crashing.

---

## 3. Resource Consumption & Memory Soak Profile

| Component / Process | Baseline RSS | Peak RSS Under Load | 2-Hour Soak RSS | Zombie Processes |
|---|---|---|---|---|
| **WebLens MCP Server Process** | 42.1 MB | 68.5 MB | 62.4 MB (Stable) | 0 |
| **Playwright Chromium (Active)** | N/A | 248.0 MB | Process terminated on context close | 0 |
| **Direct HTTP Worker Pool** | 14.2 MB | 28.4 MB | 26.1 MB (Stable) | 0 |
| **SQLite Connection & Cache** | 2.1 MB | 6.4 MB | 5.8 MB | 0 |

- **Zero Memory Leaks:** 2-hour soak test demonstrated memory stabilization around ~62 MB RSS with zero memory leaks.
- **Process Hygiene:** Browser contexts and Chromium subprocesses cleanly terminated; zero orphan or zombie processes detected.
