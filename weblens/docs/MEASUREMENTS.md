# Measurements

Every number in the README comes from a committed result file in
`benchmarks/results/`. This page records the method and the run history so a
reader can recompute or challenge the numbers.

## Environment

- Windows 11, 16 GB RAM, NVIDIA RTX 3050 6 GB (the GPU is not used by WebLens).
- CPython 3.14.0 via `uv`.
- `mcp` 2.3.0, `httpx` 0.28.1, `httpcore` 1.0.9, `trafilatura` 2.3.1,
  `tiktoken` 0.14.0, `ruff` 0.17.1. The optional browser extra used
  `playwright` 1.64.0.
- Home network; no VPN or external HTTP proxy. The optional browser uses a
  WebLens loopback egress proxy for destination validation. The headline keyless
  runs used no provider API key. A separate Tavily run used a key in the local,
  gitignored `.env`; the key is not recorded in any result.
- Tokenizer for every token number: `tiktoken` `cl100k_base`.

The machine is a laptop, not an isolated benchmark host. Latency includes
provider throttling, DNS, and Wi-Fi variance. The timestamp is UTC.

## Dataset

`benchmarks/queries.jsonl` contains 58 hand-written English queries:

| category | count | purpose |
| --- | --- | --- |
| `docs` | 18 | Official documentation answers; also used for extraction sampling |
| `current_facts` | 10 | Recency-sensitive facts with expected dates/terms |
| `niche_technical` | 12 | Less common programming/tooling questions |
| `unanswerable` | 10 | Fictional, future, proprietary, or joke premises |
| `conflicting` | 8 | Planted numeric contradictions across sources |

Each row has `id`, `category`, `query`, `answerable`, expected answer terms, and
(where applicable) `relevant_domains` / `relevant_url_prefixes`. The labels are
the author's, not independently adjudicated.

## What one benchmark run does

`python -m benchmarks.run`:

1. Constructs the service and MCP server; measures schema tokens.
2. For every query: calls `web_search` with `max_results=5`, `max_tokens=600`.
3. Calls `deep_research` with `max_tokens=900` for every query.
4. For the first 6 `docs` queries that returned a result: calls `extract_url`
   with `max_tokens=1200` on the first result.
5. Records the raw payload, statuses, provider failures, and wall-clock
   milliseconds in JSON.
6. Checks hard gates and returns exit code 1 on any breach.

`--fresh-cache` deletes `benchmarks/.cache` first. The benchmark is sequential
by design; it does not simulate concurrent users.

## Metric definitions

- **search precision@n**: relevant returned URLs / all returned URLs across
  answerable queries. A URL is relevant only if it matches a labelled domain or
  URL prefix. Missing results reduce the denominator, so read it with top-3.
- **top-3 authoritative**: answerable queries with at least one labelled result
  in the first three positions / 40 answerable queries.
- **research answer support**: queries whose verbatim findings contain the
  labelled answer terms / 30 queries with answer terms. It is a term check, not
  a correctness judgment.
- **status match**: agreement between the expected evidence state and the
  returned status, where the dataset defines one.
- **no-result accuracy**: unanswerable queries returned as
  `no_reliable_result` / 10.
- **conflict recall**: conflicting queries flagged `conflicting_sources` / 8.
- **p50 / p95**: nearest-rank percentiles over all non-error calls in the run,
  including provider waits and cache misses.
- **schema tokens**: compact `tools/list` JSON for all four tools, counted with
  `cl100k_base`.

## Run history

| run | configuration | precision | top-3 | support | no-result | conflict | search p50/p95 | extract p50/p95 | research p50/p95 | gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `2026-10-21_mwmbl_filter` | fallback, Mwmbl added | 0.1711 (32/187) | 0.50 (20/40) | 0.9333 (28/30) | 0.10 (1/10) | 0.00 (0/8) | 2118 / 10027 | 171 / 1664 | 8269 / 23477 | fail |
| `2026-10-21_guard_subset` | guard subset (28 queries) | 0.1875 (15/80) | 0.3333 (6/18) | 1.00 (18/18) | 0.80 (8/10) | n/a | 3361 / 3529 | 940 / 1652 | 7923 / 13291 | fail |
| `2026-10-21_fuse_guard` | fuse, short deadlines | 0.0966 (17/176) | 0.30 (12/40) | 0.8667 (26/30) | 0.90 (9/10) | 0.00 (0/8) | 2023 / 2520 | 752 / 1754 | 9037 / 15429 | fail |
| `2026-10-21_final` | fuse, restored DDG, degraded network | 0.1238 (13/105) | 0.225 (9/40) | 0.5667 (17/30) | 0.90 (9/10) | 0.00 (0/8) | 2417 / 3523 | 1561 / 2226 | 7792 / 15394 | fail |
| `2026-10-21_final2` | fuse, DDG 3.5 / Mwmbl 2.5 / Wikipedia 4.0 s | 0.1461 (26/178) | 0.35 (14/40) | 0.7333 (22/30) | 0.90 (9/10) | 0.00 (0/8) | 2512 / 4023 | 641 / 3214 | 8573 / 18637 | fail |
| `2026-10-23_tavily` | Tavily only, fresh cache | 0.2618 (50/191) | 0.65 (26/40) | 0.9667 (29/30) | 0.80 (8/10) | 0.00 (0/8) | 2872 / 5580 | 275 / 1489 | 7271 / 13693 | fail |

`final` is retained as an example of provider degradation: on that run,
DuckDuckGo, Mwmbl, and Wikipedia all timed out on a large fraction of queries.
It is not the headline number and should not be compared directly with a healthy
run.

`final2` is the current headline. It used a fresh cache and the accuracy-first
deadlines. It passes token, citation, uncalibrated-field, answer-support,
no-result, search-p95, extract, research-p95, and schema gates. It fails
labelled-domain precision (0.1461 vs. 0.25), top-3 authoritative (0.35 vs. 0.60),
and search p50 (2512 ms vs. 1500 ms). The command therefore exits 1; that is the
intended behavior.

The `final2` JSON has identical `started_at` and `finished_at` values because the
harness at that time recorded the finish timestamp too early. The per-call rows,
latencies, and summary were unaffected; `benchmarks/run.py` records the timestamp
after the run for future results.

## Keyed provider run: Tavily

Tavily was run as the only search provider with a fresh cache:

```powershell
$env:WEBLENS_SEARCH_PROVIDERS="tavily"
uv run python -m benchmarks.run --fresh-cache --out benchmarks/results/2026-10-23_tavily.json
```

The key was supplied through the local, gitignored `.env`; it is not in the
result file. The run took 10 minutes 10 seconds and used no keyless provider.

| metric | measure | gate | result |
| --- | --- | --- | --- |
| precision@n | 0.2618 (50/191) | ≥ 0.25 | pass |
| top-3 authoritative | 0.65 (26/40) | ≥ 0.60 | pass |
| answer support | 0.9667 (29/30) | ≥ 0.60 | pass |
| no-result accuracy | 0.80 (8/10) | ≥ 0.75 | pass |
| conflict recall | 0.00 (0/8) | reported | gap |
| search p50 / p95 | 2872 / 5580 ms | p50 < 1500, p95 < 5000 | **fail both** |
| extract p50 / p95 | 275 / 1489 ms | p50 < 2500, p95 < 8000 | pass |
| research p50 / p95 | 7271 / 13693 ms | p95 < 20000 | pass |

This is the first recorded run that clears both accuracy gates. It does not
become the default: it requires a key, and it misses both search latency gates.
It is an accuracy/latency trade-off, not a free win. The no-result result also
drops from 9/10 to 8/10 (`no-06` returns `partial` and `no-10` returns `ok`),
which is a reminder that the provider changes more than ranking. The precision
denominator is 191 returned URLs for Tavily versus 178 for `final2`, because
Tavily filled all five slots on more queries; compare the raw counts, not only
the ratios.

This is one live run against 58 labelled queries, not a controlled Tavily-vs-
keyless A/B. Provider load, network conditions, and the labels can all move the
numbers. Do not convert it into a general claim about Tavily's quality.

## Commands

```powershell
uv run python -m benchmarks.run --fresh-cache --out benchmarks/results/2026-10-21_final2.json
uv run python -m benchmarks.cold_start --runs 3 --out benchmarks/results/2026-10-23_cold_start.json
uv run python benchmarks/browser_smoke.py --runs 3 --https-check --out benchmarks/results/2026-10-27_browser_smoke.json
uv run weblens tokens --pretty
```

The result `.json` is the source of truth. The `.md` beside it is generated from
the JSON and is convenient for review only.

## Cold start

`benchmarks.cold_start` launches fresh interpreters for:

- importing `weblens.service`;
- constructing the service and MCP server;
- loading `tiktoken` and counting a first string.

It also measures one Wikipedia network search, three repeated searches that use
the provider HTTP response cache after the first network call, one network
extraction of `https://example.com/`, and three HTTP-cache extraction hits. The
network samples are single observations, not percentiles. Search envelopes are
not cached; only provider HTTP responses and page fetches are.

Result: [`benchmarks/results/2026-10-23_cold_start.json`](../benchmarks/results/2026-10-23_cold_start.json)
(generated Markdown beside it).

| metric | median | min | max |
| --- | --- | --- | --- |
| import `weblens.service` | 471.3 ms | 467.5 ms | 494.0 ms |
| service + MCP server ready | 2290.5 ms | 2006.9 ms | 2491.4 ms |
| first `count_tokens` (tiktoken load) | 320.1 ms | 211.1 ms | 390.6 ms |
| search, Wikipedia network (single sample) | 2121.0 ms | | |
| search, repeated through HTTP cache (3 samples) | 7.4 ms | 6.3 ms | 8.2 ms |
| extract network (single sample) | 1779.0 ms | | |
| extract, HTTP cache + reparse (3 samples) | 5.3 ms | 4.9 ms | 6.2 ms |

The run was taken at low CPU load but with high disk activity, and the OS file
cache was warm. Startup is sensitive to disk, antivirus, and memory pressure.
Treat the table as a single-machine observation, not a startup guarantee. Do not
compare these numbers with the benchmark p50/p95 rows, which measure per-call
latency in an already-running process.

## Browser smoke test

`benchmarks.browser_smoke` starts a local HTTP server that serves an HTML shell
with `<div id="app">` and an inline script, then extracts it through the normal
service with `allow_browser=true`. It also checks that the same URL is refused
under the default private-network policy. The run uses three fresh WebLens
instances so each elapsed time includes Chromium launch; `--https-check` also
renders a public HTTPS page to exercise the proxy's `CONNECT` + TLS path.

```powershell
uv sync --extra browser
uv run playwright install chromium
uv run python benchmarks/browser_smoke.py --runs 3 --https-check --out benchmarks/results/2026-10-27_browser_smoke.json
```

Result: [`benchmarks/results/2026-10-27_browser_smoke.json`](../benchmarks/results/2026-10-27_browser_smoke.json).

| metric | value |
| --- | --- |
| runs | 3 |
| first extract including Chromium launch, median | 1761.5 ms |
| min / max | 1702.6 / 3413.0 ms |
| extract status / warnings | `ok` / `browser_rendered` |
| passages / tokens | 1 / 182 per run |
| proxy requests per run | 1 / 1 / 1 |
| rendered JavaScript text found | yes, all runs |
| same URL under default policy | `error` (`blocked_url`) |
| public HTTPS check | `ok`, 2117.9 ms, `Example Domain`, 1 proxy request |

This is a functional smoke test, not a page-corpus latency benchmark. Every
local run passed through the egress proxy. The proxy resolves and pins the
destination IP, but it is in-process and unaudited; see the browser residual in
the threat model. The 2026-10-24 run (median 2305.9 ms, public HTTPS 4846.1 ms)
is retained for comparison, as is the earlier single local run (2026-10-23,
3231.8 ms) taken before the proxy.

## MCP conformance run

`@modelcontextprotocol/conformance` 0.1.16 (active suite) was run against
`uv run weblens serve --http --host 127.0.0.1 --port 8765` on 2026-10-27 with
Node v24.19.0. The suite does not filter scenarios to advertised capabilities.

Result: [`benchmarks/results/2026-10-27_mcp_conformance.json`](../benchmarks/results/2026-10-27_mcp_conformance.json).

| metric | value |
| --- | --- |
| scenarios | 30 |
| checks passed | 9 |
| checks failed | 21 |
| warnings | 1 |
| scenarios fully passed | 8 |
| meaningful core | `server-initialize` 1/1, `ping` 1/1, `tools-list` 1/1, `dns-rebinding-protection` 2/2 |
| transport | Streamable HTTP, stateless |
| runner exit | Windows libuv assertion after results were saved |

The 21 failures are optional logging/completion/resources/prompts/elicitation/
sampling capabilities or the suite's fixture tools, not the four WebLens tools.
`tools-call-simple-text` and `tools-call-error` are not counted as meaningful:
they pass when the server returns an unknown-tool error. See the report for the
full limitation list.

## Reproducibility limits

- Live providers change. A rerun is not expected to match row-for-row.
- Provider HTTP responses are cached with provider-specific TTLs (300-1800 s).
  A repeated search can hit that cache, but full search envelopes are not
  cached, so there is no warm-search p50 claim.
- There is no human relevance judgment or LLM judge. Do not convert these
  metrics into a claim of answer correctness.
- Brave and SearXNG were not measured. Tavily has a separate recorded run; see
  the keyed-provider section.
