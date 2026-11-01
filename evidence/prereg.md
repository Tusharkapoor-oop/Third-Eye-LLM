# Pre-Registration Plan: WebLens vs Tavily Master Evaluation

**Date:** 2026-11-01  
**Specification Version:** v6 Master Protocol  
**Repository Commit:** 902415d49f8da502b9de0e1c78da7f5777a1d2f8  

---

## 1. Hypotheses Under Test

- **H1 (Efficiency & Token Footprint):** WebLens keyless extracts bounded lexical passages resulting in at least a 2x reduction in context tokens compared to unbudgeted document extraction, without losing essential answer support on standard factual queries.
- **H2 (Retrieval Quality):** Tavily Direct API achieves higher top-5 retrieval precision and answer support than WebLens keyless on broad web and news queries due to proprietary index freshness and scoring.
- **H3 (Hybrid Optimization Layer):** WebLens backed by Tavily (`weblens-tavily`) recovers Tavily's retrieval recall while bounding returned tokens to pre-configured agent budgets.
- **H4 (Conflict Detection Deficiency):** WebLens conflict detection recall is an open deficiency (previously measured at 0/18), failing to systematically surface contradictory sources.
- **H5 (Network Egress Enforcement):** WebLens DNS-pinned egress proxy reliably blocks loopback, link-local, private IP addresses, and DNS-rebinding fixtures without leaking requests.

---

## 2. Pre-Registered Gates and Performance Thresholds

1. **Search Latency Gate:**
   - Median (p50): <= 1,500 ms (1.50 s)
   - 95th Percentile (p95): <= 5,000 ms (5.00 s)
   - Gate status remains fixed; thresholds cannot be altered after observing data.

2. **Quality-First Guard Rule:**
   - Any claim of efficiency, latency, or cost victory is invalid unless quality non-inferiority is established on identical paired queries.
   - Non-inferiority threshold: Answer support difference lower CI bound >= -0.02 (-2.0 percentage points); false-confidence rate <= +0.01 (+1.0 percentage point).
   - If not yet measured or if CI exceeds threshold, guard status is `NOT_ESTABLISHED` or `VIOLATED`.

3. **Classification of Efficiency Wins:**
   - `ACHIEVED_10X`: Ratio >= 10.0 and 95% CI lower bound >= 10.0.
   - `PARTIAL`: Ratio between 2.0 and 10.0.
   - `TIE_OR_WORSE`: Ratio < 2.0.

---

## 3. Dataset Registry and Cryptographic Hashes

| Corpus Name | Path | Size (Bytes) | SHA-256 Digest | Purpose |
|---|---|---:|---|---|
| Hand-Labelled Benchmark | `reports/tavily-comparison/data/stage7_dataset.jsonl` | 52,776 | `a4a64151fbdbda850a9de128bb7f83ec67f126b633aac42488c6f0b9296a9b21` | Paired gold-standard accuracy evaluation (81 dev / 27 test) |
| Expanded Eval Dataset | `benchmarks/eval_dataset_expanded.json` | 75,742 | `6130548dacb595da44a0973e66c4e3a44836846baf16a97ef1ca87664f2d065f` | 200 extended general QA queries |
| Paired Tavily Subset | `benchmarks/tavily_paired_subset.json` | 14,425 | `ecb14a073716808d993f709ce4e78769bdc31c4009863b67fd68e3b504f767b8` | 40 paired queries within credit budget |
| WebLens Core Regression | `weblens/benchmarks/queries.jsonl` | 15,793 | `442c7bfc90acc3aef89a22d17ebf24ec8a2b6e310ed10ceab32aa0df2ca9ccba` | 58 regression cases (conflicts, no-result, syntax) |
| Root Eval Benchmark | `benchmarks/eval_dataset.json` | 16,621 | `846b4de9b38de945821ad56e5bd4fa2375af9640164b9e9c2de6bf8245e32df1` | 50 human-written factual queries |

*Note: The synthetic 10,000 query dataset (`reports/_archive/prior-run-20261027/extreme-benchmark/datasets/extreme_benchmark_10k.jsonl`, SHA-256 `d1d91fe1e7289affb0a85a0a412c6a9d47dbbde2ea5e994566dcd2aa1ba1c5ba`) is formally excluded from accuracy scoring due to placeholder claims and template artifacts.*

---

## 4. Systems Under Test and Configurations

- **S0 (WebLens Keyless):** Providers: `ddg,mwmbl,wikipedia`; mode: `fuse`; browser fallback: disabled by default; local SQLite cache enabled.
- **S2 (WebLens + Tavily):** Providers: `tavily`; mode: `single`; output budget: 600 search tokens / 1500 extract tokens.
- **S3 (Tavily Direct API):** Endpoint `https://api.tavily.com/search`, `include_answer=False`, `search_depth="basic"`, `max_results=5`.
- **S5 (Root Stack WebIntel Keyless):** `src/engine/search/aggregator.py` default providers.
- **S1 (WebLens + SearXNG):** `BLOCKED` (SearXNG container offline).
- **Controls:**
  - C0 (Null Control): Returns empty result `[]`. Floor anchor (0.0 support, 0.0 precision).
  - C1 (Random Control): Returns random unrelated URL and text. Floor anchor.
  - C3 (Oracle Control): Injects gold ground-truth URL and passage text. Ceiling anchor (1.0 support, 1.0 precision).

---

## 5. Statistical Methodology

1. **Binary Proportions (Accuracy, Support, Abstention, Security Block Rates):**
   - Calculated with Wilson score 95% confidence intervals.
   - For comparisons on identical queries, paired McNemar test is computed.

2. **Continuous Variables (Latency, Tokens, Cost, Ratios):**
   - Bootstrap resampling (fixed seed `20261101`, 10,000 resamples) for means, medians, and difference intervals.
   - Sample sizes n < 30 are explicitly labelled as "too small to support a claim".

3. **Multiple Testing Correction:**
   - Benjamini-Hochberg false discovery rate (FDR) control applied across multi-slice family tests.

4. **Budgets and Independent Witness Verification:**
   - Tavily API spending strictly capped at 60% of available quota (max 600 credits).
   - Authoritative credit consumption verified via `https://api.tavily.com/usage` witness before and after paid runs.
