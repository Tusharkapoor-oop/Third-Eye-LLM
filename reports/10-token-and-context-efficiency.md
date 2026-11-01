# Phase 10: Token and Context Efficiency

Tokenizer: **tiktoken `o200k_base`**, fixed for all measurements; `cl100k_base`
also recorded for tool schemas for cross-compatibility context needs.

## Tool schema overhead (the fixed cost of using the engine)

| Metric | Value | Gate | Verdict |
|---|---|---|---|
| 5-tool total schema, o200k | 680 | < 1000 | PASS |
| 5-tool total schema, cl100k | 655 | < 1000 | PASS |

## Returned-token budgets at runtime (R1: result payloads the model sees)

| Metric | Budget | Baseline | Post-fix |
|---|---|---|---|
| Max search-returned tokens per call | 600 | 345 (avg 76.5) | recorded in final run artifacts |
| Max extract-returned tokens per call | 1500 | 904 (avg 571.0, n=40) | recorded in final run artifacts |

## What changed and why it matters (optimization experiments — details in `reports/14`)

1. **Exact serialized budget enforcement** — the post-fix aggregator measures the
   actual `SearchResponse.to_dict()` serialization and trims rows/snippets until
   the real serialized size fits the caller's `max_tokens`. Baseline approximated
   per-item cost and could overflow guarantees; the fix makes the budget a hard
   property. Quality side effect verified by the answer-support gate comparison.
2. **Deep-research budget split** — facts capped at 70 % of budget; final report
   serialized and trimmed to fit `max_tokens`; previously the report could
   exceed its declared budget.
3. **Query cached results reuse** — aggregator TTL cache unchanged (1 h); cache
   tokens are never charged twice within a run.

## Tokens per CORRECT answer — the number that matters

The denominator is measured answer-support (`answer_supported_count`) on the
core 50-query set; total-returned-tokens come from the same run. This ratio is
computed in `reports/FINAL-AUDIT-REPORT.md` for baseline and post-fix runs from
the artifacts so that the headline number is never hand-written.

## What was NOT measured (declared)

- End-model-context consumption for full agent tasks (requires a live model
  loop; no Ollama/LM Studio/cloud model available on this machine — see
  `reports/08`). Schema + returned payload tokens are the observable proxy.
- Prompt-caching behavior of downstream clients.
