# ADR 0002: Deterministic evidence research; no LLM synthesis

- Status: Accepted
- Date: 2026-10-21

## Context

The system must not fabricate answers or uncalibrated confidence. A local LLM may
not be running, may be small, and may hallucinate. Hosted synthesis adds cost,
latency, and a new trust boundary. The caller is already a capable model; it
needs evidence, not a second prose answer.

## Decision

`deep_research` runs a deterministic loop:

1. Decompose the query into at most 4 variants.
2. Search in parallel.
3. Rank and fetch at most 6 pages (12 hard cap in the engine).
4. Select query-relevant passages, then verbatim sentences.
5. Return up to 8 findings (3 per domain), each with URL, fetch timestamp, and
   exact character span.
6. Report gaps, conflicts, stale-source warnings, and an explicit status.

No LLM, classifier, embedding model, or learned ranker is called. Ordering is a
documented lexical/keyword heuristic. Scores are never exposed.

Refusal guards are deterministic and run before or after fetching:

- `sensitive_query`
- `future_value_unknown:<year>`
- `proprietary_source_unavailable`
- `unverifiable_entity:<name>`
- `exact_value_not_found` / unsupported `exact`/`precise`
- `no_search_results`, `no_supported_claim`, `no_source_for:<term>`

## Alternatives considered

- **LLM synthesis with citations:** convenient, but unmeasured accuracy gain,
  extra latency, and a new hallucination path.
- **Vector reranking:** adds an embedding model and index; no labelled data yet
  to justify it.
- **Return search snippets only:** cheaper, but snippets are not exact spans and
  often lack the answer.

## Consequences

- Output is evidence, not an answer. The caller must synthesize.
- Recall is bounded by the search results and fetch cap.
- The guard rules can over-block and under-block; they are documented as
  heuristics, not guarantees.
- The approach is reproducible and cheap to audit, which matters more than
  fluent prose for this use case.
