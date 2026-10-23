# Research report: a local-first web evidence engine

Date: 2026-10-21

## 1. Question

Can a local, model-independent service give an AI agent useful live web
evidence on a mid-range Windows laptop, with:

- no mandatory paid API keys,
- exact, verifiable citations rather than prose,
- small, enforced output budgets,
- explicit uncertainty instead of confidence scores,
- and a security posture suitable for fetching arbitrary URLs?

The deliverable is not a better chatbot. It is a retrieval and evidence layer
that any MCP-capable model can call.

## 2. Method

1. Review the MCP transport and tool model used by the available Python SDK
   (`mcp` 2.3.0), including the modern stateless flow and legacy initialize
   flow.
2. Implement a service with four tools and a provider router.
3. Build a 58-query labelled dataset spanning docs, current facts, niche
   technical questions, unanswerable questions, and conflicting claims.
4. Run the dataset through search, research, and a sample of extractions on a
   Windows 11 machine (Python 3.14.0, 16 GB RAM, RTX 3050 6 GB). Record raw rows
   and p50/p95 latencies.
5. Add deterministic refusal guards for claims that cannot be supported, then
   re-run the subset and full set.
6. Measure cold start, cache hits, and schema tokens.
7. Record decisions as ADRs and limitations as explicit non-claims.

The cold-start run measured 471 ms median to import the service, 2.29 s to get
the service and MCP server ready (including the first `tools/list`), and 0.32 s
for the first tokenizer load on a host with low CPU load but high disk activity.
A cached extraction took 5.3 ms. These are in
[`benchmarks/results/2026-10-23_cold_start.json`](../benchmarks/results/2026-10-23_cold_start.json);
they are not a startup guarantee.

No human relevance study, vendor API comparison, formal MCP conformance run, or
security audit was possible in this environment. Those gaps are stated, not
estimated.

## 3. Landscape

### Hosted search APIs

Tavily and Brave expose search (and, for Tavily, extraction) as a hosted API.
They are the obvious reliability upgrade, but require keys and quotas. Their
current pricing and free-tier limits were not verified here because no keys were
available. WebLens includes adapters but does not claim measured parity.

### Metasearch

SearXNG can aggregate engines locally, but JSON output is commonly disabled on
public instances and a self-hosted instance adds operational work. No instance
was verified.

### Crawl/extract tools

Firecrawl and Crawl4AI focus on turning pages or sites into clean markdown. They
are useful complements, not search engines. WebLens includes a small,
robots-aware crawl/map because the agent often needs a few pages, not a mirror.

### MCP fetch servers

Minimal MCP fetch servers expose one URL fetch. They are a good baseline for
tool size, but do not provide search, ranking, evidence spans, conflict states,
or budgets.

### Keyless web search

DuckDuckGo Lite is the most useful keyless general web endpoint, but its HTML is
unofficial and it throttles. Mwmbl is a small public index with a JSON API.
Wikipedia's API is reliable but encyclopedic. The measured system uses all three
and records failures rather than pretending one is a stable contract.

## 4. Protocol findings

The Python SDK used here identifies `2026-07-28` as the latest protocol version
and supports a stateless per-request flow: no `initialize`, a version in
per-request `_meta`, and no `Mcp-Session-Id`. The same server also completes a
legacy `2025-11-25` `initialize` and a following `tools/list` without a session.

Tests assert those two message flows. They do **not** constitute official
conformance. `2025-06-18`, `2025-03-26`, and `2024-11-05` are not directly
tested. Details and raw request shapes are in `PROTOCOL.md`.

Design consequence: keep the tool surface stateless. Sessions are a
compatibility switch, not a place to store research state.

## 5. Architecture findings

### Search

Parallel provider fusion is necessary. Sequential fallback makes p95 depend on
the slowest failed provider. Per-provider deadlines prevent a hung low-value
provider from dominating, but shortening the primary provider's deadline to hit
a p50 target **reduces accuracy**: slow DuckDuckGo responses often contain the
labelled authoritative result.

Measured operating points:

| configuration | precision@n | top-3 | search p50/p95 |
| --- | --- | --- | --- |
| earlier fallback/filter run | 0.1711 | 0.50 | 2118 / 10027 ms |
| fuse, short deadlines | 0.0966 | 0.30 | 2023 / 2520 ms |
| fuse, 3.5/2.5/4.0 s deadlines | 0.1461 | 0.35 | 2512 / 4023 ms |

The short-deadline run is faster at p95 and detects more unanswerables, but loses
labelled results. Given the stated priority (accuracy before latency), the
headline configuration uses 3.5 s DuckDuckGo, 2.5 s Mwmbl, and 4.0 s Wikipedia
deadlines. It still misses the 1.5 s p50 target (2.51 s) and the precision/top-3
gates; those are reported, not argued away. The earlier fallback run has higher
precision but a 10 s p95 and predates the current fuse/provider changes, so it is
not a clean A/B comparison.

### Evidence research

A deterministic loop can produce high term-level support (0.733-0.933) without
an LLM. It cannot synthesize or resolve paraphrases, and its p95 (15-19 s) is too
slow for interactive use on every query. It is best treated as a deliberate
"collect evidence" call, not a default search replacement.

### No-result behavior

The initial engine almost never returned `no_reliable_result` on unanswerable
queries (1/10). Deterministic guards raised this to 9/10:

- sensitive requests,
- explicit future years,
- proprietary source requests,
- fictional entities absent from the evidence,
- unsupported `exact`/`precise` modifiers.

This is a large behavioral improvement, not a claim of general truthfulness. A
joke premise with real-looking pages can still produce `partial`.

### Token budgets

Hard budgets on the final serialized payload are enforceable and were never
violated in the benchmark (0 violations across all calls). The four-tool schema
is 838 `cl100k_base` tokens. Compact JSON and short keys are doing real work:
the schema is under the 1,000-token target, and default results fit in 600
tokens.

The cost is readability; callers must learn the short-key contract. Structured
output was rejected because it increases the schema and duplicates information
already in the JSON.

### Extraction and crawl

Trafilatura fast mode plus cheap lxml metadata is the right default. Full
metadata extraction was measured at 1.4–3.7 s and rejected. Exact spans into the
cleaned text work and are citation-checkable, but they are not original HTML
offsets.

PDF extraction initially imported `pypdf`, which was not a declared dependency —
a clean install would have failed at runtime. It was replaced with the already
declared PyMuPDF and covered by a generated-PDF test. This is an example of why
the dependency and test audit matters more than a demo.

Crawl/map is best-effort: sitemaps when available, link extraction otherwise,
same-site and robots-aware, with duplicate removal. It is not a search engine
crawler.

## 6. Security findings

The key control is connection-time IP validation. A pre-flight hostname check is
insufficient against DNS rebinding; the socket must be opened to the validated
IP. Redirects must be revalidated per hop, and literal private IPs must be
rejected even if they appear as "hostnames". All of these are unit-tested.

Prompt injection is treated as a data/instruction separation problem, not a
classification problem. The engine flags common patterns and HTML-comment
instructions, but the real control is that the MCP server exposes no write,
shell, email, or payment tool. The calling model must still preserve the
boundary.

The optional browser is the largest residual risk: Chromium resolves DNS
independently, so hostname checks do not pin the destination IP. It is disabled
by default, and the threat model says so plainly.

## 7. Trade-offs

| Axis | Finding | Decision |
| --- | --- | --- |
| Accuracy | Labelled-domain precision is low (0.10–0.17); answer support is high (0.87–0.93) | Keep evidence-first design; report both; do not claim human relevance |
| Tokens | 838-token schema, 0 budget violations | Keep compact JSON and hard budgets |
| Latency | Search p50 2.5 s cold, p95 4.0 s; research p95 15-19 s | Accept search p50 miss for accuracy; keep research opt-in |
| Security | Strong SSRF tests, no audit; browser path weaker | Defaults: loopback, no private nets, no browser |
| Protocol | Two message flows verified, no conformance suite | State exact evidence, not "fully compliant" |

## 8. What was not established

- No comparison with Tavily or Brave because no keys were available.
- No public SearXNG instance with verified JSON output.
- No Chromium/Playwright run.
- No official MCP conformance suite.
- No human relevance judgments; precision is labelled-domain precision.
- No conflict-detector improvement: recall stayed at 0/8.
- No Linux/macOS measurement.

These are blockers for stronger claims, not footnotes to hide.

## 9. Recommendations

1. **Measure a keyed provider first.** Run Brave and Tavily on the same dataset
   with the same budgets. If either clears the accuracy gates without a p95
   regression, make it the preferred provider and keep the keyless chain as
   fallback.
2. **Add human relevance labels.** Separate "not on the labelled domain" from
   "not relevant." The current precision number conflates them.
3. **Keep the accuracy-first deadline.** Do not shorten the primary provider's
   deadline just to make p50 look better.
4. **Report warm and cold latency separately.** Provider HTTP responses are
   cached, but the full search envelope is rebuilt on every call. Do not assume
   cache hits are the common case without a workload measurement; add the
   envelope cache and measure it before quoting a warm p50.
5. **Treat research as a deliberate call.** 15-19 s p95 is acceptable for
   evidence collection, not for every turn.
6. **Do not enable the browser by default.** Pin DNS or isolate the browser
   process before calling it SSRF-safe.
7. **Improve conflict detection only with data.** The current 8-query conflict
   set is too small to tune against.

## 10. References

- MCP specification and SDK: <https://modelcontextprotocol.io/>,
  <https://github.com/modelcontextprotocol/python-sdk>
- DuckDuckGo Lite: <https://lite.duckduckgo.com/lite/>
- Mwmbl API: <https://api.mwmbl.org/search/>
- Wikipedia API: <https://www.mediawiki.org/wiki/API:Main_page>
- trafilatura: <https://github.com/adbar/trafilatura>
- tiktoken: <https://github.com/openai/tiktoken>
- PyMuPDF: <https://pymupdf.readthedocs.io/>
- Reproducible raw data: `benchmarks/results/`, `benchmarks/queries.jsonl`,
  `benchmarks/run.py`, `benchmarks/cold_start.py`
