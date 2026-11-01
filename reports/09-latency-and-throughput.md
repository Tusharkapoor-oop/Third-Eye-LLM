# Phase 09: Latency and Throughput

A note on math. All west-of-1:00 latency figures below are wall-clock
`time.perf_counter()`/`time.time()`-based durations measured around the actual
network calls, aggregated from the runs listed. Percentiles computed by the
runner (`np.percentile`, default linear interpolation). Sample sizes are given;
p99 is **not** reported where the sample is too small to support it (<40 samples) —
reporting p99 on n=40 would be numerical noise.

## Search latency (the dominant cost)

| Run | Dataset | n | p50 | p95 | max |
|---|---|---|---|---|---|
| baseline (pre-fix) | 50q | 50 | 3.06 s | 9.94 s | — |
| baseline | 50q | 50 | *recorded in* `reports/baseline_benchmark_results.json` (p50 3.06s / p95 9.94s search) | | |
| final (post-fix) | 200q | 200 | *recorded in* `reports/benchmark_runs/final_200q_results.json` | | |

Unanswered rows are filled from the actual JSON artifacts at report-generation
time by `reports/14-optimization-experiments.md` §"generated tables"; no number
in the final report is typed by hand (`reports/FINAL-AUDIT-REPORT.md` includes
the computed values).

## Extraction latency

| Run | n | p50 | p95 |
|---|---|---|---|
| baseline | 40 | 5.91 s | 10.89 s |
| final 200q | recorded in the artifact | | |

## Provider-level latency (paired, same queries, interleaved)

The paired Tavily-vs-ddgs run measures raw provider latency on identical
queries. The merged per-provider statistics are computed in
`reports/11-quality-and-factual-accuracy.md` from the two run JSONLs
(`run_79ce051b.jsonl` + rerun remainder) — including timeouts and errors as
their true latency, never dropped (rule: outliers are flagged, never deleted).

## Stage decomposition (measured separately)

| Stage | Evidence anchor |
|---|---|
| Search provider call | paired run latencies |
| HTTP extraction + trafilatura + chunk + BM25 | `browser_vs_http.json` "http" rows (2.8–5.3 s incl. connection) |
| Headless browser launch + dump | `browser_vs_http.json` "browser" rows (9.2–18.7 s) |
| Playwright cold launch + navigate + render (weblens) | 3.23 s median incl. launch [smoke JSON] |
| Deep research (3 sub-queries multi-search + extraction) | live tests: 12.3–42.4 s for 3 deep-research cases [junit timings] |
| MCP tool schema size | 680 o200k / 655 cl100k tokens — see token report |

## Honest threat-to-validity

1. All runs on one network at one time of day; no time-of-day repeats exist.
2. Outliers were kept: the 2 timeouts in run_4ab70742 are included, not removed.
3. Live provider behavior (DDG scraping) is precarious by nature; numbers are
   comparable only within same-day runs.
4. Percentile cells marked "recorded in the artifact" are filled into the final
   audit report from the stored JSON at generation time; this intermediate file
   intentionally does not restate figures that could drift from the artifact.
