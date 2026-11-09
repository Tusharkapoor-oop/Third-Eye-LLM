# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- **Canonical/mirror drift** — `src/weblens` is now byte-identical to
  `weblens/src/weblens`; the local runtime no longer fails every search with
  `TypeError: diversify() got an unexpected keyword argument 'domain_caps'`.
  Added `weblens/tests/test_mirror_drift.py` and a CI drift step.
- **MCP console entry points** — `web-intel-mcp` now targets the installable
  `server.mcp_server:main`; the broken `web-intel-bench` entry point was removed
  (run `python benchmarks/run_benchmarks.py` from a checkout).
- **FTS5 crashes** — `crawl2rag_query` quotes/escapes tokens and strips FTS
  operators, so questions containing `NOT`/`AND`/`OR`/quotes no longer raise
  `sqlite3.OperationalError`.
- **URL corruption** — `normalize_url` preserves percent-encoding instead of
  producing invalid URLs (`%25` → `%`).
- **Fabricated market data** — `market_research` only reports `currency`,
  `multiplier` and `as_of_date` when they are present in the source text.
- **Provider error classification** — `FetchError.status` is surfaced; 401/403
  are terminal and 429 is retryable across Tavily, Brave, SearXNG and Yahoo.
- **Event-loop blocking** — SQLite, ONNX, trafilatura and PyMuPDF work moved to
  `asyncio.to_thread` in extraction, Crawl2RAG, research chat and embeddings.
- **Test-suite teardown wedge** — leaked extraction tasks are cancelled and
  awaited; the full root suite terminates cleanly.
- **MCP tool annotations** — mutating tools (`crawl2rag_index`, `research_chat`)
  no longer advertise `readOnlyHint=true`.
- **Prompt-injection detection** — HTML-comment and operator-directed injection
  patterns are detected (regression tests added).

### Security

- Deployment is **secure by default**: the Docker image no longer passes
  `--allow-insecure`; non-loopback listeners refuse to start without
  `WEBLENS_HTTP_TOKEN`/`WEBLENS_API_KEYS`; deploy scripts and compose fail fast.
- Docker/Cloud Build contexts exclude nested env files (`**/.env*`), removing
  the `weblens/.env` image-leak path.
- Added tracked-file secret scanning (`tests/test_no_tracked_secrets.py`).
- Added trusted-proxy handling for `X-Forwarded-For` (off by default), explicit
  Host/Origin validation, and hardened SSRF blocklists.
- Corrected the claim ledger: the live-key-in-history finding is recorded as
  **FAIL** (rotation + history purge required); the supply-chain claim is
  **UNVERIFIED** because no OSV/pip-audit artifact exists.

### Added

- Regression tests for every fix above; coverage gate, type checking, static
  security analysis, formatting gate and mirror-drift guard in CI.
- `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, pre-commit hooks.
- `docs/MCP_API_REFERENCE.md` rewritten to match the real tool schemas
  (including `market_portfolio`).

### Changed

- README tool counts corrected (11 stateless / 14 total) and stale
  auth/rate-limit/HSTS claims replaced with current, verifiable statements.
