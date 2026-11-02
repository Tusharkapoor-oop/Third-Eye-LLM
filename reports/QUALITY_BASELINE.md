# WebLens Quality Baseline Report

## 1. Executive Summary

This report establishes the verified empirical quality baseline for WebLens across its two deployment targets (System 1: Local WebLens MCP and System 2: Deployed WebLens MCP on Cloud Run) and its commercial benchmark comparator (System 3: Tavily Direct API).

Measurements are derived directly from the 100-query stratified benchmark (`benchmarks/eval_dataset_expanded.json`, SHA-256 `6130548dacb595da44a0973e66c4e3a44836846baf16a97ef1ca87664f2d065f`) evaluated under the preregistered corrected scoring harness (`evidence/prereg-v10-001-scoring-fix.md`).

---

## 2. Quantitative Baseline Matrix

| Metric | System 1: Local WebLens | System 2: Deployed WebLens | System 3: Tavily Direct | Verification Status |
|---|---|---|---|---|
| **Queries Evaluated** | 100 | 100 | 100 | **Verified** |
| **p50 Latency (ms)** | 3,548.8 | **1,094.0** | 2,001.1 | **Verified** |
| **p90 Latency (ms)** | 3,623.7 | **1,395.8** | 2,651.2 | **Verified** |
| **p95 Latency (ms)** | 3,678.3 | **1,590.8** | 2,803.6 | **Verified** |
| **Mean Latency (ms)** | 3,571.5 | **1,159.9** | 2,044.1 | **Verified** |
| **Mean Tokens / Query** | **297.4** | 425.5 | 1,486.6 | **Verified** |
| **Answer Support Count** | 56 / 100 (56.0%) | 87 / 100 (87.0%) | **90 / 100 (90.0%)** | **Verified** |
| **Mean Precision@5** | 0.431 | 0.687 | **0.786** | **Verified** |
| **False Confidence Flags** | 5 / 10 | 6 / 10 | 9 / 10 | **Verified** |
| **Total Credits Consumed** | **0.0 credits** | **0.0 credits** | 100.0 credits | **Verified** |
| **Total Cost (USD)** | **$0.00** | **$0.00** | $0.50 | **Verified** |

---

## 3. Analysis of Baseline Findings

### 3.1 Latency Advantage (System 2: Deployed WebLens)
- Deployed WebLens running on Google Cloud Run achieves a p50 latency of **1,094.0 ms**, representing a **1.83x speed advantage over Tavily Direct API** (2,001.1 ms).
- At the tail (p95), Deployed WebLens delivers results in **1,590.8 ms** compared to Tavily's **2,803.6 ms** (1.76x tighter tail latency).
- Local WebLens experiences higher latency (3,548.8 ms p50) due to consumer residential ISP egress constraints and local rate throttling on keyless providers.

### 3.2 Factual Answer Support
- Tavily achieves 90.0% answer support (90/100 items).
- Deployed WebLens achieves **87.0% answer support** (87/100 items) using entirely keyless upstream search infrastructure.
- Local WebLens achieves 56.0% answer support, reflecting stricter rate limiting on consumer residential IP addresses compared to Google Cloud's data center network egress.

### 3.3 Token Efficiency & Cost
- Deployed WebLens consumes **425.5 mean tokens per query**, cutting downstream LLM token consumption by **71.4%** compared to Tavily Direct (1,486.6 mean tokens).
- Operating cost for WebLens across both local and deployed environments is **$0.00** with 0 API credits consumed, whereas Tavily consumed 100.0 credits ($0.50) for the 100 queries.

---

## 4. Verification Evidence & Hashes

- Raw Results JSONL: `reports/three-system-comparison/v10-cycle0-corrected-scorer/three_system_results.jsonl`
- Summary JSON: `reports/three-system-comparison/v10-cycle0-corrected-scorer/summary.json`
- Verification Status: **Verified** (Reproduced via `weblens-lab/evaluations/run_three_system_benchmark.py`).

