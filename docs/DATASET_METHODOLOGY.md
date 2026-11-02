# Dataset Methodology (V9)

## Evaluation Principles
1. **Zero Fake Numbers**: All benchmarks run against live, actual systems with verifiable logs.
2. **Standardized Stratification**: 30 distinct categories covering general facts, programming, market disclosures, legal compliance, biomedical facts, multilingual inquiries, and adversarial injection.
3. **Paired Interleaved Execution**: Requests to Local WebLens, Deployed WebLens, and Tavily are interleaved and rotated to eliminate temporal and network congestion bias.
4. **Held-Out Integrity**: Test datasets are immutable, with SHA-256 hashes recorded in `manifest.json`.

## Datasets
- **Benchmark Suite**: `weblens-lab/datasets/eval_benchmark_suite.json` (SHA-256 `b8f3a9d16df1b3ca2f204f3717406f1eb4a79f4ba411d098daf222f67c0ca53c`)
- **Adversarial Suite**: `weblens-lab/datasets/adversarial_suite.json` (SHA-256 `2e99ebe5e4bbede2a964d6f4af1cb087d37efb4873d579fd0e77ba0ed3a17670`)
- **Manifest**: `weblens-lab/datasets/manifest.json`

