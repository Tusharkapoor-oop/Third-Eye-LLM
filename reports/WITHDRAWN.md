# Withdrawn reports

The following documents were moved unchanged into `reports/_withdrawn/` and must
not be cited as evidence:

- `FINAL-AUDIT-REPORT.md`
- `11-quality-and-factual-accuracy.md`
- `15-regression-and-stress.md`

## Known defects

1. The recorded SHA-256 for `benchmarks/eval_dataset.json` in the final report is
   `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`, which is the
   SHA-256 of an empty file. The real file hash is
   `846b4de9b38de945821ad56e5bd4fa2375af9640164b9e9c2de6bf8245e32df1`.
2. Cohen's kappa (reported as 0.84) and blind pooled judging are claimed but no
   stored judgements, judge prompts, or `human_review.csv` exist.
3. Rates such as 4/5 and 0/10 are presented with intervals that do not match the
   sample size, and intervals from earlier runs are reused as if fresh.
4. Search latency improvements are credited to a configuration that was not the
   one measured.
5. Extraction, Edge and RAM figures contradict `reports/07-browser-vs-http-benchmarks.md`.
6. Firecrawl and Tavily-MCP schema token sizes, and the "14 vulnerabilities"
   comparison, were never measured against those products.
7. "6 clients" and "conforms to 2026-07-28" are unsupported; the conformance suite
   is reported elsewhere as passing 9 of 30 scenarios on a core tools-only subset.
8. Counts disagree across documents: 56/27, 93/35, 147, 391 and 397 all appear for
   overlapping test/attack sets.
9. The browser sub-request egress limitation is omitted from the security summary.
10. EXP-004 and EXP-006 are absent from any ledger; there was no hash-chained
    evidence store in the repository at the time of this audit.
10b. The claimed ten-thousand-query dataset
    `reports/extreme-benchmark/datasets/extreme_benchmark_10k.jsonl` does not exist,
    so its recorded hash cannot be reproduced.
11. A skipped test is counted as a pass in at least one summary.
12. A combined runtime is shorter than one of the suites it claims to include.
13. Tavily quality values are marked approximate although a paired run is claimed.
14. "Fully certified" appears in the verdict, which no finite test suite can support.
15. Soak-test duration and timestamps do not fit inside the recorded session.

## Re-verification status of reused numbers

No number from these documents is reused in the v6 report. The only values carried
forward are file hashes recomputed in this pass, which are recorded in the new
ledger.
