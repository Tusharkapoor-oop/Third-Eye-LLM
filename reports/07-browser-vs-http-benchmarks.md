# Phase 07: Browser vs Direct HTTP Benchmarks

Raw artifact: `reports/benchmark_runs/browser_vs_http.json` (2026-10-24, this machine).
Browser fixture comparison uses the local JS-shell method from
`weblens/benchmarks/results/2026-10-23_browser_smoke.json`.

## Measured head-to-head

| # | Page | Method | Latency | Content check (marker in text/DOM) | Tokens / size |
|---|---|---|---|---|---|
| 1 | example.com (static) | Direct HTTP + trafilatura | 2.80 s | **NO** — marker missing from scored passages | 1 passage, 28 tok |
| 2 | example.com (static) | Headless Edge DOM dump | 9.23 s | YES | 1,991 B |
| 3 | svelte.dev/docs (SSR SPA) | Direct HTTP | 5.32 s | YES | 2 passages, 302 tok |
| 4 | svelte.dev/docs (SSR SPA) | Headless Edge DOM dump | 12.17 s | YES | 41,719 B |
| 5 | react.dev (SSR SPA) | Direct HTTP | 3.44 s | YES | 5 passages, 750 tok |
| 6 | react.dev (SSR SPA) | Headless Edge DOM dump | 18.68 s | YES | 272,503 B |
| 7 | local JS-only shell | Playwright Chromium (weblens, proxy egress) | 3.23 s median (n=3 runs, incl. launch) | YES — content only exists post-JS | 182 tok, 1 passage |
| 8 | same local shell | Keyless HTTP-only policy check | n/a | n/a | blocked BEFORE launch (SSRF guard) |

## Derived conclusions [MEASURED]

1. **HTTP-first wins on internet pages that server-render**, even "SPA" ones:
   2.2×–5.4× faster for equal relevance (rows 3–6). The browser path buys
   nothing on these and costs 9–19 s.
2. **Browser is the only path for client-only content** (row 7): HTTP cannot
   produce it at any price; Playwright renders it in ~3.2 s when a session is
   reused, but the root stack's fresh-process model costs 9–19 s (rows 2/6).
3. **Static-minimal page extraction has a quality gap** (row 1 vs 2): the
   trafilatura+BM25 path dropped the marker text from scored passages on the
   simplest page — a reranker/chunking artifact, not a network failure.
   Listed in the failure taxonomy (`reports/15-regression-and-stress.md`).
4. **Security asymmetry** (rows 2 vs 8): weblens's proxy-validated renderer
   enforces the network policy browser-wide; the root stack validates only the
   first navigation. Mitigation is a one-line reimplementation away (reuse
   weblens's proxy) and is PROPOSED, not yet implemented.

## Verdict per routing strategy

| Strategy | Wins when | Measured evidence |
|---|---|---|
| Direct HTTP first | pages server-render (most of the modern web) | rows 1, 3, 5 |
| Browser on HTTP-failure/client-only | client-rendered content | rows 2, 4, 6, 7 |
| Browser first | almost never justified by data | — (no measured case where HTTP-first lost) |
| Tavily extract (when keyed) | keyed situations only | **NOT RUN** here (no extract credits spent; search-only comparison exists in reports/11) |

**Recommendation RETAINED**: keep HTTP-first with browser fallback; the current
trigger heuristic is conservative, which the data supports.
