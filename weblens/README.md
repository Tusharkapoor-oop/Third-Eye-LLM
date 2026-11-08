# WebLens

Local-first, evidence-first web intelligence for AI agents, exposed over MCP.
WebLens is a small, auditable Python service that gives any MCP-capable model
live search, page extraction, bounded site crawling, and deterministic
multi-source research without sending your queries to a hosted "agent search"
vendor.

It is **not** a chat model and does not write prose answers. It returns compact
JSON evidence: URLs, fetch timestamps, exact character spans, gaps, conflicts,
and explicit no-result states. The calling model decides what to say.

> Status: v0.1, working implementation with measured limitations. The
> benchmark intentionally fails gates it does not meet; see
> [Benchmarks](#benchmarks). Do not read this README as a claim of formal MCP
> conformance or of production-scale accuracy.

## What works

| MCP tool | What it does | Default bounds |
| --- | --- | --- |
| `web_search` | Live web search. Returns title, URL, snippet, date. No relevance/confidence score. | 5 results, 600 tokens |
| `extract_url` | Extract query-relevant passages from one HTML/PDF/plain page, with exact spans. `full=true` returns cleaned text. | 1,500 tokens |
| `crawl_site` | `mode=map` lists URLs from sitemaps/links; `mode=crawl` extracts a bounded set of same-site pages. Respects `robots.txt`. | 10 pages, depth 2, 2,000 tokens |
| `deep_research` | Runs several searches, fetches up to 6 pages, keeps verbatim claims, and reports gaps, stale sources, or numeric conflicts. No LLM is called. | 2,000 tokens |

The four-tool `tools/list` schema measures **838 `cl100k_base` tokens** on this
machine. Every budget is enforced on the final serialized payload, including
the envelope, `ms`, `tok`, warnings, and cutoff flags.

The `research` and `full` profiles add `evidence_synthesis` (select them with
`WEBLENS_MCP_PROFILE=research` / `full`, or `weblens serve --profile research`).
It turns a research result into a claim ledger, tests explicit polar,
comparison, numeric, and definition hypotheses with lexical stance rules, and
resolves contradictions by source tier, recency, and independent-domain
support. It is deterministic and LLM-free; it never paraphrases a source.
`supported` means the collected evidence is consistent with the hypothesis, not
that the hypothesis is proven.

Local gate (2026-11-08): the curated 11-case / 21-hypothesis evaluation matched
21/21 verdicts, 11/11 expected statuses, and 20/20 claims with complete
URL/timestamp/span citations. The evidence is curated/synthetic, so this is a
local implementation check, not production acceptance.

Also included:

- CLI for search/extract/crawl/research/synthesize plus `doctor` and schema-token reports.
- stdio MCP transport (default) and optional streamable HTTP.
- SSRF-safe fetching with connection-time IP validation, redirect checks,
  size caps, per-host concurrency limits, and no environment proxy trust.
- Optional Playwright browser behind a loopback egress proxy; disabled by default.
- SQLite cache with TTLs, ETag/Last-Modified revalidation, and bounded
  stale-on-error fallback. Stale evidence keeps its original fetch timestamp and
  is reported with `stale_cache_used` / `stale_source:<domain>`.
- Prompt-injection warning flags on retrieved content in English, Spanish,
  Chinese, Russian, and Arabic (not a classifier).
- Reproducible benchmark dataset (58 labelled queries), hard gates, and a
  cold-start/cache measurement script.

## Requirements

- Windows 11 (tested), Python 3.11+ (tested on CPython 3.14.0), [uv](https://docs.astral.sh/uv/).
- No API keys for the default keyless path.
- 16 GB RAM is enough. The optional browser path needs Playwright Chromium.
- WebLens is CPU/network-bound; the RTX 3050 is not used.

## Quick start (PowerShell)

```powershell
cd "C:\Users\ACER\Downloads\Broswer for ai agnets\weblens"
uv sync
uv run weblens doctor --live --pretty
uv run weblens search "sqlite WAL mode write-ahead log" --pretty
uv run weblens extract "https://docs.python.org/3/library/asyncio-task.html" -q "timeout" --pretty
uv run weblens research "HTTP 429 Retry-After" --pretty
uv run weblens synthesize "Does asyncio.timeout cancel the task when the deadline expires?" --pretty
```

Run the MCP server over stdio:

```powershell
uv run weblens serve
```

Optional HTTP transport (loopback only by default):

```powershell
uv run weblens serve --http --port 8765
# POST http://127.0.0.1:8765/mcp
```

For a non-loopback bind, WebLens refuses to start unless you pass a bearer
token, configure tenant API keys, or explicitly opt into an insecure bind:

```powershell
uv run weblens serve --http --host 0.0.0.0 --token "replace-me"
```

### Multi-tenant HTTP

Use one key per tenant instead of a shared token. `WEBLENS_API_KEYS` accepts a
JSON object or comma-separated `tenant=key` pairs:

```dotenv
WEBLENS_API_KEYS={"acme":"replace-with-a-long-random-key","beta":"another-long-random-key"}
WEBLENS_TENANT_RATE_LIMITS={"acme":600,"beta":120}
```

Clients send either `Authorization: Bearer <key>` or `X-API-Key: <key>`. The
legacy `--token` / `WEBLENS_HTTP_TOKEN` maps to the `default` tenant. Keys must
be at least 8 characters; WebLens stores only SHA-256 digests in the registry.

The limiter is a per-tenant token bucket. `WEBLENS_HTTP_RATE_LIMIT_PER_MINUTE`
is the fallback for tenants without an override. Authenticated requests are
keyed by tenant, not by IP; unauthenticated loopback requests are keyed by the
right-most `X-Forwarded-For` hop or the socket address. Responses include
`X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`; a 429
also includes `Retry-After`. A token bucket allows a burst up to one window's
quota and then refills continuously. Repeated failed key attempts are limited
separately by `WEBLENS_HTTP_AUTH_FAILURE_LIMIT_PER_MINUTE` (default 60 per IP),
so a flood of bad keys cannot bypass the tenant limiter.

Stateful `full`-profile tools use a per-tenant SQLite file under
`~/.weblens/tenants/<tenant>/`. The `default` identity keeps the historical
single-tenant paths so existing local data remains available. Tenant ids are
validated before they become directory names, and the tenant is never accepted
as a tool argument.

### Optional Redis cache

SQLite remains the zero-dependency default. For multiple app instances, install
the optional client and select Redis:

```powershell
uv pip install "weblens[redis]"
```

```dotenv
WEBLENS_CACHE_BACKEND=redis
WEBLENS_REDIS_URL=redis://127.0.0.1:6379/0
WEBLENS_REDIS_NAMESPACE=weblens
```

Redis payloads are compressed and namespaced under `<namespace>:cache:`.
`WEBLENS_CACHE_MAX_BYTES` still applies to the SQLite backend; Redis relies on
per-key TTL and server-side eviction. A Redis outage becomes a cache miss, never
a request failure; `weblens cache stats` reports the backend and last error.
`weblens cache purge` returns zero for Redis because expiry is server-side.

### Fetch resilience and repeat queries

Page fetches that hit a transient network failure (timeout, protocol reset,
retryable 5xx/429) can be answered from an expired cache entry inside
`WEBLENS_CACHE_STALE_GRACE_S` (default 7 days). The response keeps its original
`fetched_at`, so callers can see its real age; extraction adds
`stale_cache_used`, and research adds `stale_source:<domain>`. A 404/403,
blocked URL, or oversized response is never masked by stale content. Set the
grace to `0` to disable the fallback.

Research gives each fetch a real deadline. The first HTTP/2 attempt gets most of
the budget and the HTTP/1.1 pool gets the remainder, so one slow stream cannot
consume the whole research timeout before the fallback runs.

Repeated identical searches reuse a short-lived provider-result cache for
`WEBLENS_SEARCH_CACHE_TTL_S` seconds (default 300; `0` disables it). Cache hits
carry `search_cache_hit`; failed or partial searches are not cached.

## MCP client setup

Use the absolute path to this directory. The command is the same for Roo Code,
Cline, Continue, and Claude Desktop:

```json
{
  "mcpServers": {
    "weblens": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "C:\\Users\\ACER\\Downloads\\Broswer for ai agnets\\weblens",
        "weblens",
        "serve"
      ]
    }
  }
}
```

Client-specific file locations and syntax are in
[`docs/CLIENTS.md`](docs/CLIENTS.md). Ready-to-copy examples are in
[`examples/clients/`](examples/clients/). Restart the client after changing its
MCP configuration. If the client starts `uv` outside this directory, the
`--directory` argument is required.

## CLI

All commands print compact JSON by default; `--pretty` is for humans.
`status=error` exits 1. Evidence statuses such as `no_reliable_result` are
successful calls and exit 0.

```text
weblens serve [--http] [--host H] [--port P] [--token T] [--stateful]
weblens search QUERY [-k N] [--freshness day|week|month|year]
                     [--domain D] [--exclude-domain D] [--max-tokens N]
weblens extract URL [-q QUERY] [--full] [--max-tokens N]
weblens crawl URL [--mode map|crawl] [--max-pages N] [--max-depth N] [-q QUERY]
weblens research QUERY [--max-tokens N]
weblens synthesize QUERY [--max-tokens N] [--max-hops 1|2|3]
weblens doctor [--live] [--pretty]
weblens cache stats [--pretty]
weblens cache purge [--all] [--pretty]
weblens tokens [--pretty]
```

## Output contract

Compact JSON uses short keys to save tokens. The important fields are:

- Search result: `t` title, `u` URL, `s` snippet, optional `d` date.
- Passage: `u` URL, `at` fetch timestamp (UTC ISO-8601), `x` exact text,
  `s` `[start, end]` character span in the cleaned page text, optional `h`
  heading, optional `inj` injection flags.
- Research finding: `c` verbatim claim, `u` URL, `at` timestamp, `s` span,
  optional `h` heading, `d` publication date, `inj` flags.
- `tok` is the measured `cl100k_base` token count of the final payload.
- `cut=true` means a budget truncated the result; `warn` explains why.

Every tool returns one of these statuses:

| status | meaning |
| --- | --- |
| `ok` | Evidence was found and no known gap applies. |
| `partial` | Some evidence was found, but a gap, provider failure, or cutoff applies. |
| `no_reliable_result` | No evidence can support an answer. `gaps` says why. |
| `conflicting_sources` | Numeric sources disagree under a conservative heuristic. |
| `possibly_outdated` | The query is recency-sensitive and all dated sources are older than one year. |
| `error` | Input or transport failure. Over MCP this is `isError: true`. |

There is deliberately **no** `score`, `confidence`, `relevance`, or `quality`
field. Result order is a heuristic (reciprocal-rank fusion plus a small static
authority prior); it is not a calibrated probability.

`no_reliable_result` is used for, among other cases:

- sensitive-query refusal (`sensitive_query`),
- future values with an explicit future year (`future_value_unknown:<year>`),
- closed-source/proprietary source requests (`proprietary_source_unavailable`),
- a fictional entity that never appears in the evidence
  (`unverifiable_entity:<name>`),
- an `exact`/`precise` request whose evidence never supports exactness,
- searches whose results do not meet the query-term coverage floor.

## Configuration

Copy `.env.template` to `.env` only if you need overrides. All variables use the
`WEBLENS_` prefix.

Key defaults:

```dotenv
WEBLENS_SEARCH_PROVIDERS=ddg,mwmbl,wikipedia
WEBLENS_SEARCH_MODE=fuse
WEBLENS_ALLOW_PRIVATE_NETWORKS=false
WEBLENS_ALLOW_BROWSER=false
WEBLENS_CACHE_MAX_BYTES=536870912
WEBLENS_CACHE_STALE_GRACE_S=604800
WEBLENS_SEARCH_CACHE_TTL_S=300
WEBLENS_DEFAULT_RESULTS=5
WEBLENS_MAX_SEARCH_TOKENS=600
WEBLENS_MAX_EXTRACT_TOKENS=1500
WEBLENS_MAX_RESEARCH_TOKENS=2000
WEBLENS_CACHE_BACKEND=sqlite
# WEBLENS_API_KEYS={"acme":"replace-me"}          # multi-tenant HTTP
# WEBLENS_TENANT_RATE_LIMITS={"acme":600}         # optional per-tenant QPM
# WEBLENS_REDIS_URL=redis://127.0.0.1:6379/0      # with cache_backend=redis
```

`WEBLENS_CACHE_MAX_BYTES` caps the logical compressed payload plus metadata; `0`
disables eviction. SQLite/WAL overhead is additional, so this is not a hard disk
quota. Inspect the actual file size and entry count with `weblens cache stats`;
`weblens cache purge` removes expired rows and `--all` clears the WebLens
database without touching other files in the cache directory.

Keyless providers are `ddg` (DuckDuckGo Lite HTML), `mwmbl` (public API), and
`wikipedia` (MediaWiki API). Optional keyed providers are `brave` and `tavily`;
`searxng` points at a self-hosted instance. `bing` and `yahoo` exist only as
optional, degraded HTML adapters and are not in the default chain; both can be
rate-limited during burst traffic.

Per-provider deadlines are built in for the keyless path (`ddg` 3.5 s,
`mwmbl` 2.5 s, `wikipedia` 4.0 s, `yahoo` 4.0 s) and for the keyed providers
(`tavily` and `brave`, 8.0 s). `WEBLENS_PROVIDER_TIMEOUT_S` is the fallback for
providers without an explicit deadline. Fuse mode runs providers in parallel and
records failures in `fail` instead of hiding them.

### Keyed providers

Put keys in `weblens/.env`, which is gitignored. Do not put a real key in
`.env.template` or in a client configuration file.

```dotenv
# Tavily: https://app.tavily.com
WEBLENS_TAVILY_API_KEY=<paste-tavily-key>
# Brave: https://api.search.brave.com/app/keys
WEBLENS_BRAVE_API_KEY=<paste-brave-key>
```

Then choose a routing order. `fallback` stops at the first provider that fills
the result count; `fuse` queries the listed providers in parallel and merges
them:

```dotenv
WEBLENS_SEARCH_PROVIDERS=tavily,ddg,mwmbl,wikipedia
WEBLENS_SEARCH_MODE=fallback
```

The keyless default remains `ddg,mwmbl,wikipedia`; setting a key does not change
the provider list. A missing key is reported as an unavailable provider, not as
a fake result.

### Optional browser

The browser is disabled by default. To enable the tested Playwright path:

```powershell
uv sync --extra browser
uv run playwright install chromium
$env:WEBLENS_ALLOW_BROWSER="true"
```

Playwright manages its own Chromium build. A Chrome for Testing binary installed
by another tool is not auto-detected. The browser is only used when the static
HTML looks like a JavaScript shell; it is not a general "always render" switch.

Chromium is launched behind a loopback-only egress proxy. The proxy resolves each
HTTP request or HTTPS `CONNECT` destination once, rejects non-public answers, and
opens the upstream socket to that validated IP; Chromium does not perform the
page-destination lookup itself. QUIC, DNS prefetch, and non-proxied WebRTC UDP are
disabled. The proxy is still an in-process component, not a separate network
namespace or a security boundary, and it has not been independently audited.

### Optional hybrid Crawl2RAG

`Crawl2RAG` uses SQLite FTS5/BM25 by default and needs no model. To add local
dense candidates, install the optional extra and place an all-MiniLM-L6-v2 ONNX
model in a local directory:

```powershell
uv sync --extra hybrid
# model.onnx and tokenizer.json go under:
#   ~/.weblens/models/all-MiniLM-L6-v2/
# or:
#   ~/.cache/weblens/models/all-MiniLM-L6-v2/
```

WebLens never downloads a model implicitly. Set an explicit path with
`WEBLENS_EMBEDDING_MODEL_DIR` if the model lives elsewhere, or disable dense
retrieval with `WEBLENS_EMBEDDING_ENABLED=false`. When the model or optional
packages are missing, `Crawl2RAG.query()` stays on BM25 and reports
`mode="bm25"`; when dense retrieval is active it fuses BM25 and dense rankings
with reciprocal rank fusion and reports `mode="hybrid"`. Dense scoring currently
scans at most 50,000 indexed passages per query; larger knowledge bases stay on
BM25 until an approximate-nearest-neighbour index is added. The exact dense
matrix is cached per process, so repeated queries skip the SQLite blob scan;
ingestion and `clear()` invalidate it, and a size-based scan-cap fallback keeps
the embedder enabled for later smaller knowledge bases. At the 50,000-passage
cap with 384-d vectors, the cached matrix is roughly 77 MB of process memory.

On a local 21-query Python-standard-library diagnostic (20 pages, 112
passages), BM25-only Recall@5 was 0.905 and hybrid Recall@5 was 1.000. That is a
small local check, not an official benchmark. Re-run it with
`weblens-lab/evaluations/run_crawl2rag_hybrid.py --require-hybrid`. A synthetic
dense-cache benchmark (`weblens-lab/evaluations/run_dense_cache_benchmark.py`)
measured roughly 0.1–16 ms for cached queries versus 6–962 ms to rebuild the
matrix for 1,000–50,000 passages across local runs; those are synthetic timings
that vary with disk and CPU load, not a production benchmark.

## Security posture

WebLens treats every page as untrusted data and every URL as hostile until
proven otherwise. The default deployment is:

- stdio, no network listener;
- no private-network access;
- no API keys;
- no browser;
- read-only MCP tools.

Implemented controls include connection-time SSRF validation (the socket is
opened to a validated IP, not the hostname), DNS answers that mix public and
private addresses are rejected wholesale, redirect targets are revalidated on
every hop, response bodies are capped while streaming, and a global/per-host
concurrency limit bounds resource use. The optional browser is launched through a
loopback egress proxy that performs the same validate-then-connect step for HTTP
requests and HTTPS tunnels. Retrieved text may carry `inj` flags for
instruction-smuggling patterns in English, Spanish, Chinese, Russian, and
Arabic. Matching normalises full-width characters, accents, Arabic diacritics,
and Cyrillic short-i, and it keeps negated credential advice such as "do not
share credentials" out of the exfiltration flag. Those flags are heuristics and
do not grant or remove permissions. On a local 50-payload / 50-benign corpus,
the current rules measured recall 1.00 with 0.00 FPR; that is a curated local
diagnostic, not a production benchmark. Re-run it with
`weblens-lab/evaluations/run_injection_multilingual.py`.

See [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) for the asset/threat/control
matrix, adversarial tests, and residual risks. In particular, enabling the
optional browser or private-network mode materially expands the attack surface.

## Architecture

```text
MCP client
   |  stdio or streamable HTTP
   v
mcp_server.py  (four tools, compact JSON, read-only annotations)
   v
service.py     (budgets, error boundary, stable statuses)
   +--> search/router.py ---> ddg | mwmbl | wikipedia | brave | tavily | searxng | bing | yahoo
   +--> extract/ -----------> SafeFetcher -> trafilatura/lxml/PyMuPDF
   |                          + optional Playwright -> loopback egress proxy
   +--> crawl/ -------------> robots.txt + sitemap/link map + page dedupe
   +--> research/engine.py --> searches -> fetches -> verbatim findings -> gaps
   v
cache.sqlite3 or Redis (TTL + revalidation) and ~/.weblens/
~/.weblens/tenants/<tenant>/ (full-profile stateful tools only)
```

The core search/extract/crawl/research surface is stateless with respect to a
caller. The cache is disposable, expires entries by TTL, and evicts the oldest
entries when its logical payload exceeds `WEBLENS_CACHE_MAX_BYTES` (SQLite).
Optional full-profile stateful tools write only to a per-tenant directory; the
tenant identity comes from the ingress API key, never from a tool argument. There
is no vector database, no LLM call, and no shared cross-tenant research store.

Design decisions are recorded in [`docs/adr/`](docs/adr/). Protocol evidence and
version support are in [`docs/PROTOCOL.md`](docs/PROTOCOL.md). The comparison
with other retrieval tools is in [`docs/COMPARISON.md`](docs/COMPARISON.md), and
the raw run history and metric definitions are in
[`docs/MEASUREMENTS.md`](docs/MEASUREMENTS.md).

## Benchmarks

The benchmark is reproducible from committed data and scripts:

```powershell
uv run python -m benchmarks.run --fresh-cache --out benchmarks/results/latest.json
uv run python -m benchmarks.cold_start --runs 3
```

It runs 58 labelled queries across `docs`, `current_facts`, `niche_technical`,
`unanswerable`, and `conflicting`, then checks token budgets, exact citation
spans, forbidden confidence fields, retrieval quality, no-result behavior, and
p50/p95 latency. A breach makes the command exit non-zero; it does not silently
pass.

Headline keyless run: `benchmarks/results/2026-10-21_final2.json` (58 queries,
fresh cache). It **fails three gates**: labelled-domain precision, top-3
authoritative, and search p50. The failure is reported, not hidden.

| metric | measured | gate | result |
| --- | --- | --- | --- |
| search precision@n (answerable) | 0.1461 (26/178) | ≥ 0.25 | FAIL |
| top-3 labelled-authoritative | 0.35 (14/40) | ≥ 0.60 | FAIL |
| research answer support | 0.7333 (22/30) | ≥ 0.60 | PASS |
| no-result accuracy | 0.90 (9/10) | ≥ 0.75 | PASS |
| conflict recall | 0.00 (0/8) | reported, not gated | GAP |
| search p50 / p95 | 2512 / 4023 ms | p50 < 1,500, p95 < 5,000 | FAIL (p50) |
| extract p50 / p95 | 641 / 3214 ms | p50 < 2,500, p95 < 8,000 | PASS |
| research p50 / p95 | 8573 / 18637 ms | p95 < 20,000 | PASS |
| schema tokens | 838 | ≤ 1,000 | PASS |
| token / citation / uncalibrated violations | 0 / 0 / 0 | 0 | PASS |

The run used DuckDuckGo 3.5 s, Mwmbl 2.5 s, and Wikipedia 4.0 s deadlines. An
earlier run with shorter deadlines (`2026-10-21_fuse_guard`) reached p95 2.5 s
but lost labelled results; a run with restored DuckDuckGo but short
low-priority deadlines (`2026-10-21_final`) hit a provider-degradation window
and is retained only as evidence, not as the headline. See
[`docs/MEASUREMENTS.md`](docs/MEASUREMENTS.md) for all rows.

A separate keyed run with Tavily as the only provider
(`benchmarks/results/2026-10-23_tavily.json`) cleared both accuracy gates:

| metric | Tavily | keyless final2 |
| --- | --- | --- |
| precision@n | 0.2618 (50/191) | 0.1461 (26/178) |
| top-3 authoritative | 0.65 (26/40) | 0.35 (14/40) |
| answer support | 0.9667 (29/30) | 0.7333 (22/30) |
| no-result accuracy | 0.80 (8/10) | 0.90 (9/10) |
| search p50 / p95 | 2872 / 5580 ms | 2512 / 4023 ms |
| extract p50 / p95 | 275 / 1489 ms | 641 / 3214 ms |
| research p50 / p95 | 7271 / 13693 ms | 8573 / 18637 ms |

Tavily therefore improves measured accuracy but **fails both search latency
gates** (p50 2.87 s, p95 5.58 s) and is not the default. Keyless remains the
zero-key default; Tavily is an optional accuracy-first trade-off. The precision
denominators differ (191 Tavily URLs vs. 178 keyless URLs), so read the raw
counts. See
[`docs/MEASUREMENTS.md`](docs/MEASUREMENTS.md#keyed-provider-run-tavily) for the
method and caveats.

Browser smoke test (three fresh local JavaScript-shell runs and a public HTTPS
proxy check, Playwright Chromium):
[`benchmarks/results/2026-10-27_browser_smoke.md`](benchmarks/results/2026-10-27_browser_smoke.md).
The local first-extraction median was 1.76 s (range 1.70–3.41 s), each run
rendered the JavaScript text through the egress proxy, the public HTTPS
`CONNECT` check returned `Example Domain`, and the same local URL was refused
under the default private-network policy. These are single-host functional
timings, not a page-corpus latency claim.

Interpretation rules:

- **Precision is labelled-domain precision**, not human-judged relevance. A
  useful Stack Overflow page for a docs query still counts as wrong if the
  label names the official docs domain. Report raw counts, not only ratios.
- **Top-3 authoritative** means at least one of the first three search results
  matches a labelled domain or URL prefix.
- **Answer support** checks that research findings contain the labelled answer
  terms; it is not an LLM judge.
- Latencies are from one Windows 11 machine and vary with provider throttling
  and network conditions. Cold-start measurements are in
  [`benchmarks/results/2026-10-23_cold_start.md`](benchmarks/results/2026-10-23_cold_start.md).

Cold-start sample (fresh interpreter, OS file cache warm): importing
`weblens.service` took 471 ms median, getting the service and MCP server ready
(including the first `tools/list`) took 2.29 s median, and the first `tiktoken`
count took 0.32 s. A network extraction of `https://example.com/` took 1.78 s;
the HTTP-cache hit took 5.3 ms. A repeated Wikipedia search took 7.4 ms once the
provider response was cached. These are single-machine observations, not a
startup guarantee; the run was taken when CPU load was low but disk activity was
high, and startup remains sensitive to antivirus and disk contention.

Ingress-only sample (in-process ASGI, synthetic handler, 2026-11-08,
`weblens-lab/evaluations/run_ingress_benchmark.py`): 1,000 paced requests over
59.949 s at 1,000 QPM returned 1,000/1,000 HTTP 200s with p50 1.08 ms, p95
1.77 ms, and p99 2.71 ms. A 10,000-request burst across 10 tenants and
concurrency 100 returned 10,000/10,000 HTTP 200s at 1,248 rps with p95 1.40 ms.
The scope is API-key auth, tenant binding, rate limiting, and security headers
only. It excludes MCP tool dispatch, provider/network latency, and the real HTTP
transport, so it is **not** the production 1,000 QPM gate.

Known measured gaps are listed in [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md):
the keyless headline has labelled-domain precision 0.146, top-3 authoritative
0.35, zero conflict recall, and a search p50 of 2.5 s that misses the 1.5 s
target. Tavily clears the accuracy gates in one run but misses both search
latency gates, so it is optional rather than the default.

## Tests

```powershell
uv run pytest -q
uv run ruff check src tests benchmarks
```

The suite covers URL normalization and redirect loops, SSRF/DNS/redirect
defenses, search parsing and filtering, extraction and exact spans, crawl
dedupe/robots, research guards and conflicts, token budgets, and MCP schema,
error mapping, and stateless modern/legacy HTTP behavior. `tests/test_browser_proxy.py`
covers HTTP forwarding, HTTPS-style `CONNECT` tunneling, and refusal of private
destinations. When the optional browser extra is installed,
`tests/test_browser_optional.py` also launches Playwright Chromium against a
local JavaScript shell; otherwise that test is skipped.

CI is defined in [`.github/workflows/weblens-ci.yml`](../.github/workflows/weblens-ci.yml).
It runs lint and the offline test suite on Ubuntu and Windows with Python 3.11
and 3.13. It does not call live providers, so it is deterministic; the live
benchmark remains a manual, recorded run.

The tests use fakes and do not prove live-provider correctness. The benchmark is
the live measurement, and it is allowed to fail.

## Limitations and non-claims

- No LLM synthesis. Research output is evidence, not an answer.
- Keyless search providers are unofficial/best-effort and can throttle or
  change markup. There is no uptime or rate-limit SLA.
- The official MCP conformance suite (0.1.16) was run against stateless HTTP on
  2026-10-27. The meaningful tools-only core passed (`server-initialize`, `ping`,
  `tools-list`, DNS-rebinding protection), but the active suite also reports 21
  failures for optional capabilities and fixture tools outside its four-tool
  surface; this is not a full-conformance claim. The Windows Node runner exits with a
  libuv assertion after saving results. See
  [`docs/PROTOCOL.md`](docs/PROTOCOL.md) and
  [`benchmarks/results/2026-10-27_mcp_conformance.md`](benchmarks/results/2026-10-27_mcp_conformance.md).
- The browser path is optional, disabled by default, and was smoke-tested with
  Playwright Chromium on Windows. It is heuristic (it does not render every
  JavaScript page). It now uses a loopback egress proxy that resolves and pins
  each page destination, but the proxy is in-process and has not been
  independently audited; do not call the browser a sandbox or "SSRF-safe." See
  the threat model.
- Numeric synthesis only accepts claims whose text, heading, or source URL
  carries a topic anchor; generic words such as "maximum" and "size" are not
  enough. Common word units (for example "terabytes" and "bytes") are normalized.
  Conflict detection is conservative and only handles same-unit numeric
  contradictions with overlapping subject tokens.
- Tavily was exercised live on a 58-query run; Brave was not measured because no
  Brave key was available. SearXNG JSON support depends on the instance. No
  unmeasured vendor comparison is claimed.
- The cache is not encrypted. Do not put secrets in queries or cache a private
  intranet through a misconfiguration. `WEBLENS_CACHE_MAX_BYTES` caps logical
  payload, while SQLite/WAL overhead can make the file larger.

## Roadmap

1. Run Brave on the same 58-query set; Tavily cleared accuracy but missed both
   search latency gates. Keep keyless as the zero-key default unless Brave keeps
   the accuracy gain and meets the latency gates.
2. Add a human relevance judgment sheet alongside the labelled-domain metric so
   "relevant but not on the labelled domain" is visible.
3. Improve conflict detection only if it raises recall without false positives
   on the existing set.
4. Add independent process/network-namespace isolation and an external audit for
   the optional browser. The in-process egress proxy now pins page destinations
   and is tested, but it is not a sandbox; keep the browser off by default.
5. Make the official MCP conformance run a reliable CI gate. The suite was run
   against stateless HTTP on 2026-10-27 and the core scenarios passed, but the
   Windows Node runner exits with a libuv assertion and optional-capability
   scenarios are not applicable to a tools-only server.

## License

MIT. See [`LICENSE`](LICENSE).
