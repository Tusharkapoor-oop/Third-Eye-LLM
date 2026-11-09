# WebLens / webintel — Read-Only Assessment (snapshot 2)

Date: 2026-11-09, snapshot taken 13:29–13:50 local.
Commit assessed: `a9af2ae` (HEAD), working tree dirty (195 entries, another process
was editing the repo during this session — see §7).
No source file was modified by this assessment. All logs are in `reports/`.

## 0. Grades

| Area | Grade |
|---|---|
| Canonical engine, tests and defaults (HEAD) | **OK** |
| Legacy/root engine security | **BAD**, two **WORST** spots |
| Root test harness | **BAD** |
| CI claims vs behaviour | **BAD** |
| Docs/status numbers | **BAD** |
| Performance (model client) | **BAD** |

## 1. Canonical package — OK

- Full suite: **761 tests, all passed, EXIT=0** (`reports/verdict_canon_suite2_2026-11-09.log`,
  100% dot progress, no `FAILED`, no timeout).
- Mirror guard: `pytest tests/test_mirror_drift.py` → **57 passed**, and
  `diff -rq weblens/src/weblens src/weblens` → **0 differences** at snapshot time.
  (Earlier in the session the two trees drifted and the guard failed 5–8 cases;
  that was real then and is resolved now.)
- Defaults now correct: `allow_hosts = ""` means "any public host" for outbound
  fetches, and the inbound MCP Host allowlist is a separate setting
  (`allowed_hosts = "localhost,127.0.0.1,[::1]"` → `mcp_host_allowlist`).
  `python -m weblens.cli extract https://example.com` → `{"status":"ok", ...}`.
  The blocker reported earlier existed at commit `4e0885d`; it is fixed in HEAD.
- Adversarial probe: **181/184** matched (`reports/verdict_probe_2026-11-09.log`).
- Tool schema budget: core 838 / research 1319 / full 2097 tokens, all under 1000
  per profile where required; 14 tools.

Remaining probe mismatches (3):

1. `normalize_url("http://exa mple.com/")` returns the URL with a space instead of `None`.
2. `normalize_url("http://exam\tple.com/")` silently rewrites the host to `example.com`.
3. Malformed-page fixture: the table case loses the sentence it was checking because
   the protected table/code block is reflowed into one line (see §3.4).

## 2. Legacy/root engine — BAD with two WORST spots

### WORST — advanced search bypasses SSRF checks

`search_pipeline` sets `force_tier2=True` for `search_depth="advanced"`. That branch
(`extractor.py:295`) calls `_extract_tier2_playwright(url)` with **no**
`validate_url_security`. Proven by recording the URL handed to Playwright:

```
http://127.0.0.1:9999/admin               -> reached tier-2
http://169.254.169.254/latest/meta-data/  -> reached tier-2
file:///C:/Windows/win.ini                -> reached tier-2
```

The canonical package solves this class with `net/browser_proxy.py` (egress proxy
that pins the resolved IP for CONNECT and plain HTTP); the root stack never adopted it.

### WORST — HTTP transport has no authentication

`server.py::run_server()` accepts `--host` and serves the Streamable HTTP app with no
token, no loopback-only guard. `python server.py --http --host 0.0.0.0` exposes all
14 tools (browser, document, stateful SQLite tools). The token requirement in the
README applies to `weblens.cli`, not to this entry point.

### BAD — no IP pinning in the legacy fetcher

`safe_fetch_url` calls `resolve_and_verify_host(host, port)` and discards the
returned address, then streams to the hostname (`security.py:222`). A DNS answer
that changes between check and connect defeats it. Canonical `SafeNetworkBackend`
does pin.

### BAD — table/code blocks are destroyed inside real pages

With prose around them, protected blocks come out as
`| A | B | | --- | --- | | 1 | 2 |` and ```` ```python print('hi') ``` ```` —
one line each, not parseable as Markdown. Standalone blocks extract correctly, so
the loss is specifically the prose reflow.

### BAD — SSL context per model request

`model_provider.py:149` builds `httpx.AsyncClient(timeout=timeout)` per attempt.
Measured earlier on this machine: 8.64 s / 4.45 s / 3.61 s per construction
(`ssl.create_default_context` alone 0.82 s). `security.shared_ssl_context()` exists
and is used elsewhere, but not here.

### Minor

- `sanitize_untrusted_content` misses zero-width and homoglyph injection; the
  canonical scanner catches both.
- `normalize_url` strips `ref`/`source`, which are not always tracking parameters.
- `is_blocked_or_spa` escalates every 503 to Chromium, so an outage costs a browser
  launch per URL.

## 3. Test harness — BAD at the root

- Root suite **as configured aborts**: `+++ Timeout +++` in
  `tests/test_04_fuzz_and_chaos.py:78` (`test_fuzz_web_search_inputs`), `EXIT=1`
  (`reports/verdict_root_suite_2026-11-09.log`). This is the third independent
  occurrence; the earlier ones hit `test_fuzz_deep_research_inputs`.
  Cause: those Hypothesis tests call the live `web_search`/`deep_research` tools, so
  each example performs real network + model work and ONNX reranking.
- With those two tests deselected the root suite is green:
  **356 passed, 2 deselected, 777.70 s** (`reports/full_suite_2026-11-09c.log`).
- CI (`ci.yml`) sets `WEBINTEL_LIVE_TESTS=0` and labels the step "offline", but only
  `tests/test_mcp_e2e.py` reads that variable. The fuzz tests ignore it, so the CI
  claim is false for the tests most likely to hang.
- The arena gate (`test_07`) asserts on a checked-in `arena_report.json`, not a fresh
  run; scores across recorded runs are 81.6 / 87.0 / 90.6, and the gate currently
  passes on 90.6. It certifies an artifact, not the engine.
- Static checks: 438 Python files compile cleanly; `ruff check weblens/src src`
  reports 9 issues (2 unused imports, 2 unsorted imports, missing final newlines,
  `strip()` with multi-characters, `TimeoutError` alias).

## 4. Verify-before-release checklist

1. Close the `force_tier2` SSRF hole (validate the URL or route browser egress
   through the canonical proxy).
2. Add auth or a loopback-only guard to `server.py --http`.
3. Make the two root fuzz tests hermetic (stub search/model, or honour
   `WEBINTEL_LIVE_TESTS` in them), then re-run the full root suite as configured.
4. Pin the resolved IP in legacy `safe_fetch_url`.
5. Reuse `shared_ssl_context()` in `model_provider`.
6. Re-run the arena before trusting the gate, or version the artifact with its commit.
7. Re-run `pytest weblens/tests` and the drift guard once the concurrent edits stop.

## 5. What is strong

- Canonical SSRF policy: connect-time IP pinning, mixed-answer rejection, metadata /
  loopback / private / mapped-IPv6 / CGNAT blocking, port and scheme allowlists.
- Browser egress proxy: CONNECT + HTTP pinning, header/body bounds, upgrade and
  userinfo refusal.
- Injection scanning: EN/ES/ZH/RU/AR, NFKC, combining-mark handling, invisible
  Unicode, negation-aware exfiltration rule.
- Rate limiter: O(1) token bucket with LRU bound and injectable clock.
- Path guard: traversal, absolute paths and Windows device names all blocked.
- 800 random Unicode/control strings produced no exceptions.

## 6. Evidence index

| File | Content |
|---|---|
| `reports/verdict_canon_suite2_2026-11-09.log` | canonical 761 tests, EXIT=0 |
| `reports/verdict_probe_2026-11-09.log` | probe 181/184 |
| `reports/edge-case-probe-2026-11-09.json` | machine-readable results |
| `reports/verdict_root_suite_2026-11-09.log` | root suite timeout, EXIT=1 |
| `reports/full_suite_2026-11-09c.log` | root suite 356 passed / 2 deselected |
| `reports/verdict_canon_suite_2026-11-09.log` | earlier canonical run (timeout) |

## 7. Caveat: the repository was being edited during this session

Two new commits landed while I was testing (`ccafa81`, `a9af2ae`), 195 working-tree
entries are dirty, and files under `weblens/src`, `weblens/tests`, `src/weblens` and
`tests/` were rewritten between 13:07 and 13:21 (coverage tests, redis/tenancy
features). One collection attempt failed on a half-written
`weblens/tests/test_redis_paths_coverage.py` (`async @pytest.mark.asyncio`) and
succeeded minutes later. Every result above is therefore a snapshot of HEAD
`a9af2ae` at 13:29–13:50; re-run the two commands before acting on any count.
