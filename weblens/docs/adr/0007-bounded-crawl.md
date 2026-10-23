# ADR 0007: Bounded, robots-aware crawl and map

- Status: Accepted
- Date: 2026-10-21

## Context

A crawler can become an unbounded scanner or a denial-of-service tool. The host
machine is a laptop, not a crawl cluster, and the caller needs a small set of
relevant pages rather than a mirror.

## Decision

- `mode=map`: combine links from the start page with sitemap discovery, cap at
  200 URLs (tool default 10), fetch at most 8 sitemaps, and keep the start URL
  first.
- `mode=crawl`: same-site only, max 30 pages, depth 3, link count and query
  length limits, calendar/archive URL filters, and path-affinity prioritization.
- Respect `robots.txt` with a cached policy; count denied URLs and report
  `robots_denied:<n>`.
- Remove exact and near-duplicate pages (shingle similarity ≥ 0.9).
- Reuse the same SSRF-safe fetcher and extraction pipeline.
- Budget the final payload and prefer the root page and nearby paths.

## Alternatives considered

- **Unbounded crawl:** unacceptable resource and ethical risk.
- **Sitemap-only map:** misses sites without sitemaps; link extraction is a
  fallback.
- **Headless browser for every page:** slow, heavy, and a larger SSRF surface;
  disabled by default.
- **No dedupe:** wastes budget on cookie/login/print variants.

## Consequences

- Map coverage is best-effort and can miss deep pages.
- Path affinity can exclude relevant pages far from the root; the depth cap is
  the escape hatch.
- Robots.txt is honored, but the crawler is not a search-engine-grade polite
  crawler; users should still avoid hammering small sites.
- The crawl output is evidence-oriented, not a byte-perfect mirror.
