# Phase 05: Benchmark Dataset Documentation

This audit uses two version-controlled labelled datasets plus one paired subset.
All are human-writeable JSON with deterministic content; every file hash is
recorded in the evidence database when a run imports it.

## A. `benchmarks/eval_dataset.json` — core labelled set (50 queries)

| Stratum (category) | Count | Notes |
|---|---|---|
| current_facts | 10 | stable "current" facts, verifiable answer text |
| documentation_lookups | 10 | exact API/doc answers (flags, operators, commands) |
| niche_technical | 10 | rare identifiers (PEP numbers, RFC numbers, registers) |
| unanswerable_or_fabricated | 10 | non-existent products/events, impossible questions |
| conflicting_or_debatable | 10 | topics where sources genuinely disagree |

Fields per item: `id, query, ground_truth_answer, acceptable_sources[],
is_unanswerable, has_conflict`. Gold answers were written per item, not
derived from any system's output — no circular ground truth.

## B. `benchmarks/eval_dataset_expanded.json` — expanded set (200 queries)

| Stratum | Count | Purpose |
|---|---|---|
| current_facts | 28 | broad factual recall |
| documentation_lookups + technical_documentation + current_official_docs | 49 | doc retrieval |
| programming_debugging | 20 | error-message search quality |
| academic_scientific | 20 | pull-of-reference sources |
| product_comparison | 10 | comparison-query handling |
| multi_source_research | 10 | synthesis-style queries |
| exact_phrase_search | 10 | verbatim string retrieval |
| ranking_extraction_weakness | 9 | probes where ranking/extraction previously failed |
| long_tail / ambiguous_questions | 10 | rare + underspecified inputs |
| niche_technical | 10 | rare identifiers |
| unanswerable_or_fabricated | 15 | no-good-answer detection |
| conflicting_or_debatable | 21 | conflict handling |
| pages_poor_html / javascript_heavy_pages / pages_return_errors | 6 | extraction-path stress |

## C. `benchmarks/tavily_paired_subset.json` — pre-registered paired subset (40 queries)

Deterministic, hash-ordered stratified sample of the core set (8 per category)
created **before any Tavily run was performed**; Tavily credits are spent only on
this subset so every Tavily comparison is paired on identical queries with ddgs.

## Label protocol and honesty statement

1. Gold answers + acceptable source domains were authored directly, each stating
   the correct answer (or "does not exist" for unanswerable, or the two sides for
   conflicts). Time-sensitive items concern stable facts only.
2. Scoring in `run_benchmarks.py` (`check_answer_contained`) is a **token-overlap
   heuristic against gold answers** — exact-match, 4+-digit numeric match, or
   ≥50% of gold tokens present in the returned evidence. This is a *strict but
   mechanical* rubric; it can false-negative when a passage expresses the same
   fact differently. Numerator/denominator are always reported.
3. The engine is prevented from "self-answering": the evaluator checks only
   whether the returned evidence contains the gold content — no model judge
   biases the number, no confidence score is emitted by the engine
   (`zero_uncalibrated_scores` gate is permanently true — verified each run).
4. Limitations: no blind model-judge and no human kappa exist in this audit;
   quality figures should be read as *heuristic rubric* numbers. A human
   spot-check list of the 10 weakest items is included in
   `reports/11-quality-and-factual-accuracy.md`.
5. Any post-run edit to these three files would be a protocol violation; current
   SHA-256 hashes of all three are stored in the test-evidence database (imported
   during `record-benchmark`).

## Known weaknesses of the datasets (declared)

- The sets emphasize lookup-style questions; deep multi-hop research with
  checkpoints is not labelled here (roadmap item).
- All queries in English; multilingual strata absent (roadmap item).
- `acceptable_sources` domains are heuristics, some too permissive (e.g.
  `github.com` for generic tech questions), so precision is measured post-hoc
  per-result rather than per-domain.
