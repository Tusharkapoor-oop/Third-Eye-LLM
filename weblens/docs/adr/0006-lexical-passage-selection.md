# ADR 0006: Lexical passage retrieval, no exposed score

- Status: Accepted
- Date: 2026-10-21

## Context

Passages must be relevant to the query and cheap to compute locally. A learned
reranker or embedding model adds dependencies, memory, latency, and a
calibration problem. The system must not return a "relevance score" that looks
like a probability but is not.

## Decision

Select passages with a deterministic lexical scorer:

- BM25 over query terms, plus phrase, heading, and early-position priors.
- Prefer chunks that cover the full query; require a minimum term coverage.
- Strip headings and bullets from the final claim, but keep the heading as
  metadata.
- Return exact `[start, end]` spans into the cleaned text.
- Never expose a numeric score. Ordering is a heuristic; the caller sees only
  the ordered passages and the evidence status.

License queries get a special exact-span candidate because license names often
span newlines and are not single sentences.

## Alternatives considered

- **Embedding similarity:** better semantic recall in principle, but unmeasured
  on the 58-query set and adds a model/index.
- **LLM passage selection:** expensive per query and non-deterministic.
- **Return full page text:** simple, but expensive and noisy.
- **Expose BM25 scores:** creates false confidence and is not comparable across
  queries.

## Consequences

- Synonyms and paraphrases are missed. Query expansion is limited to a few
  deterministic variants.
- Exact spans are reproducible for a given cleaned text, but a changed page
  invalidates them.
- The approach is fast, offline, auditable, and has no model download.
- Revisit only when a labelled reranking set shows a measured gain over BM25.
