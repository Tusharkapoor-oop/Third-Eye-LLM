# WebLens: Web Intelligence Platform & Model Context Protocol (MCP)

[![CI](https://github.com/Tusharkapoor-oop/Third-Eye-LLM/actions/workflows/ci.yml/badge.svg)](https://github.com/Tusharkapoor-oop/Third-Eye-LLM/actions/workflows/ci.yml)
[![WebLens CI](https://github.com/Tusharkapoor-oop/Third-Eye-LLM/actions/workflows/weblens-ci.yml/badge.svg)](https://github.com/Tusharkapoor-oop/Third-Eye-LLM/actions/workflows/weblens-ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

WebLens is a local-first, cloud-deployable web intelligence platform for AI agents. It provides compact, citable evidence packets, bounded crawling, a local RAG knowledge base, and nine application workflows over a real MCP server.

**What it is:** an evidence engine. It returns URLs, fetch timestamps, exact
character spans, gaps, conflicts and explicit no-result states — never invented
prose. **What it is not:** an LLM, a scraper farm, or a "just trust the summary"
search API.

This README reports **measured** results from the current V10 evaluation. It deliberately does not repeat older unverified marketing numbers.

**Jump to:** [quick start](#installation--local-execution) · [MCP tools](docs/MCP_API_REFERENCE.md) · [quality gates](#engineering-quality-gates) · [security](SECURITY.md) · [measured benchmark](#v10-three-system-measurement-120-queries) · [contributing](CONTRIBUTING.md)

---

## Live Cloud Deployment

- **MCP endpoint:** `https://weblens-fgunqcnrla-uc.a.run.app/mcp`
- **Alias endpoint:** `https://weblens-16131012091.us-central1.run.app/mcp`
- **Health/root:** `GET /` returns `{"status":"ok","service":"weblens","version":"0.1.0","mcp_endpoint":"/mcp"}`
- **Current revision:** `weblens-00006-l9h` (region `us-central1`)
- **Transport:** JSON-RPC over Streamable HTTP MCP
- **Public tool surface:** 11 stateless tools. The three stateful tools (`crawl2rag_index`, `crawl2rag_query`, `research_chat`) are **not** registered on the public unauthenticated listener because they share a process-wide SQLite store.
- **Local tool surface:** all 14 tools under `--profile full` on loopback (or with a bearer token).

The Cloud Run IAM policy is public (`allUsers`), but the MCP listener requires a bearer token: the current code refuses to bind a non-loopback host without `WEBLENS_HTTP_TOKEN` or `WEBLENS_API_KEYS`, and `--allow-insecure` is no longer used by the shipped `Dockerfile`. The deployed-revision measurements below were taken before that change. See the security section below.

### Cloudflare Containers

A separate deployment package targets Cloudflare Containers: `wrangler.jsonc`, `Dockerfile.cloudflare`, and the Worker in `cloudflare/worker.ts`. It is deployment-ready but has **not** been deployed. See [cloudflare/README.md](cloudflare/README.md) for the Workers Paid prerequisite, secret setup, MCP client configuration, and operational limits.

---

## V10 Three-System Measurement (120 queries)

Dataset: `weblens-lab/datasets/eval_benchmark_suite_v10.json` (`v10.0.0`), 120 curated queries, 30 categories × 4, 60 dev / 60 held-out, SHA-256 `a42d4004fb91208f1ae18de89e2337f2ccf5e7cb580a3c600a8ec7d8057d6361`.

Systems measured independently, same queries, no merged results:

1. Local WebLens MCP server process (`python -m weblens.cli serve --http --profile full`, keyless providers only)
2. Deployed WebLens MCP (`weblens-00003-l9q` at measurement time; current revision has remediation changes)
3. Tavily direct `/search` (`search_depth=basic`, 5 results)

| Metric | Local WebLens | Deployed WebLens | Tavily |
|---|---:|---:|---:|
| Graded queries | 107 | 107 | 107 |
| Success rate | 0.900 | 0.942 | 1.000 |
| p50 latency | **837.0 ms** | 1,037.8 ms | 1,537.4 ms |
| p95 latency | **1,497.3 ms** | 1,622.2 ms | 2,673.1 ms |
| P@5 | 0.553 | 0.471 | **0.740** |
| nDCG@5 | 0.669 | 0.729 | **0.777** |
| Hit@5 | 0.729 | 0.832 | **0.935** |
| Mean tokens (`cl100k`) | **182.3** | 206.2 | 1,378.7 |
| Provider credits | 0 | 0 | 120 |

95% CIs for P@5: local `[0.484, 0.624]`, deployed `[0.411, 0.533]`, Tavily `[0.675, 0.804]`.

**Honest reading:** WebLens is ~1.8× faster and returns ~7.5× fewer tokens than Tavily, but Tavily is more relevant and more reliable on this dataset. Paired local−Tavily P@5 is **−0.187**, 95% CI `[−0.265, −0.108]` (24 wins / 34 ties / 49 losses). Do not claim WebLens beats Tavily on retrieval quality **on this v10 suite**; the v11 n=40 hybrid table below is a different, smaller measurement and is labeled hybrid.

Full report: `reports/three-system-comparison-v10/V10_REPORT.md`.

### Dataset status

- 120 curated queries achieved.
- 100k primary / 250k preferred / 500k stress targets: **BLOCKED**, not met.
- 10k adversarial cases: **BLOCKED**; 9 curated cases exist.
- 13 unanswerable/ambiguous/contradictory queries are excluded from graded metrics (107 graded).

---

## Official Tavily Demo Use-Case Coverage

All eight official Tavily demo use cases were exercised through real WebLens tools, with Tavily `/search` as a retrieval baseline:

| ID | Use case | WebLens tool | WebLens facet coverage | Tavily facet coverage |
|---|---|---|---:|---:|
| UC-01 | Company research | `company_research` | 0.25 | 0.75 |
| UC-02 | Financial market research | `market_research` | 0.25 | 1.00 |
| UC-03 | Web-powered assistant | `deep_research` | 0.50 | 1.00 |
| UC-04 | Compliance risk screening | `deep_research` | 0.00 | 0.75 |
| UC-05 | Sales meeting prep | `meeting_prep` | 0.50 | 0.75 |
| UC-06 | Supply chain risk | `deep_research` | 0.00 | 0.75 |
| UC-07 | Underwriting research | `deep_research` | 0.00 | 0.75 |
| UC-08 | Data enrichment | `sheets_enrich` | 0.60 | 1.00 |

Mean facet coverage: **WebLens 0.263 vs Tavily 0.844**. Mean tokens: **149.1 vs 1,278.6**. Mean latency: **9,102 ms vs 332 ms**. Scoring counts output evidence only; query/input echoes are excluded.

Caveat: Tavily `/search` returns snippets, not a synthesized report; this is a retrieval-only lower bound for Tavily, not a full agent comparison. Results: `reports/tavily-use-cases-v10/results.json`.

---

## Model Access (Not a Ranking)

| Model | Status | Evidence |
|---|---|---|
| `mistralai/mistral-large-4-1t-a52b` (NVIDIA) | **ACCESSIBLE** | HTTP 200, exact JSON reply, 21.4 s, 116 reasoning tokens |
| `openai/gpt-oss-20b` (NVIDIA) | **BLOCKED** | Two probes (60 s, 150 s) returned `ReadTimeout` |
| `nv-mistralai/mistral-nemo-12b-instruct` | **BLOCKED** | HTTP 404, not entitled for this account |
| “GPT-OSS 12B” | **UNSUPPORTED** | No such model ID available; 12B option is Mistral NeMo 12B |

Only one model produced a completion. A model-vs-model quality ranking would be fabricated and is not reported.

---

## Nine Product Applications

Verified live end-to-end: **9 PASS / 0 PARTIAL / 0 FAIL** (`reports/nine_applications_verification.json`).

1. Deep research with URL + exact span citations
2. Company researcher
3. Conversational answer engine
4. Crawl2RAG (real crawl → index → query, passage spans)
5. Market researcher / portfolio analyzer
6. Sheets batch enricher (formula injection defanged)
7. Meeting preparation agent
8. WebLens 101 tutorial (all 9 steps)
9. Persistent research chat (reopen and export)

Run: `python tools/run_all_nine_apps_live.py`

---

## Security Posture (Measured, Not Assumed)

**Local:** 38/38 checks pass (`reports/local-security/local_security_results_v2.json`). SSRF blocking works for metadata, loopback, RFC1918, IPv6 loopback and `file://`; a public control URL still extracts, proving the block is not blanket denial.

**Deployed (revision `00006-l9h`):** 18 PASS / 4 FAIL / 1 UNSUPPORTED (`reports/deployed-security/deployed_security_results_v2.json`). Those results describe that historical revision, not the current code.

Open findings in the *current* code:

- Auth is mandatory for non-loopback listeners (`WEBLENS_HTTP_TOKEN`/`WEBLENS_API_KEYS`); the `Dockerfile` no longer passes `--allow-insecure`. A deployment that omits the token exits with status 2 instead of serving unauthenticated requests.
- Application-level rate limiting is implemented (`weblens/src/weblens/ratelimit.py`, per-tenant token buckets). The "no rate limit" finding applied to revision `00006-l9h`.
- Security headers (HSTS, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`) are emitted by `weblens/src/weblens/cli.py`. The "no HSTS" finding applied to revision `00006-l9h`.
- Cross-tenant isolation remains **UNSUPPORTED** for callers sharing one token: stateful tools were removed from the public listener after a real leak was found on revision `00005`. True multi-tenant isolation across distinct identities is not implemented.

Not claimed: “fully hardened”, “10/10 remote checks passed”, or “zero trust”. The old README claimed these; they are contradicted by the measured audit.

The build context excludes env files via `.dockerignore`/`.gcloudignore` (`**/.env*`), so `weblens/.env` is not copied into the image. Known residual risk: a live Tavily key remains in **git history** (commits `1c11ac3`, `a93e61b`); rotate it and purge history as documented in `evidence/SECURITY-FINDINGS.md`.

---

## MCP Client Configuration

### Deployed (11 stateless tools; bearer token required)

```json
{
  "mcpServers": {
    "weblens-cloud": {
      "url": "https://weblens-fgunqcnrla-uc.a.run.app/mcp",
      "headers": {"Authorization": "Bearer ${WEBLENS_HTTP_TOKEN}"}
    }
  }
}
```

Generate the token with `openssl rand -hex 32`, set `WEBLENS_HTTP_TOKEN` on the
server, and give clients the same value. Requests without it receive HTTP 401.

### Local (all 14 tools)

```json
{
  "mcpServers": {
    "weblens-local": {
      "command": "python",
      "args": ["-m", "weblens.cli", "serve", "--profile", "full"],
      "env": {"WEBLENS_MCP_PROFILE": "full"}
    }
  }
}
```

---

## Installation & Local Execution

```bash
git clone https://github.com/Tusharkapoor-oop/Third-Eye-LLM.git
cd Third-Eye-LLM
pip install -e ./weblens -e .
```

```bash
# stdio MCP server (all 14 tools)
python -m weblens.cli serve --profile full

# local HTTP MCP server
python -m weblens.cli serve --http --host 127.0.0.1 --port 8765 --profile full

# non-loopback requires a bearer token; the server refuses to start otherwise
WEBLENS_HTTP_TOKEN="$(openssl rand -hex 32)" \
  python -m weblens.cli serve --http --host 0.0.0.0 --port 8080 --profile full

# --allow-insecure exists only to explicitly accept an unauthenticated endpoint
# (never use it for a public deployment).
```

### Application CLI

```bash
python -m weblens.cli app company "Anthropic"
python -m weblens.cli app market "Apple Inc."
python -m weblens.cli app market --portfolio "AAPL" --portfolio "MSFT"
python -m weblens.cli app meeting "Architecture Review" -a "Guido van Rossum" -c "Python Software Foundation"
python -m weblens.cli app tutorial --step all
```

---

## Tests Actually Executed

| Suite | Result |
|---|---|
| Canonical package (`pytest weblens/tests`) | **769 passed, 1 skipped** in 191.6 s |
| Canonical coverage | **90.74 %** (gate: `--cov-fail-under=90`) |
| Root / legacy stack (`pytest tests`) | **353 passed, 5 skipped** in 483.1 s; terminates cleanly (the old teardown wedge is fixed) |
| Skipped tests | Browser-dependent tests skip when Chromium cannot launch in the environment |
| `ruff check` + `ruff format --check` (inside `weblens/`) | **pass** |
| `mypy weblens/src/weblens` | **0 errors** (54 files) |
| `bandit -r weblens/src/weblens -ll` | **0 medium/high** |
| Mirror drift guard (`test_mirror_drift.py`) | **pass** |
| Tracked-secret scan (`tests/test_no_tracked_secrets.py`) | **pass** |
| Provider status classification (tavily/brave/searxng/yahoo) | **pass** (401/403 terminal, 429 retryable) |
| Benchmark metric unit tests (`test_v11_metrics.py`) | **13 passed** |
| Nine apps live runner | **9/9 PASS** |
| Local security v2 | **38/38 PASS** |
| Deployed security v2 (historical revision `00006-l9h`) | **18 PASS / 4 FAIL / 1 UNSUPPORTED** |

Measured on Windows with Python 3.14 in this workspace. CI additionally runs both suites on Python 3.11–3.13.

### Measured head-to-head vs Tavily (live API, 40 held-out queries)

The shipped default when a Tavily key is configured is a **hybrid**: Tavily is
one of WebLens's providers, then WebLens filters, ranks and fuses it with
keyless providers. This is **not** an independence claim, and each WebLens query
also spends one Tavily credit.

Artifact: `evidence/raw/R-20261109-HYBRID-40-FILTER/REPORT.md` (ledger
`cfacf8a7…`, exit 0, uncontaminated, n=40, 2026-11-09).

| Metric | WebLens hybrid (shipped) | Tavily direct |
|---|---:|---:|
| Hit@5 | **0.775** | 0.625 |
| P@5 | **0.365** | 0.200 |
| nDCG@5 | **0.399** | 0.214 |
| MRR | **0.613** | 0.392 |
| p50 / p95 latency | 718 / 2040 ms | **331 / 501 ms** |
| Mean result tokens | **419** | 1678 |

Paired P@5 difference **+0.165** (95% CI **+0.095 … +0.245**), win/tie/loss
**18 / 21 / 1**.

**Honest reading:** on this n=40 suite the hybrid leads on precision, Hit@5 and
token cost, and is still slower than Tavily at p50 and p95. The keyless fallback
(no Tavily key) is measured separately: P@5 0.325 vs Tavily 0.180, n=40, but
Hit@5 0.550 vs 0.600 and p50 ~3.1 s. The keyless early-stop experiment was
rejected on a pre-registered non-inferiority test; the hosted fast path is
gated on a Tavily pool and fired in 36/40 rows.

**Important:** WebLens ships an author-curated "primary source" hint table whose
labels overlap this dataset's labels. Left enabled it inflates P@5 (a prior run
went from 0.410 to **0.805** — pure label leakage). The benchmark disables it
(`use_official_source_hints=False`) and records that setting in `results.json`.
An earlier revision of this README would have quoted the inflated figure.

---

## Engineering Quality Gates

Every pull request must pass these automated gates (enforced in CI and available
via `pre-commit`):

| Gate | Command | Threshold |
|---|---|---|
| Lint | `cd weblens && ruff check src tests benchmarks` | zero findings |
| Format | `cd weblens && ruff format --check src tests benchmarks` | clean |
| Types | `mypy weblens/src/weblens` | zero errors |
| Static security | `bandit -r weblens/src/weblens -ll -q` | no medium/high |
| Canonical tests + coverage | `cd weblens && pytest tests --cov=weblens` | all pass, **≥ 90 %** |
| Root/legacy tests | `pytest tests` | all pass, no hangs |
| Mirror drift guard | `pytest weblens/tests/test_mirror_drift.py` | byte-identical trees |
| Secret scan | `pytest tests/test_no_tracked_secrets.py` | no tracked credentials |

The canonical package and its mirror `src/weblens` must remain byte-identical;
the guard test fails otherwise. See [CONTRIBUTING.md](CONTRIBUTING.md) for the
full local workflow.

---

## Repository Layout

- `weblens/src/weblens/` — canonical WebLens package (edit here)
- `src/weblens/` — editable-install mirror; must stay identical
- `weblens-lab/` — evaluation harness, dataset, security lab, adapters
- `reports/` — V10 analysis, use-case results, security results, nine-app evidence
- `evidence/` — claim ledger, experiment index, loop state, security findings
- `server.py` — legacy MyWebEngine demo; **not** the Cloud Run entry point

---

## Documentation

- [Documentation index](docs/README.md)
- [MCP API reference](docs/MCP_API_REFERENCE.md)
- [Security policy](SECURITY.md) · [Security threat model](docs/SECURITY_THREAT_MODEL.md) · [Security findings](evidence/SECURITY-FINDINGS.md)
- [Contributing guide](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [License](LICENSE)
- [V10 three-system report](reports/three-system-comparison-v10/V10_REPORT.md)
- [Claim ledger](evidence/CLAIM_LEDGER.md)
- [Experiment index](evidence/EXPERIMENT-INDEX.md)
- [Final A–L report](reports/FINAL_REPORT.md)
