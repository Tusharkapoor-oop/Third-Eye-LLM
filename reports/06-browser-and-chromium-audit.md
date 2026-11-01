# Phase 06: Browser and Chromium Audit

**Browsers verified on this machine [MEASURED]**

| Browser | Version | Path | Role in this audit |
|---|---|---|---|
| Google Chrome | 155.0.8059.86 | `C:\Program Files\Google\Chrome\Application\chrome.exe` | root-stack fallback target (list order after Edge) |
| Microsoft Edge | 155.0.4283.62 | `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` | primary fallback target of root stack |
| Playwright Chromium | 1.64.0 bundle | managed install (weblens venv) | weblens renderer, proxy-egress validated |

## A. Lifecycle and startup measurement [MEASURED]

Root stack launches a *fresh* headless browser process per fallback call
(`--headless=new --dump-dom` subprocess). Measured cold costs:

| Event | Root stack (Edge subprocess) | weblens (Playwright Chromium) |
|---|---|---|
| cold launch → DOM | 9.2 s (example.com) / 12–19 s (SPA) | median 3,231.8 ms incl. launch + navigate on a local fixture |
| per-call model | new process each time | fresh instance per run in smoke test |
| cleanup | process exits at timeout/dump | `await renderer.close()`; verified no orphans in smoke |

The root stack's `--timeout` flag + Python `subprocess.run(timeout=…)` double-guard
was verified: the bounded timeout fires (candidate proof: react.dev pre-fix run
ended in a controlled timeout return, not a hang).

## B. Rendering and extraction correctness [MEASURED]

| Page type | Direct HTTP (trafilatura) | Browser fallback |
|---|---|---|
| static (example.com) | success; passage extracted but marker text dropped from scored passages (flaw noted) | DOM dump ok, 1,991 bytes, marker present |
| JS SSR-heavy (svelte.dev/docs) | success, 2 passages, 302 tokens, marker present | DOM ok, 41,719 bytes, marker present |
| JS SSR-heavy (react.dev) | success, 5 passages, 750 tokens, marker present | DOM ok, 272,503 bytes, marker present |
| local JS-only shell (no SSR) | (weblens) HTTP insufficient → browser rendered; content present [MEASURED, weblens smoke 2026-10-23] | |

Key honest finding: **modern SPA landing pages server-render their HTML**, so for
react.dev and svelte.dev direct HTTP extraction *already* retrieves the content
3–6× faster than the browser. The browser is justified for genuinely
client-only content (verified via the local JS-shell fixture rendering).

## C. Reliability [MEASURED]

- Hung render: bounded at 20–25 s and returned `(False, error)` — verified pre-fix
  on react.dev.
- **Windows decoding defect (found and fixed during this audit)**: `text=True`
  without an explicit encoding crashed on cp1252 once a UTF-8 DOM dump was large
  enough; now `encoding="utf-8", errors="replace"`. Re-verified end-to-end:
  react.dev → ok, 272,503 bytes.
- Browser crash recovery: `subprocess.run` returns rc≠0 and error text; no
  retry-loop — acceptable v0, documented as future work (exponential retry).

## D. Browser security [MEASURED + LIMITATION DECLARED]

- Private/loopback destination check runs **before** browser launch in the root
  stack (`fetch_rendered_dom` → `validate_url_security`); test: localhost fixture
  refused with `Security block` before any process spawn.
- weblens stacks Chromium behind a local egress proxy that validates **every**
  destination (redirect/iframe/fetch included); smoke test's private-URL check
  blocked `127.0.0.1` with `blocked_url` [MEASURED].
- **Root-stack limitation (declared, untested for exploitability in this audit)**:
  after launch, the browser's own sub-requests (redirects, iframes, XHR) are not
  re-validated by the root stack — `--dump-dom` mode has no egress proxy. The
  first URL is validated; a page that redirects to an internal host from the
  headless shell is **theoretically reachable within the browser process**.
  Threat-mitigation options recorded in `reports/14-optimization-experiments.md`
  (PROPOSAL: route fallback through a validated local proxy like weblens does).
  No exploit was sought or executed against third-party infrastructure.

## E. Browser vs direct HTTP head-to-head

See `reports/07-browser-vs-http-benchmarks.md` (full table + verdict).
Raw: `reports/benchmark_runs/browser_vs_http.json`, weblens smoke:
`weblens/benchmarks/results/2026-10-23_browser_smoke.json`.

## F. Routing decision (validated against data)

Rule adopted by the engine: try direct HTTP extraction first; invoke the browser
only when the HTTP result is empty/insufficient or `render_js=True` is requested.
The measured data supports this: on 2/2 real SPA pages HTTP sufficed; the browser
provided unique value on the client-only fixture. Adjustments proposed in the
optimization ledger.
