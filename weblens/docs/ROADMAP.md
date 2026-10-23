# Roadmap

This roadmap is ordered by the project's stated priorities: no fake accuracy,
accuracy, tokens, then latency. Items without a measurement plan are not
promises.

## P0 - close the measurement gaps

1. **Run a keyed provider on the same dataset.** Add `BRAVE_API_KEY` or
   `TAVILY_API_KEY`, run `benchmarks.run` against the 58 queries, and publish a
   raw result file. Success criterion: improve labelled-domain precision and
   top-3 while keeping search p95 under 5 s and zero budget/citation violations.
   If neither provider wins, keep the keyless default and say so.
2. **Add human relevance labels.** A second judgment per answerable query
   (`relevant`, `partially relevant`, `irrelevant`) plus a short reason. Report
   both labelled-domain precision and human precision; do not merge them.
3. **Report cold and warm latency.** Cold start is measured in
   `benchmarks/results/2026-10-23_cold_start.*` (low CPU load, high disk
   activity). Search envelopes are not cached yet; add the TTL cache in item 11,
   then run the same 58 queries against a warm cache. Keep the cold run as the
   conservative gate.
4. **Re-run the headline configuration.** `2026-10-21_final2` is the current
   headline and still fails three gates. A keyed provider and repeated runs in
   different network windows are needed to separate provider variability from
   router quality.

## P1 - accuracy and evidence quality

5. **Conflict detection with data.** Expand the conflicting set to at least 30
   queries covering numbers, dates, versions, and ranges. Only then change the
   detector. Target: recall at least 0.6 with no more than one false positive on
   the answerable set.
6. **Answer-support evaluation beyond term containment.** Add a small manually
   scored rubric (does the finding answer the question?) and report inter-rater
   agreement if a second reviewer is available.
7. **No-result calibration.** Add adversarial unanswerable queries with real
   pages, jokes, near-miss entities, and numeric lookalikes. Keep the current
   0.9 subset result honest; do not generalize it.
8. **Provider-specific parsing tests.** Record sanitized fixtures for DDG,
   Mwmbl, and Wikipedia so parser regressions are caught offline.

## P2 - latency and UX

9. **Early-return fusion.** Return once the primary provider supplies the
   requested number of results and a short grace period expires, instead of
   waiting for every low-priority provider. Measure accuracy before/after; do
   not adopt on latency alone.
10. **Hedge slow providers.** Start a secondary path only after the primary
    misses its p50, with a strict cap. Measure duplicate work and provider
    throttling.
11. **Warm-cache fast path.** Cache full search envelopes (not only HTTP
    responses) with a short TTL and expose `cache_age_s` so callers know the
    freshness. Measure hit rate and staleness.
12. **Stream progress for research.** MCP progress notifications could make a
    15-19 s research call less opaque, but the current SDK/client support must
    be verified first; do not invent a protocol feature.

## P3 - security and operations

13. **Browser isolation or removal.** The optional browser path does not pin DNS
    to a validated IP. Either run Chromium behind a network namespace or proxy
    that enforces egress policy, or remove the browser path. Do not call it
    SSRF-safe before then.
14. **Cache size limit and purge command.** Add a configurable byte cap and a
    `weblens cache purge` command that deletes only the WebLens database.
15. **Per-client rate limit for HTTP.** A token bucket on tool calls; useful when
    more than one local client shares one provider quota.
16. **Official MCP conformance run.** Use the official suite where available;
    publish the exact version and failures. Until then, keep the message-level
    claims in `PROTOCOL.md`.

## P4 - packaging and portability

17. **Linux/macOS smoke tests.** The code is OS-independent, but only Windows 11
    was measured. Add CI jobs for Ubuntu and macOS and record any platform
    differences.
18. **Single-file Windows installer (optional).** Only if users cannot run
    `uv`. PyInstaller/Nuitka packaging increases size and AV false positives;
    measure startup and binary size first.
19. **Client examples.** Add tested configs for Roo Code, Cline, Continue,
    Claude Desktop, and one HTTP client. Keep them in `docs/CLIENTS.md` until a
    client-specific file is verified.

## Explicitly not planned

- **LLM answer synthesis in the server.** It duplicates the caller, adds
  hallucination risk and cost, and was not measured to improve support.
- **A vector database or embedding reranker.** No labelled data justifies it.
- **Unbounded crawling or a search-engine-scale index.** Out of scope and
  hostile to small sites.
- **Scraping providers that disallow it in `robots.txt`.** Use their official
  API or omit them.
- **Tuning gate thresholds to make the current run green.** Fix the behavior or
  document the miss.

## Definition of done for v0.2

- One keyed provider measured on the same dataset, with raw rows.
- Human relevance column added and reported separately.
- Cold and warm latency reported.
- Conflict recall measured on at least 30 labelled cases.
- Final full run and final cold-start run committed.
- No unmeasured claim in the README, report, or comparison matrix.
