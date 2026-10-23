# ADR 0008: Reproducible benchmark with hard, failing gates

- Status: Accepted
- Date: 2026-10-21

## Context

It is easy to demo a search tool on a few happy-path queries and claim quality.
This project explicitly forbids fabricated measurements and uncalibrated
confidence. Latency, accuracy, and token claims need a committed dataset,
scripts, raw rows, and a failure mode that cannot be talked away.

## Decision

- Maintain a 58-query JSONL dataset across five categories, including
  unanswerable and conflicting queries.
- One command runs search, research, and a sample of extractions, with a fresh
  cache option.
- Record raw rows (URLs, timings, statuses, token counts) and a summary.
- Enforce gates: schema tokens, token-budget violations, citation spans,
  forbidden confidence fields, precision, top-3, answer support, no-result
  accuracy, and p50/p95 latency.
- Exit non-zero on any breach. Do not tune gate thresholds to make a run pass.
- Report raw counts alongside ratios.
- Keep result files in `benchmarks/results/` with the code that produced them.

## Alternatives considered

- **Ad-hoc timing in a notebook:** not reproducible and easy to select.
- **Unit tests only:** they cannot measure live-provider accuracy or latency.
- **LLM-as-judge:** adds cost, variance, and a second model to validate; a
  labelled term/domain check is weaker but transparent.
- **Soft warnings:** ignored in practice.

## Consequences

- The current run fails several gates. That is the intended behavior and is
  documented in the README and `LIMITATIONS.md`.
- Labelled-domain precision is harsh; it measures a narrow notion of
  "authoritative" and not human relevance.
- Live providers make runs non-deterministic; the dataset and scripts are
  deterministic, the network is not.
- A future keyed provider must be added to the same harness before it can be
  recommended.
