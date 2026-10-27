# Comparison

WebLens is compared here on architecture and on measurements produced by this
repository. Only Tavily was exercised live; Brave, SearXNG, and the hosted
crawl/extract services were not. Vendor quality, price, quota, and uptime are
**not** measured as a controlled benchmark. Rows marked "not verified" must not
be read as endorsements or as losses.

## Category matrix

| Capability | WebLens | Tavily API | Brave Search API | SearXNG (self-hosted) | Firecrawl | Crawl4AI | Official MCP fetch server |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Primary deployment | Local Python + MCP | Hosted API | Hosted API | Self-hosted service | Hosted API | Local Python library | Local Python + MCP |
| Key required by default | No | Yes | Yes | No (self-hosted) | Yes | No | No |
| Web search | Yes, keyless providers | Yes | Yes, independent index | Metasearch aggregation | Search + scrape | Crawling, not a search index | No |
| Page extraction | Yes (HTML/PDF/plain) | Yes | No (search API) | Via upstream engines | Yes | Yes | Yes, single page |
| Site map / crawl | Yes, bounded, robots-aware | Yes (hosted) | No | No | Yes (hosted) | Yes | No |
| Evidence spans (`[start,end]`) | Yes, cleaned-text character spans | Not in the basic search response | No | Depends on engine | Markdown/JSON, not span-first | Markdown, not span-first | Raw markdown/text |
| Explicit no-result / conflict / stale states | Yes (deterministic) | Not a documented contract | No | No | No | No | No |
| Token budget enforced on final payload | Yes, `cl100k_base` | Caller-controlled | Caller-controlled | Caller-controlled | Caller-controlled | Caller-controlled | Caller-controlled |
| LLM synthesis | **No** (by design) | Optional answer | No | No | Optional | Optional | No |
| Measured in this repo | Yes | Yes, one 58-query run | Blocked (no key) | Unverified | No | No | No |

Notes:

- Tavily's exact free-tier quota and current response schema are not asserted
  here. The adapter targets its search API and was exercised live on
  2026-10-23; the raw run is in `docs/MEASUREMENTS.md`. Tavily's scoring fields
  are deliberately discarded.
- Brave's official API is the preferred keyed provider for reliability. The
  adapter exists, but no key was available, so it was not measured. Brave's HTML
  results page disallows crawling via `robots.txt`, so WebLens does not scrape
  it.
- SearXNG's JSON API is commonly disabled on public instances. A self-hosted
  instance with `format=json` enabled is required; none was verified.
- Firecrawl and Crawl4AI are crawl/extraction tools, not search engines. They
  are listed to separate "search" from "extract/crawl", not as direct
  substitutes.
- The official MCP fetch server is a minimal single-URL fetch, not a search or
  research system. It is useful as a baseline for tool-surface size, not for
  answer quality.

## WebLens run history (not a controlled A/B)

These numbers come from the committed dataset and result files. Provider
behavior, timeouts, and code changed between runs, so treat the rows as
operating points, not as a clean ablation.

| run | precision@n | top-3 authoritative | answer support | no-result | conflict recall | search p50/p95 ms | research p50/p95 ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `2026-10-21_mwmbl_filter` | 0.1711 (32/187) | 0.50 (20/40) | 0.9333 (28/30) | 0.10 (1/10) | 0.00 (0/8) | 2118 / 10027 | 8269 / 23477 |
| `2026-10-21_guard_subset` (docs+unanswerable only) | 0.1875 (15/80) | 0.3333 (6/18) | 1.00 (18/18) | 0.80 (8/10) | n/a | 3361 / 3529 | 7923 / 13291 |
| `2026-10-21_fuse_guard` | 0.0966 (17/176) | 0.30 (12/40) | 0.8667 (26/30) | 0.90 (9/10) | 0.00 (0/8) | 2023 / 2520 | 9037 / 15429 |
| `2026-10-21_final` (degraded network) | 0.1238 (13/105) | 0.225 (9/40) | 0.5667 (17/30) | 0.90 (9/10) | 0.00 (0/8) | 2417 / 3523 | 7792 / 15394 |
| `2026-10-21_final2` | 0.1461 (26/178) | 0.35 (14/40) | 0.7333 (22/30) | 0.90 (9/10) | 0.00 (0/8) | 2512 / 4023 | 8573 / 18637 |
| `2026-10-23_tavily` (Tavily only) | 0.2618 (50/191) | 0.65 (26/40) | 0.9667 (29/30) | 0.80 (8/10) | 0.00 (0/8) | 2872 / 5580 | 7271 / 13693 |

Interpretation:

- The short-deadline fuse run cut search p95 dramatically (10.0 s → 2.5 s) and
  improved no-result accuracy (0.1 → 0.9), but lost labelled-domain hits because
  slow providers were cancelled while they still held useful results. Accuracy
  is the higher priority, so the headline configuration uses 3.5 s DuckDuckGo,
  2.5 s Mwmbl, and 4.0 s Wikipedia deadlines.
- The headline run `final2` trades p50 (2.51 s) and p95 (4.02 s) for better
  labelled-domain precision (0.146), top-3 (0.35), and answer support (0.733)
  than the short-deadline run. It still fails the precision, top-3, and search
  p50 gates. It passes the search p95, answer-support, no-result, extract,
  research-p95, schema, token, citation, and confidence gates.
- The `final` run is retained as a provider-degradation sample, not a clean
  comparison: 26 of 48 non-unanswerable queries lost DuckDuckGo, 26 lost
  Wikipedia, and 31 lost Mwmbl (queries can lose more than one provider). Do not
  use it as the headline.
- `2026-10-23_tavily` is the first run to clear both accuracy gates (precision
  0.262, top-3 0.65, support 0.967). It fails both search latency gates
  (p50 2.87 s, p95 5.58 s) and its no-result accuracy falls to 0.80. It is an
  optional accuracy-first trade-off, not the default. The keyless and Tavily runs
  are separate operating points, not a controlled vendor A/B.
- `answer support` is term containment in verbatim findings, not an LLM or human
  correctness judgment.
- `conflict recall` is 0/8 in every full run. This is a real gap, not a reporting
  artifact. The detector is deliberately conservative.
- Precision uses labelled domains, so useful results on unlabelled domains are
  counted as false positives. Human relevance was not independently judged.

## Three-axis decision record

Priority order from the project brief: (1) no fake accuracy, (2) accuracy,
(3) tokens, (4) latency.

| choice | tokens | accuracy evidence | latency evidence | decision |
| --- | --- | --- | --- | --- |
| Four compact tools, short-key JSON | 838 schema; 0 budget violations | No effect measured | Lower serialization cost, not isolated | Keep |
| Keyless default `ddg,mwmbl,wikipedia` | No extra schema | Precision 0.146, top-3 0.35, support 0.733 in final2 | p50 2.51 s, p95 4.02 s cold | Keep as zero-key default, document variability |
| Tavily only (key required) | No extra schema | Precision 0.262, top-3 0.65, support 0.967 in one run | p50 2.87 s, p95 5.58 s | Optional accuracy-first; fails both latency gates |
| Fuse with short deadlines | No effect | Precision 0.097, top-3 0.30, support 0.867 | p50 2.02 s, p95 2.52 s | Rejected: loses labelled results |
| Fuse with 3.5/2.5/4.0 s deadlines | No effect | Precision 0.146, top-3 0.35, support 0.733 | p50 2.51 s, p95 4.02 s | Keep: better accuracy, p95 under 5 s |
| Deterministic research (no LLM) | 2,000 budget | 0.733–0.933 term support; no synthesis | p95 15.4–18.6 s | Keep; synthesis not justified by measurement |
| Browser rendering | Larger dependency | Smoke-tested; heuristic, not a quality claim | Seconds per first page; smoke result recorded | Off by default; loopback egress proxy pins page destinations, but process isolation/audit remains |
| Crawl/map | Bounded 30 pages | No quality label; structural only | Not in headline latency | Keep, documented as best-effort |

## What would change the decision

1. **Brave keyed measurement.** Tavily cleared the accuracy gates but failed
   both search latency gates. Run Brave on the same 58 queries; if it keeps the
   accuracy gain and gets p50/p95 under 1.5/5 s, it should become the preferred
   keyed provider. Keep the keyless chain as the zero-key fallback.
2. **Human relevance labels.** A second label set that credits relevant content
   on any domain would separate "ranking problem" from "label-domain problem".
3. **Conflict-focused set.** The current 8 conflicting queries are too few and
   too narrow to tune a detector. Add numeric, date, and version conflicts from
   independent sources before changing the heuristic.
4. **Warm-cache percentile.** Report cold and warm search latency separately
   after the search-envelope cache exists; provider HTTP responses are already
   cached, but a repeated search still rebuilds the envelope and ranking.

## Unverified or blocked comparisons

- **Tavily quota and pricing:** a live search run was recorded, but the
  free-tier quota, current pricing, and long-term quality were not verified.
- **Brave official API:** no `BRAVE_API_KEY`; not run.
- **Public SearXNG:** no instance with verified JSON output; not run.
- **Playwright/Chromium:** smoke-tested on Windows with Playwright Chromium;
  the browser path remains optional and routes page traffic through an
  in-process egress proxy. DNS is resolved and pinned per connection, but the
  proxy is not an independent sandbox and has not been audited.
- **Official MCP conformance suite:** 0.1.16 active suite run on 2026-10-27
  against stateless HTTP. The tools-only core scenarios passed; 21
  optional-capability/fixture-tool scenarios failed, and the Windows Node runner
  asserts after saving results. This is not a full-conformance claim. See
  `PROTOCOL.md` and `benchmarks/results/2026-10-27_mcp_conformance.md`.

Claims about these systems in this repository are limited to public,
architectural facts and are marked unverified where measurement would be
required.
