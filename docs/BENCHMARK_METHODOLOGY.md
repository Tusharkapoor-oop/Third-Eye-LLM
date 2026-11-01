# WebLens Benchmark Methodology & Statistical Evaluation Protocol

## 1. Evaluation Integrity Principles
WebLens benchmarks adhere to strict scientific rigor:
1. **Zero Fabrication:** No metric, sample size, or confidence interval may be typed by hand or estimated. Every number is derived from raw JSON execution records in `evidence/raw/` registered in `evidence/ledger.jsonl`.
2. **Quality-First Guard:** Speed and token reductions are only valid if quality metrics (answer support, precision, citation accuracy) do not regress beyond pre-registered margins.
3. **Paired Comparisons:** Comparisons between WebLens and Tavily are executed under identical conditions: identical queries, equal token caps, identical deadlines, and identical evaluation prompts.

---

## 2. Benchmark Datasets & Provenance

| Dataset Identifier | Path | Item Count | SHA-256 Digest | Description & Provenance |
|---|---|---|---|---|
| `dataset.core` | `weblens/benchmarks/queries.jsonl` | 58 | `442c7bfc90acc3aef89a22d17ebf24ec8a2b6e310ed10ceab32aa0df2ca9ccba` | Stratified general, technical, and multi-hop queries. |
| `dataset.root` | `benchmarks/eval_dataset.json` | 50 | `846b4de9b38de945821ad56e5bd4fa2375af9640164b9e9c2de6bf8245e32df1` | Frozen root lookup benchmark queries. |
| `dataset.expanded` | `benchmarks/eval_dataset_expanded.json` | 200 | `6130548dacb595da44a0973e66c4e3a44836846baf16a97ef1ca87664f2d065f` | Expanded multi-domain evaluation set with gold answers. |
| `dataset.paired` | `reports/tavily-comparison/data/stage7_dataset.jsonl` | 108 | `a4a64151fbdbda850a9de128bb7f83ec67f126b633aac42488c6f0b9296a9b21` | Paired WebLens vs. Tavily Direct comparison set. |

---

## 3. Statistical Formulations

### 3.1 Proportions: Wilson Score Interval
For binary proportions (e.g., answer support, detection recall, citation accuracy), we report the 95% Wilson score confidence interval without continuity correction:
$$\tilde{p} = \frac{\hat{p} + \frac{z^2}{2n}}{1 + \frac{z^2}{n}} \pm \frac{z}{1 + \frac{z^2}{n}} \sqrt{\frac{\hat{p}(1-\hat{p})}{n} + \frac{z^2}{4n^2}}$$
where $z = 1.95996$ for $\alpha = 0.05$. If $n < 30$, the metric is explicitly flagged with the caveat `(too small to support a claim)`.

### 3.2 Continuous Metrics: Non-Parametric Bootstrap CI
For continuous metrics (latency, tokens returned, tokens per correct answer), we compute the 95% confidence interval via 2,000 bootstrap resamples with replacement. We report the empirical mean, p50 (median), p95, and $[lo, hi]$ intervals.

### 3.3 Paired Hypothesis Testing
- **Binary Outcomes:** McNemar's paired test with continuity correction assesses differences between WebLens and Tavily on identical query items.
- **Continuous Outcomes:** Paired Student's t-test or Wilcoxon signed-rank test. Differences are considered statistically significant only when the 95% CI of the paired difference excludes zero.

