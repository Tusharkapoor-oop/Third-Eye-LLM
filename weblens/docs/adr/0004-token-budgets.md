# ADR 0004: Hard token budgets on final serialized payloads

- Status: Accepted
- Date: 2026-10-21

## Context

The client's context window is the scarce resource. A budget that counts only
passage text is misleading: the JSON envelope, URLs, timestamps, spans, warnings,
and the `tok` field itself all consume tokens. Different tokenizers give
different counts, so an unnamed "token" number is not reproducible.

## Decision

- Use `tiktoken` `cl100k_base` and name it in every report.
- Enforce the caller's `max_tokens` on the **final serialized payload**,
  including `ms`, `tok`, warnings, and cutoff flags.
- Reserve 6 tokens for the `tok` field while filling the payload.
- Truncate a passage first, then drop passages; if even the envelope cannot fit,
  mark `budget_exhausted`.
- Default budgets: search 600, extract 1,500, research 2,000. Floors: search
  120, extract 200, map 200, crawl 300, research 300. Below-floor requests are
  `bad_input`.
- Default result count is 5; the caller can lower or raise it within 1–10.

## Alternatives considered

- **Approximate character budgets:** cheaper to implement, but model-dependent
  and easy to breach.
- **Count only content fields:** understates real context cost.
- **No hard budget:** risks flooding the caller and hiding the cost.
- **`o200k_base`:** larger vocabulary, but `cl100k_base` is widely supported and
  was already used for the schema measurement.

## Consequences

- Token counting costs CPU and requires the tokenizer file on first use (a
  cold-start cost, measured separately).
- Budgets are conservative for tokenizers with larger vocabularies.
- Every response reports `tok` and `cut` so the caller can see what happened.
- Token counts are not comparable to a different model's tokenizer without
  re-counting.
