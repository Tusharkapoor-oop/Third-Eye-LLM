# Limitations and non-claims

This file is the honest boundary of the implementation. If a claim is not here
or in a measured result file, do not assume it.

## Measured quality gaps

The 58-query benchmark includes 18 docs, 10 current-fact, 12 niche-technical, 10
unanswerable, and 8 conflicting queries. It is small, hand-labelled, and
English-centric. It is a regression harness, not a product-quality evaluation.

Known failures in the current run are recorded in
[`benchmarks/results/`](../benchmarks/results/) and summarized in the README.
The persistent ones are:

1. **Labelled-domain precision is low.** The metric only credits URLs matching
   the label's `relevant_url_prefixes`. A genuinely useful result on another
   domain is counted as wrong. This is intentionally strict and is not the same
   as human relevance. The final2 run scored 0.1461 (26/178).
2. **Conflict recall is weak.** The detector only compares numbers with the same
   normalized unit and at least 50% subject-token overlap across different
   registrable domains. It does not understand synonyms, ranges, dates, or
   non-numeric contradictions. On the current conflicting set it flagged 0/8.
3. **No-result detection is heuristic.** Guards cover sensitive requests,
   explicit future years, proprietary source requests, unverifiable fictional
   entities, and unsupported `exact`/`precise` modifiers. A joke premise with a
   real-looking page can still produce `partial`. The final2 subset scored 9/10;
   one unanswerable query still returned a result.
4. **Keyless latency is variable.** DuckDuckGo Lite can hang, throttle, or
   return a challenge; Mwmbl can time out; Wikipedia is fast but only
   encyclopedic. Fuse mode waits for the slowest non-cancelled provider, so p50
   can exceed the 1,500 ms starting target even when p95 is acceptable. In
   final2, search p50 was 2.5 s and p95 was 4.0 s.
5. **Current facts are not guaranteed current.** Dates come from page metadata
   and may be missing or wrong. `possibly_outdated` only fires when the query
   contains a recency term and every dated source is older than one year.

## Search provider reality

- `ddg` parses the unofficial DuckDuckGo Lite HTML endpoint. Its markup and
  anti-bot behavior are not a contract. There is no SLA, and a bot challenge is
  reported as a provider error rather than bypassed.
- `mwmbl` uses a small public index and returns fewer, less authoritative
  results for many technical queries. Its API can be slow or unavailable.
- `wikipedia` uses the MediaWiki API. It is reliable for encyclopedic topics but
  cannot answer most programming or vendor-specific questions.
- The `tavily` adapter was exercised live on 2026-10-23 against a key in the
  local `.env`; its measured run is recorded separately in
  `docs/MEASUREMENTS.md`. Its pricing, quota, and long-term result quality are
  still not claimed.
- The `brave` adapter exists but was **not measured**: no Brave API key was
  available. Its pricing, quotas, and result quality are not claimed.
- `searxng` expects a self-hosted instance with JSON output enabled. Many public
  instances disable JSON; none was verified here.
- `bing` is optional and marked degraded. Microsoft retired the official Bing
  Search APIs, and the HTML fallback returned unsafe, unrelated results during
  development. It is not in the default chain.

The keyless and Tavily runs are separate operating points, not a controlled
vendor bake-off. The comparison document labels Brave and SearXNG as unverified
or blocked, not as wins.

## Extraction

- HTML extraction uses trafilatura in fast mode plus lxml metadata. It strips
  navigation, scripts, and most boilerplate, but can remove content inside
  unusual layouts or keep cookie banners.
- JavaScript-only pages can use the optional Playwright browser. It was
  smoke-tested on Windows with Playwright Chromium against a local JavaScript
  shell; the latest result is in
  `benchmarks/results/2026-10-27_browser_smoke.json`. It remains disabled by
  default and is not part of the headline latency.
- The browser fallback is heuristic: it runs only when the static text is short
  and the HTML looks like a JavaScript shell. Pages that need JavaScript but do
  not match those markers are returned with their static text.
- Browser page traffic is routed through a loopback egress proxy that resolves
  and validates each destination once and connects to the validated IP. The
  proxy is in-process, not a network namespace, and has not been independently
  audited; it reduces but does not eliminate browser-path risk.
- PDF text extraction now uses PyMuPDF, capped at 40 pages. It only extracts an
  existing text layer; scanned PDFs are not OCRed.
- Character spans refer to the cleaned text returned by the extractor, not the
  original HTML byte offsets. Re-fetching a changed page can invalidate spans.
- Metadata (`d`, `at`, `h`) is best-effort and may be absent. `at` is the fetch
  time, not the publication time.

## Research

- Research is deterministic and does not call an LLM. It does not synthesize an
  answer, resolve synonyms, or judge whether a claim actually answers the
  question. It returns verbatim sentences and gaps.
- Findings are limited to 8 (3 per domain) and 6 pages by default. A relevant
  page ranked below the cutoff is never fetched.
- The answer-support metric only checks labelled terms in findings. It is not a
  human or LLM correctness judgment.
- Conflict detection is conservative. False negatives are expected; false
  positives are possible when two numbers share a unit and subject tokens but
  refer to different things.
- `exact`/`precise` is an answerability-critical modifier: if the evidence never
  supports the modifier, the result is refused. This can reject a correct
  approximate answer when the user used "exact" loosely.
- Sensitive-query refusal is pattern-based and can both over-block and
  under-block.

## MCP

- The official `@modelcontextprotocol/conformance` 0.1.16 active suite was run
  on 2026-10-27 against stateless HTTP. It is not a full pass: 9 checks passed,
  21 failed, and 1 warned. The failures are scenarios for optional capabilities
  or fixture tools outside its four-tool surface. The meaningful core scenarios
  (`server-initialize`, `ping`, `tools-list`, `dns-rebinding-protection`) all
  passed. The Windows Node runner exits with a libuv assertion after saving
  results, so it is not yet a zero-exit CI gate. See
  `benchmarks/results/2026-10-27_mcp_conformance.md`.
- Only `tools/list` was asserted over the modern `2026-07-28` stateless HTTP
  flow. The legacy `2025-11-25` `initialize` + `tools/list` flow was asserted.
  The conformance run covered `2025-06-18` and `2025-11-25` scenarios only.
- `2025-03-26` and `2024-11-05` were not directly tested.
- Conformance did not exercise WebLens's four tool calls over HTTP; stdio,
  OAuth, TLS, and browser-client behavior remain untested.
- Only the four tools are populated. The SDK advertises empty `prompts` and
  `resources` capabilities, whose list methods return `[]`; no prompt/resource
  items, sampling, elicitation, completion, logging, progress, subscriptions, or
  OAuth are implemented.
- Streamable HTTP uses SSE framing (`json_response=False`). A client that only
  accepts `application/json` may not work.
- No load test, TLS termination, CORS policy, or per-client rate limit exists.

## Security

- SSRF defenses are unit-tested but not independently audited. A public proxy
  or an unexpected URL-parser differential can still reach a private service.
- The optional browser's egress proxy is also unit-tested, but it shares the
  WebLens process and is not a sandbox. A Chromium or proxy defect could bypass
  the destination policy; see the browser residual in the threat model.
- Prompt-injection flags are heuristics; they are not a classifier and do not
  sanitize content. The calling model must preserve the data/instruction
  boundary.
- The cache is unencrypted SQLite. Queries and fetched content may be sensitive.
  `WEBLENS_CACHE_MAX_BYTES` caps logical payload, not SQLite/WAL disk use;
  `weblens cache stats` reports both, and `weblens cache purge` deletes rows only.
- Parser vulnerabilities in lxml, trafilatura, or PyMuPDF are handled only by
  dependency updates and the process boundary; parsing is not sandboxed.
- Enabling private networks or the browser invalidates several default security
  assumptions. Do not enable them casually.

## Performance

- Latencies are single-machine measurements on Windows 11 with a home network.
  They include provider throttling and are not a service-level guarantee.
- Cold start is measured separately because importing tiktoken, lxml, and the
  MCP SDK dominates the first call. Warm HTTP-cache hits are much faster; search
  envelopes themselves are not cached.
- The tokenizer is `tiktoken` `cl100k_base`. Token counts differ for other
  models/tokenizers; budgets are not "context windows".
- Schema tokens (838) count the serialized four-tool `tools/list` result, not the
  full request envelope or client-side overhead.
- The headline benchmark run used `--fresh-cache`. Repeated benchmark
  invocations without that flag reuse `benchmarks/.cache`, so they are warm for
  page and provider HTTP responses. Because search envelopes are not cached,
  there is no warm-search p50 to report.
- The one Tavily run cleared the accuracy gates but measured 2.87 s p50 and
  5.58 s p95, failing both search latency gates. Do not generalize one run into
  a provider SLA.
- The browser smoke test measures three fresh local-page extractions and one
  public HTTPS proxy check; it is not a page-corpus latency claim.

## Scope

- Windows 11 is the tested platform. The code is OS-independent in principle
  (`uv`, asyncio, pathlib), but Linux/macOS were not measured.
- There is no multi-user mode, authentication database, quota system, or hosted
  deployment.
- There is no training data, fine-tuning, vector index, or learned ranker.
- No claim is made that this system is better than Tavily, Brave, Firecrawl,
  Crawl4AI, or any hosted search API. The comparison matrix states only
  architectural differences and marks unmeasured rows as unverified.
