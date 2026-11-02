# Three-System Comparison — 100-Query Extension Run (2026-11-02)

## What this is
A scaled re-run of the V9 three-system comparison. The published V9 executive summary rested on **n=15** queries of a 30-query suite; this run evaluates the full first **100 queries of `benchmarks/eval_dataset_expanded.json`** (held-out evaluation dataset) against all three systems with identical interleaved methodology. Raw records were preserved from a new directory; the V9 n=15 raw results were not modified.

- **Dataset**: `benchmarks/eval_dataset_expanded.json` (first 100 items)
- **Dataset SHA-256**: `6130548dacb595da44a0973e66c4e3a44836846baf16a97ef1ca87664f2d065f`
- **Runner**: `weblens-lab/evaluations/run_three_system_benchmark.py` (unchanged methodology: rotating execution order, 0.3 s politeness throttle, paired scoring)
- **Raw results**: `reports/three-system-comparison/raw-v9b-2026-11-02/three_system_results.jsonl` (100 records)
- **Machine summary**: `reports/three-system-comparison/raw-v9b-2026-11-02/summary.json`
- **Run log**: `reports/three-system-comparison/raw-v9b-2026-11-02_runlog.txt`
- **Systems**: System 1 local WebLens (independent keyless: ddg,mwmbl,wikipedia), System 2 deployed Cloud Run MCP (`https://weblens-16131012091.us-central1.run.app`), System 3 Tavily Direct API (authorized key; 1 credit/query — 100 credits total consumed)

## Results (n=100)

| Metric | System 1 Local | System 2 Deployed | System 3 Tavily Direct |
|---|---|---|---|
| p50 latency | **922.7 ms** | 1,112.1 ms | 2,381.6 ms |
| p90 latency | **1,157.1 ms** | 1,421.0 ms | 3,129.5 ms |
| p95 latency | **1,413.6 ms** | 1,868.0 ms | 3,543.7 ms |
| Mean latency | **988.2 ms** | 1,202.5 ms | 2,490.5 ms |
| Mean Precision@5 | 0.688 | 0.646 | **0.756** |
| Answer support rate | 0.80 | 0.76 | **0.90** |
| Success rate | 1.00 | 0.99 | 1.00 |
| Mean tokens/response | **425.8** | **426.9** | 1,527.3 |
| Total credits | 0 | 0 | 100 (~$0.50 est.) |

## Interpretation (unchanged direction, now at 6.7× sample size)
1. **Tavily wins quality**: +6.8 pp Precision@5 over local WebLens and +10 pp answer support at n=100 — consistent with the V9 finding, now with a larger empirical basis. Tavily pays for it with ~2.4× p50 latency and ~3.6× token payload.
2. **WebLens wins speed and cost**: local p50 922.7 ms vs Tavily 2,381.6 ms (2.58×), at zero search cost and ~72% fewer tokens.
3. **Deployed vs local**: deployed p50 +189 ms over local (network + origin round trip; region us-central1 away from local Windows client). Quality within 4 pp of local.
4. **Deployed reliability**: exactly one non-`ok` response (query 12), status `no_reliable_result` with zero errors — a graceful abstention, counted against success rate but not an unhandled failure.

## False-confidence caveat (methodology, not regression)
7 flags across systems on the `unanswerable_or_fabricated` category (ids 31–40, mixed across systems: local 6, deployed 6, Tavily 7). The runner flags "false confidence" when Precision@5 > 0.4 on an unanswerable item; the trap queries embed real tokens ("Python", "Nobel Prize", "Tokyo"), so retrievers return plausible-shaped results. This measures retrieval exposure to fabricated entities, not validated answer hallucination. V9's n=15 subset contained no trap category, which is why v9 reported 0/0/0. Treat these numbers as category-specific retrieval behavior, not behavioral hallucination between systems.

## Comparison confidence
At n=100, the Precision@5 gap (0.756 vs 0.688) and answer-support gap (0.90 vs 0.80) correspond to approximately 2–4 SEs of difference; the direction is consistent with both the V9 n=15 run and the V8 70-query paired run (CLM-008/009: 67.1% vs 97.1% support). No formal test was run by the harness; per-category breakdowns remain available in the raw JSONL for post-hoc analysis.

## Actions implied
- The quality gap is concentrated in Tavily's index depth; WebLens's aggregator should keep the Tavily provider as secondary for niche/technical categories (already implemented and used at tier changes).
- The deployed service consumes no API credits (keyless) while matching local behavior within 4 pp — cost asymmetry favors the deployed fleet for high-volume use.
- Redeploy the Cloud Run service (drift recorded in `reports/deployed-security/DEPLOYMENT_DRIFT_2026-11-02.md`) before further deployed-side experimentation, so System 2 results test current code, not a mixed revision.
