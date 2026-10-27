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

No human relevance study, controlled vendor benchmark, complete formal MCP
conformance run, or security audit was possible in this environment. The partial
conformance run is recorded below. Those gaps are stated, not estimated.

## 3. Landscape

### Hosted search APIs

Tavily and Brave expose search (and, for Tavily, extraction) as a hosted API.
They are the obvious reliability upgrade, but require keys and quotas. Tavily
was exercised live on 2026-10-23; Brave was not, because no Brave key was
available. Current pricing and free-tier limits were not verified. WebLens
includes both adapters but does not claim measured parity.

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

Tests assert those two message flows. The official conformance suite was also
run on 2026-10-27: the meaningful tools-only core passed, but the active suite
is not filtered to advertised capabilities, reports 21 failures for optional
capabilities/fixture tools, and its Windows Node runner exits with a libuv
assertion after saving results. That is not full conformance. `2025-03-26` and
`2024-11-05` remain untested. Details, raw request shapes, and the conformance
evidence are in `PROTOCOL.md` and
`benchmarks/results/2026-10-27_mcp_conformance.md`.

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

The optional browser was the largest residual risk: Chromium resolves DNS
independently, so hostname checks do not pin the destination IP. It now runs
behind a loopback egress proxy that resolves each HTTP request or HTTPS
`CONNECT` destination once, applies `DestinationPolicy`, and connects to the
validated IP; the proxy's HTTP, tunnel, and private-refusal paths are unit-tested
and the live smoke test exercises both local HTTP and public HTTPS. The proxy is
still in-process and unaudited, so the browser remains disabled by default; the
threat model states the residual plainly.

## 7. Trade-offs

| Axis | Finding | Decision |
| --- | --- | --- |
| Accuracy | Labelled-domain precision is 0.10–0.26; answer support is 0.73–0.97 | Keep evidence-first design; report both; Tavily improves accuracy but is optional |
| Tokens | 838-token schema, 0 budget violations | Keep compact JSON and hard budgets |
| Latency | Keyless search p50 2.5 s, p95 4.0 s; Tavily p50 2.9 s, p95 5.6 s; research p95 13.7–18.6 s | Keep keyless default; Tavily is an accuracy-first option that misses both search latency gates |
| Security | Strong SSRF tests, no audit; browser proxy tested but in-process | Defaults: loopback, no private nets, no browser; keep proxy/process hardening on roadmap |
| Protocol | Two message flows verified; official suite core passed but optional-capability scenarios failed and the Windows runner asserts | State exact evidence, not "fully compliant" |

## 8. What was not established

- Brave was not compared, because no Brave key was available. Tavily has one
  live run, not a controlled vendor bake-off.
- No public SearXNG instance with verified JSON output.
- The browser path is smoke-tested, and its egress proxy is unit-tested, but the
  proxy is in-process and unaudited; it was not measured on a broad page corpus.
- Official MCP conformance is incomplete: the tools-only core passed, but 21
  optional-capability/fixture-tool scenarios failed and the Windows runner
  asserts after saving results. No full-conformance claim is made.
- No human relevance judgments; precision is labelled-domain precision.
- No conflict-detector improvement: recall stayed at 0/8.
- No Linux/macOS measurement.

These are blockers for stronger claims, not footnotes to hide.

## 9. Recommendations

1. **Measure Brave next.** Tavily cleared the accuracy gates in one 58-query run
   but failed both search latency gates (p50 2.87 s, p95 5.58 s), so it remains
   optional. Brave is the remaining keyed provider with a plausible latency
   advantage; measure it before changing the default. Keep the keyless chain as
   the zero-key fallback.
2. **Add human relevance labels.** Separate "not on the labelled domain" from
   "not relevant." The current precision number conflates them.
3. **Keep the accuracy-first deadline.** Do not shorten the primary provider's
   deadline just to make p50 look better.
4. **Report warm and cold latency separately.** Provider HTTP responses are
   cached, but the full search envelope is rebuilt on every call. Do not assume
   cache hits are the common case without a workload measurement; add the
   envelope cache and measure it before quoting a warm p50.
5. **Treat research as a deliberate call.** 13.7-18.6 s p95 is acceptable for
   evidence collection, not for every turn.
6. **Keep the browser off by default.** The egress proxy now pins each page
   destination, but it is in-process and unaudited. Add process/network
   isolation and an independent review before treating the browser as a
   security boundary.
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
