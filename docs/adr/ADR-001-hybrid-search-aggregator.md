# ADR-001: Multi-Provider Hybrid Search Aggregation

## Status
Accepted

## Context
A personal web intelligence engine requires robust, low-latency live web search. Relying entirely on a single commercial API (e.g. Tavily or Brave) introduces operational costs, subscription gates, and rate limit failures. Relying solely on self-hosted SearXNG leads to upstream bot-blocking on residential/developer IPs. Direct web scrapers (like DuckDuckGo HTML) occasionally face temporary rate limits or regional connection timeouts.

## Decision
Implement a multi-provider fallback aggregator (`SearchAggregator`) that:
1. Queries resilient providers in configurable priority: DuckDuckGo (`ddgs` / HTML), direct Bing with base64 redirect resolution, and Wikipedia REST API.
2. Accepts optional API keys for Brave Search API or self-hosted SearXNG instances without breaking the default zero-config experience.
3. Automatically strips tracking tokens (`utm_*`, `fbclid`, `gclid`, `ref`) from all URLs.
4. Enforces domain diversity (maximum 2 results per top-level domain).
5. Deduplicates results by normalized URL.
6. Caches successful responses in an in-memory TTL cache with query hash keys (never caching empty/failed responses).

## Consequences
- **Positive**: Zero cost out of the box; resilience against individual provider downtime; sub-second p50 latency for direct providers; clean normalized URLs.
- **Negative**: HTML scraping formats can change over long periods, requiring maintenance of provider parsing logic.
