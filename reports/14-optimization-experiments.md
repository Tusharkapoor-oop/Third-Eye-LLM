# Phase 14: Optimization Experiment Ledger

Each experiment lists: hypothesis, baseline evidence, change, result, decision.
Commit-side note: all changes live in the working tree on top of commit
`b531618`; this is recorded so any future commit can be diffed precisely.

## EXP-1 — Insecure token-budget approximation

- **Hypothesis**: enforcing budgets against approximate text (title+url+snippet +
  20-token wrapper allowance) lets real serialized responses exceed declared
  budgets; measuring the true serialized JSON removes the overflow while
  preserving answer quality.
- **Observed baseline bug**: baseline "capital of France" search exceeded the
  search-token budget (junit test failure at `b531618`).
- **Change**: `aggregator.py` budget path replaced by `calc_resp_tokens()` that
  serializes the candidate `SearchResponse.to_dict()` with the o200k tokenizer;
  rows are appended while budget holds; on overflow the candidate's snippet is
  trimmed by the excess delta, then final overflow trims by popping rows.
- **Result**: token-boundary tests pass on the full 237-test rerun; regression
  gates hold on the post-fix runs (see `reports/15`).
- **Decision**: **RETAIN**

## EXP-2 — Injection-detection regex gap

- **Hypothesis**: reusing the richer weblens pattern scanner as a fallback when
  the root's fast regex raises detection coverage to that of the stricter stack
  without measurable latency cost on benign text.
- **Observed baseline bug**: 10 of 27 injection probes missed (role hijack,
  exfiltration, concealment, encoded payloads).
- **Change**: `security.py:sanitize_untrusted_content()` now falls back to
  `src/weblens/security/injection.py:scan_injection` when the fast regex finds
  nothing.
- **Result**: 27/27 injection tests pass (measured by full-suite rerun).
- **Decision**: **RETAIN**

## EXP-3 — Crawler trap-detection gap

- **Hypothesis**: `/tag/tag/tag/` escapes detection only because the check sits
  inside a dead branch; moving it out is a pure-logic fix.
- **Change**: `crawler.py` — consecutive-identical-segments detection now runs
  unconditionally before other checks.
- **Result**: all 20 trap tests pass.
- **Decision**: **RETAIN**

## EXP-4 — Deep-research token overrun

- **Hypothesis**: reserving 30 % of the budget for synthesis/metadata and
  enforcing a serialized-report ceiling keeps `deep_research` within its
  declared token budget without losing answer presence.
- **Change**: `deep_research.py` — facts budget = 70 % of max; report JSON
  serialized with `o200k` and facts popped until the ceiling holds; summaries
  trimmed to first sentences.
- **Result**: 3 live deep-research tests pass with budgets respected; report
  token counts returned from within-budget serialization.
- **Decision**: **RETAIN**

## EXP-5 — Windows browser-fallback decoding crash

- **Hypothesis** (discovered during this audit): `subprocess.run(text=True)`
  without an explicit encoding decodes browser output with cp1252, crashing on
  UTF-8 DOM dumps (observed: `UnicodeDecodeError: byte 0x9d` on react.dev).
- **Change**: `browser_fallback.py` passes `encoding="utf-8", errors="replace"`.
- **Measured retest**: react.dev ok=True, 272,503 bytes, 20.15 s end-to-end.
- **Decision**: **RETAIN**

## EXP-6 — Tavily as an opt-in provider

- **Hypothesis**: wiring the MIT Tavily SDK/REST call behind `is_available()`
  improves the engine's* keyed backend option without altering the keyless
  default path.
- **Change**: `TavilySearchProvider` registered in the aggregator when a key
  exists; also wired into the benchmark harness for the paired comparison.
  Harness `.env` preloading added after the harness run lost its key between
  sessions (resumability fix).
- **Result**: paired tavily/ddts run completed on the pre-registered 40-query
  subset (two run files);  exactly the number of successful Tavily search calls across both paired
  runs (each = 1 credit); the merged comparison and exact call counts are in
  `reports/11-quality-and-factual-accuracy.md`].
- **Decision**: **RETAIN**

## EXP-7 — Browser-vs-HTTP routing probe measured

- **Hypothesis**: direct HTTP should remain first; the browser fallback should
  only trigger on genuinely client-only pages.
- **Measured evidence**: `reports/07-browser-vs-http-benchmarks.md` — HTTP ties
  or wins 2.2×–5.4× on SSR-capable real pages; browser unique value on
  client-only fixtures.
- **Decision**: **RETAIN existing routing** (change rejected as unnecessary; a
  browser-pooling speedup is PROPOSED-only, below).

## PROPOSALS — evaluated, recorded, NOT implemented in this audit

- Proxy-validated egress inside the root browser fallback (borrow weblens's
  egress proxy): **PROPOSAL**. Security win; latency cost unknown at this scale.
- Browser process pooling for the headless fallback to eliminate the 9–19 s
  fresh-launch cost: **PROPOSAL**; biggest measured latency opportunity.
- SearXNG as a keyless multi-engine provider: **BLOCKED** (JSON API 403 until
  server config is changed by the user).
- Retry/backoff for search providers: rejected for now — no measurable provider
  transient above 2 timeouts/91 queries in sampled runs; revisit if tail
  failures grow.

## REJECTED during the audit

- Rearchitecting the duplicated three-stack codebase (src/, weblens/, webintel/)
  in this audit: rejected — out of scope for a behavior-preserving audit; noted
  in the roadmap.
- Blended single-score reporting: rejected by design; Pareto tables only.
