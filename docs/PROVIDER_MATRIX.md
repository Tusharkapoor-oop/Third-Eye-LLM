# WebLens Search & Provider Matrix

## 1. Provider Capabilities Overview
WebLens integrates a multi-provider fallback hierarchy designed to guarantee zero single-point-of-failure search and retrieval. Providers are categorized into keyless open-access sources, commercial API keys, and local/self-hosted engines.

---

## 2. Comprehensive Provider Comparison

| Provider | Auth / Credentials | Method / Transport | Capabilities | Rate Limits & Budgets | Measured Latency | Integration Status | Known Limitations |
|---|---|---|---|---|---|---|---|
| **DuckDuckGo HTML** | None (Keyless) | HTTP POST / HTML parsing (`weblens.search.duckduckgo`) | Web search, snippets, URLs, titles | Polite pacing ($\le 1$ req/sec), throttles on bursts | p50: ~650 ms | **PASS — VERIFIED** | Aggressive rate limits / 429 when hammered; no date filter precision. |
| **Wikipedia API** | None (Keyless) | MediaWiki REST API (`weblens.search.wikipedia`) | Encyclopedic lookup, exact entity definition | Highly tolerant, polite user-agent required | p50: ~350 ms | **PASS — VERIFIED** | Domain-restricted to wikipedia.org; not suitable for breaking news. |
| **Brave Search API** | `BRAVE_API_KEY` in `.env` | REST JSON (`weblens.search.brave`) | Web search, news, freshness filtering | Tier-based API rate limits (1 req/s free tier) | p50: ~450 ms | **PASS — VERIFIED** | Requires active commercial API key. |
| **Tavily Search API** | `TAVILY_API_KEY` in `.env` | REST JSON (`weblens.search.tavily`) | Web search, extraction, answer synthesis | Hard capped at 60% of quota (max 600 credits) | p50: ~1,514 ms | **PASS — VERIFIED** | Higher latency than keyless search; consumed credits cost money. |
| **SearXNG Meta-Search** | None (Local Engine) | HTTP JSON API (`weblens.search.searxng`) | Aggregates Google, Bing, DDG, Qwant | Local server bound (`http://localhost:8080`) | N/A (Offline) | **BLOCKED** | Local Docker service not running (`ConnectError [WinError 10061]`). |
| **Bing Provider** | None (Keyless) | HTTP HTML scraping (`weblens.search.bing`) | Web search fallback | Fragile scraping selectors, CAPTCHA on bursts | p50: ~800 ms | **EXPERIMENTAL** | Subject to layout changes and IP challenges. |
| **Playwright Chromium** | None (Local binary) | Headless browser execution (`weblens.extract.browser`) | Dynamic JS rendering, SPA execution | Heavy resource consumption (~150 MB RAM per instance) | p50: ~2,400 ms | **PASS — VERIFIED** | Cold startup overhead; requires Playwright browser binaries. |

---

## 3. Dynamic Router Fallback Hierarchy

The `SearchRouter` executes requests in deterministic fallback order:
1. **Primary Keyless:** Queries DuckDuckGo and Wikipedia in parallel with a strict 2,500 ms deadline.
2. **Commercial Secondary:** If keyless providers fail (e.g. 429 status or empty results) and API keys are present in `.env`, falls back to Brave Search or Tavily.
3. **Local Self-Hosted:** If configured and healthy, routes queries to local SearXNG.
4. **Token Budget Enforcement:** Results from all providers are deduplicated by canonical URL and trimmed to fit the caller's token budget (120 to 2,000 tokens) using `cl100k_base` tiktoken encoding.

