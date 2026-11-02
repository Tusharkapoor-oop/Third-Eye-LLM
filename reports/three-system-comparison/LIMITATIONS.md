# System Limitations & Gap Analysis (V9)

## Observed Limitations of WebLens vs Tavily

1. **Long-tail and Niche Academic Precision**:
   - Tavily demonstrated higher search precision on academic and deep technical queries (e.g. arXiv paper author lookups, semiconductor hardware details), achieving **0.653** Precision@5 vs WebLens **0.413**.
   - **Root Cause**: WebLens currently queries DuckDuckGo, Mwmbl, and Wikipedia in its default keyless chain. When DuckDuckGo lacks indexing for highly niche terms or rates limits rapid bursts, precision drops.
   - **Remediation**: Integrate ArXiv, PubMed, and Brave search backends into the default fallback chain.

2. **JavaScript-Intensive Single Page Applications**:
   - When Playwright Chromium headless is disabled (`allow_browser=False`), pages that require dynamic client-side DOM rendering cannot be extracted by HTTP fast-path fetchers.
   - **Remediation**: Enable egress-proxied Playwright fallback on a per-host basis.

3. **Rate Limiting on Free Search Engines**:
   - Public DDG HTML endpoints occasionally return HTTP 202 or rate-limit responses during rapid unthrottled bursts.
   - **Remediation**: Maintain the polite concurrency semaphore (default max 2 requests per host) and connection pool reuse.

