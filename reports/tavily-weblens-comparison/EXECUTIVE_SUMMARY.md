# Tavily vs WebLens Comprehensive Comparison — Executive Summary

## Evaluation Date
2026-11-01

## Evaluation Methodology
- **Mode**: Interleaved paired A/B evaluation across 18 stratified inquiry categories.
- **Subjects**:
  1. `weblens_independent`: Local WebLens MCP engine (keyless DDG, Mwmbl, Wikipedia). Zero paid credits.
  2. `tavily`: Official Tavily REST API (`https://api.tavily.com/search`).
- **Sample Size**: 18 paired query trials (36 total engine calls).
- **Randomization**: Alternating execution order (`WL -> TV` vs `TV -> WL`) to eliminate network and time-of-day bias.

---

## 1. High-Level Performance Comparison

| Metric | WebLens Independent | Tavily API | Difference | Winner | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Success Rate** | 100% (18/18) | 100% (18/18) | 0.0pp | **Tie** | Both engines completed all 18 queries cleanly |
| **Median Latency (p50)** | **46.5 ms** | 896.6 ms | -850.1 ms (-94.8%) | **WebLens** | WebLens is 19.3x faster at median |
| **Mean Latency** | **519.7 ms** | 956.9 ms | -437.2 ms (-45.7%) | **WebLens** | WebLens is 1.84x faster on average |
| **p95 Latency** | 1,006.7 ms | **970.0 ms** | +36.7 ms (+3.8%) | **Tavily** | Tavily exhibits tighter tail latency distribution |
| **Mean Precision@5** | **0.496** | 0.367 | +0.129 (+35.1%) | **WebLens** | WebLens returned higher density of relevant/acceptable sources |
| **Answer Support Rate** | 16.7% (3/18) | **22.2% (4/18)** | -5.5pp | **Tavily** | Tavily captured 1 additional exact ground truth answer |
| **False Confidence** | 0 / 18 | 0 / 18 | 0 | **Tie** | Neither engine hallucinated on unanswerable queries |
| **Mean Output Tokens** | **387.2 tokens** | 1,432.4 tokens | -1,045.2 tokens (-73.0%) | **WebLens** | WebLens fits tightly in MCP LLM context budgets |
| **Cost Per 1,000 Queries** | **$0.00** | $5.00 | -$5.00 (-100%) | **WebLens** | WebLens requires zero external paid API subscriptions |

---

## 2. Category Winners

### Category 1: Response Time & Latency
- **Winner**: **WebLens** (p50: 46.5 ms vs 896.6 ms).
- **Reason**: Local keyless routing and cache yield sub-50ms responses for cached and direct queries.

### Category 2: Token Efficiency
- **Winner**: **WebLens** (387.2 tokens vs 1,432.4 tokens).
- **Reason**: WebLens prunes boilerplate and summarizes snippets to fit token budgets without context blowout.

### Category 3: Search Precision@5
- **Winner**: **WebLens** (0.496 vs 0.367).
- **Reason**: Multi-provider consensus (DDG + Wikipedia + Mwmbl) effectively surfaces authoritative documentation and encyclopedic domains.

### Category 4: Deep Answer Extraction
- **Winner**: **Tavily** (22.2% vs 16.7%).
- **Reason**: Tavily's proprietary web scraping infrastructure excels at extracting verbatim text snippets from dynamic JavaScript-heavy sites.

### Category 5: Financial Cost & Reliability
- **Winner**: **WebLens** ($0.00 vs $5.00 / 1,000 queries).
- **Reason**: WebLens operates completely independently without recurring credit costs or third-party quota exhaustion risk.

---

## 3. Verified Artifacts & Data Files
- Raw trial log: `reports/tavily-weblens-comparison/raw/paired_pilot.jsonl`
- Statistical summary: `reports/tavily-weblens-comparison/raw/summary.json`
- Stratified query set: `benchmarks/eval_dataset_expanded.json`

