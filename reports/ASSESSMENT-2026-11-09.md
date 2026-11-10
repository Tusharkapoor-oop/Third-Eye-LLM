# WebLens / webintel — Assessment and Hardening Verdict

Date: 2026-11-09 (hardening pass), snapshot checked 2026-11-10.
Base commit: `a9af2ae`; the fixes below were committed by the repo owner's parallel
process as `4c99e93` during the session. Working tree still had ~128 paths in
flight from that process, so timings are noisy (see §5).

Grades use **worst / bad / ok**. The earlier read-only pass graded the repository
**bad** overall with two **worst** items. This file records the current state
after the fixes.

## 0. Grades after hardening

| Area | Before | Now |
|---|---|---|
| Canonical `weblens` engine, tests, defaults | ok | **ok** |
| Legacy/root engine security (SSRF, auth, TLS) | bad (2 worst) | **ok** |
| Root test harness | bad (suite could not finish) | **ok** |
| Docs/CI claims vs behaviour | bad | **bad → partly fixed** |
| Remaining known defects | — | see §4 |

## 1. What was fixed

### 1.1 WORST — tier-2 Playwright bypassed SSRF checks (`extractor.py`)

`_extract_tier2_playwright` now:

- validates the URL with `validate_url_security` and resolves/validates DNS
  (`resolve_and_verify_host`) **before** the browser is launched
  (`extractor.py:235`);
- installs `page.route("**/*", _guarded_route)` so **every** Chromium request
  (subresources, iframes, redirects, JS-initiated fetches) is validated and
  aborted when it targets a non-public address (`extractor.py:251-265`),
  with a per-run host cache and DNS on an executor so the event loop is not
  blocked.

### 1.2 WORST — unauthenticated HTTP transport (`server.py`, `config.py`)

- `_is_loopback_host` + `_require_token_for_bind`: `run_server` raises
  `SystemExit` when `--http` binds a non-loopback address without a token:
  "Refusing to expose the HTTP transport on non-loopback host … without
  authentication. Set WEBINTEL_HTTP_TOKEN, or bind --host 127.0.0.1."
- When `WEBINTEL_HTTP_TOKEN` is set (`CONFIG.http_auth_token`), the ASGI app is
  wrapped in `_bearer_token_guard`: requests without `Authorization: Bearer
  <token>` get `401 {"error":"unauthorized"}` + `WWW-Authenticate: Bearer`,
  compared with `hmac.compare_digest`.

### 1.3 BAD — no IP pinning in the legacy fetcher (`security.py`)

`safe_fetch_url` resolves in an executor, validates every answer, then installs
`_PinningBackend` on the httpx pool so the TCP connect goes to the validated IP
while the request URL keeps its hostname (SNI, virtual hosting and HTTP mocks
stay correct). Redirect targets are validated before each hop. Covered by
`tests/test_hardening_guards.py` and verified live: `https://example.com/` →
200, 577 bytes, "Example Domain" present.

### 1.4 BAD — per-request SSL context in the model client (`model_provider.py`)

The model HTTP client now uses the shared, pooled `shared_ssl_context()` instead
of building a new context per request.

### 1.5 Harness — the root suite could not finish

- `tests/test_04_fuzz_and_chaos.py`: the two property tests no longer touch
  live providers or the ONNX reranker (stubbed `_search_searxng`,
  `_search_ddg_html`, extractor and model synthesis). They are hermetic and run
  in ~106 s for the whole module on this machine instead of timing out at 60 s.
- `tests/test_03_security_boundaries.py`: the zip-bomb test routes the pinned
  URL and fixes DNS so it exercises the byte limit rather than the network.
- `scripts/edge_case_probe.py`: one malformed-HTML fixture asserted the literal
  text "paragraph exists", which appears in no fixture — corrected to a phrase
  that does occur. The extractor itself was fine: all nine malformed cases pass.

## 2. Verification actually run

| Check | Result | Evidence |
|---|---|---|
| Canonical suite (`weblens/tests`) | **761 passed, EXIT=0** | `reports/canon_after_fix.log` |
| Root suite (`tests`, default `--timeout=60`) | **366 passed, EXIT=0, 905 s** | `reports/root_final.log` |
| Adversarial edge-case probe | **184/184 match, EXIT=0** | `reports/probe_final.log` |
| Fuzz module alone | **7 passed, 106 s** | `reports/fuzz_module_after_fix.log` |
| Guard + security + failure-injection slice | **114 passed, 83 s** | earlier run in session |
| Live pinned fetch `https://example.com/` | 200, 577 B, correct body | session transcript |
| Mirror drift `diff -rq weblens/src/weblens src/weblens` | **0 differences** | session transcript |
| `_require_token_for_bind` / bearer guard / route guard | covered by `tests/test_hardening_guards.py` | 4 tests, included in root suite |

One caveat on the root run: an earlier full run (359 passed / 3 failed) failed
`test_deep_document_bottom_answer_retrieval`,
`test_15_concurrent_mcp_tool_calls_in_memory` and `test_robots_checker` while the
parallel process was rewriting files mid-run (the deep-document test received
example.com's live page instead of its respx mock). All three passed on rerun in
isolation and in a 20-test subset, and the clean 366-pass run above followed.

## 3. Known remaining issues (not fixed, stated honestly)

1. `extractor.py:243` still launches Chromium with `ignore_https_errors=True`,
   so tier-2 accepts invalid certificates. URLs are now SSRF-validated, but TLS
   authenticity is not enforced in the browser fallback.
2. The legacy `search_pipeline.normalize_url` remains lenient: a space inside
   the host survives normalisation (it is rejected later at fetch time). The
   canonical `weblens.urls.normalize_url` now rejects control characters and
   whitespace in the host, and encodes query spaces normally.
3. `src/engine/security.py` is an older duplicate used by
   `tests/test_ssrf_penetration.py`; it does not have the pinning backend. Only
   the root `security.py` (used by the app) was hardened.
4. Docs/CI claims: `CONTRIBUTING.md` was corrected to say only
   `tests/test_mcp_e2e.py` gates live-network assertions; other report numbers
   and the arena gate artifact were not re-verified in this pass.
5. `tests/test_hardening_guards.py` contains one uncommitted addition
   (`_require_token_for_bind` startup-refusal assertions) because the working
   tree is owned by another process; nothing was committed by this session.

## 4. Snapshot caveat

The repository was being edited and committed by another process throughout this
session (`ccafa81`, `a9af2ae`, `4c99e93`, and ~128 dirty paths at the end). All
numbers above were produced from the tree as it stood at the time of each run and
are reproducible with the commands in §2; a run made while files are being
rewritten can still show transient failures.
