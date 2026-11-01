# Red-Team Scope Manifest, Target Boundaries, and Threat Model

**Document ID:** `reports/redteam/00-scope-and-threat-model.md`  
**Execution Date:** 2026-10-27  
**Auditor Mode:** Authorized Principal Security Engineer, Application Security Red-Team Lead, Benchmark Statistician  
**Target Subject:** WebLens & WebIntel Autonomous Intelligence Engines  
**Target Environment:** Localhost / Owned Local Test Fixtures (Windows 11 x64, Python 3.13.15, Node 24.19.0)  
**Classification:** STRICT AUDIT EVIDENCE — AUTHORIZED RED-TEAM CAMPAIGN  

---

## 1. Authorized Scope Manifest & Safety Boundaries

### 1.1 In-Scope Owned Assets
The authorized penetration testing and hostile evaluation encompass only local components and owned code within the repository:
1. **WebLens Application & CLI** (`weblens/src/weblens/cli.py`, `weblens/src/weblens/service.py`).
2. **MCP Server Interfaces** (`src/server/mcp_server.py`, `weblens/src/weblens/mcp_server.py`).
3. **Browser Egress Proxy** (`weblens/src/weblens/net/browser_proxy.py`).
4. **Browser Fallback & Automation** (`src/engine/extract/browser_fallback.py`, `weblens/src/weblens/extract/browser.py`).
5. **Network Layer & Destination Policy** (`src/engine/security.py`, `weblens/src/weblens/net/ssrf.py`, `client.py`).
6. **Parsing, Extraction & Sanitization Pipeline** (`src/engine/extract/`, `src/engine/security.py`, `weblens/src/weblens/extract/`, `weblens/src/weblens/security/injection.py`).
7. **SQLite Storage & Cache Subsystems** (`weblens/src/weblens/cache.py`, `test-results/database/`).
8. **Search Provider Adapters** (DDGS, Wikipedia, Bing, Tavily adapter logic).

### 1.2 Out-of-Scope Assets & Third-Party Boundaries
- **Tavily Infrastructure:** Tavily is a third-party commercial search provider. In accordance with Section 1.2 of Master Directive V2, NO penetration testing, denial-of-service, authentication bypass, or infrastructure probing is permitted against `api.tavily.com`. Testing is restricted strictly to authorized API queries within authorized rate/budget caps.
- **External Public Services:** Search engines (DuckDuckGo, Wikipedia, Bing) and public websites are queried only through standard client HTTP requests. No destructive testing or traffic flooding is permitted.
- **Unrelated Local Processes & Private Networks:** No probing of lateral hosts or internal corporate subnets.

### 1.3 Emergency Stop Conditions
Any testing activity must cease immediately upon detection of:
1. Accidental transmission or exposure of API credentials (`TAVILY_API_KEY`, Bearer tokens).
2. Unintended outbound traffic to unverified private networks or cloud metadata IP (`169.254.169.254`).
3. Process instability causing unbounded CPU/memory consumption (>80% host RAM).
4. Permanent test data corruption or accidental modification of preserved working-tree code.

---

## 2. Architectural Data-Flow Diagram

```
+---------------------------------------------------------------------------------------------------+
|                                      MCP CLIENT / CALLER                                          |
+---------------------------------------------------------------------------------------------------+
                                                  | JSON-RPC 2.0 (Streamable HTTP / stdio)
                                                  v
+---------------------------------------------------------------------------------------------------+
|                                   WEBLENS / WEBINTEL MCP SERVER                                   |
|   - Input Schema Validation & Type Sanitization                                                   |
|   - Tool Dispatcher: web_search, extract_url, crawl_site/website, web_map, deep_research          |
+---------------------------------------------------------------------------------------------------+
             |                                              |
             | Search Intent                                | Fetch / Extract Intent
             v                                              v
+-------------------------------------------+  +----------------------------------------------------+
|          SEARCH ROUTER / AGGREGATOR       |  |               EXTRACTION SERVICE                   |
| - Keyless: DDGS Scraper (HTML/Lite)       |  | 1. Fast Direct HTTP Fetch via SafeNetworkBackend   |
| - Keyless: Wikipedia REST API             |  | 2. SSRF Destination Validation pre-connect         |
| - Keyless: Bing HTML Fallback             |  | 3. SQLite Cache Lookup / Insertion                 |
| - Commercial: Tavily Direct API (Authed)  |  | 4. Trafilatura / BeautifulSoup HTML Parsing        |
| - Result Dedup, Authoritative Boost,      |  | 5. Lexical Passage Scoring & Context Slicing       |
|   Token Budget Enforcement                |  | 6. Untrusted Content Sanitizer & Injection Guard   |
+-------------------------------------------+  +----------------------------------------------------+
                                                                    | Insufficient Content (SPA)
                                                                    v
                                               +----------------------------------------------------+
                                               |             BROWSER AUTOMATION LAYER               |
                                               | Path A (weblens): Playwright + BrowserEgressProxy  |
                                               |   - Ephemeral loopback proxy (pins DNS to safe IP) |
                                               | Path B (engine): subprocess msedge/chrome.exe      |
                                               |   - Native Windows CLI --dump-dom (UNPROXIED)      |
                                               +----------------------------------------------------+
```

---

## 3. Threat Model & Attack Surface Catalog (STRIDE / DREAD)

| Threat ID | Threat Category | Target Component | Threat Vector & Attack Mechanism | Severity | Inherent Risk | Mitigations in Codebase |
|---|---|---|---|---|---|---|
| **THREAT-01** | **Elevation of Privilege / Info Disclosure** | Egress Network / HTTP Fetcher | **SSRF & Cloud Metadata Access:** Attacker submits `http://169.254.169.254`, `http://127.0.0.1:8080`, `http://[::1]`, octal/hex IP notations, or DNS rebinding domains to access local services or cloud IAM credentials. | **CRITICAL** | High | `src/engine/security.py:validate_url_security`, `weblens/src/weblens/net/ssrf.py:DestinationPolicy` pre-connect IP validation. |
| **THREAT-02** | **Elevation of Privilege** | Browser Fallback (`browser_fallback.py`) | **Unrestricted Browser Egress & Subresource SSRF:** `msedge.exe` executed via subprocess without proxy. Malicious web page loads `<iframe src="http://127.0.0.1:8080/admin">` or performs internal CSRF/port scanning. | **HIGH** | High | Fixed in `weblens/src/weblens/net/browser_proxy.py` via DNS-pinned proxy; **remains vulnerable** in `src/engine/extract/browser_fallback.py`. |
| **THREAT-03** | **Tampering / Information Disclosure** | Extraction Pipeline | **Indirect Prompt Injection:** Malicious web pages embed adversarial directives (`<!-- Ignore prior instructions... -->`, zero-width steganography, role hijacking) to manipulate host LLM agents. | **HIGH** | High | `sanitize_untrusted_content()` regex and `scan_injection()` pattern matcher strip adversarial tags and flag injection types. |
| **THREAT-04** | **Tampering / Information Disclosure** | SQLite Cache (`cache.py`) | **Cache Key Collision & Cross-User Poisoning:** Requests with identical URLs but differing `Authorization` headers share the same cache key (`cache_key("http", method, url, body)`). | **MEDIUM** | Medium | Response headers filtered (strips `Set-Cookie`), but request authorization headers not keyed. Acceptable for single-tenant local engine; critical if multi-tenant. |
| **THREAT-05** | **Denial of Service** | HTTP Client & Extractors | **Resource Exhaustion & Decompression Bombs:** Malicious upstream returns infinite stream, 100 MB gzip bombs, or thousands of circular redirects. | **MEDIUM** | Medium | `MAX_RESPONSE_BYTES` (5 MB ceiling), `MAX_REDIRECTS` (5 limit), timeouts on connect (5s) and read (10s). |
| **THREAT-06** | **Information Disclosure** | MCP Logging & Error Returns | **Credential & Private Key Leakage:** Unhandled upstream errors dump `TAVILY_API_KEY` into JSON-RPC response or persistent test logs. | **CRITICAL** | High | Active regex redaction `tvly-*`, `sk-*`, `Bearer *` in `benchmark_harness.py` and persistent evidence loggers. |

---

## 4. Historical Hypotheses Verification Matrix

The 9 historical claims cited in Master Directive V2 were audited directly against the active codebase:

1. **Claim: 160 regression tests passed.**  
   *Audit Finding:* **REPRODUCED & VERIFIED.** Running `pytest weblens/tests` collected and executed exactly 160 test cases. All 160 passed (9.5s). In addition, running `pytest tests/` (engine root) collected and passed 237 test cases (96.2s), totaling 397 passing tests across both stacks.
2. **Claim: Browser egress restrictions work.**  
   *Audit Finding:* **PARTIAL / CONTEXT-DEPENDENT.** Verified that `weblens/src/weblens/net/browser_proxy.py` successfully intercepts Playwright traffic through an ephemeral loopback proxy with DNS-pinned IP checking. However, `src/engine/extract/browser_fallback.py` invokes `msedge.exe`/`chrome.exe` directly via subprocess without proxy or subresource restriction.
3. **Claim: WebLens provides a useful latency advantage.**  
   *Audit Finding:* **PARTIAL / REJECTED FOR SEARCH, VERIFIED FOR EXTRACTION.** Tavily direct API achieves ~1.82s p50 network latency, beating WebLens keyless search (~2.87s p50) due to scraper overhead. However, WebLens Adaptive Routing provides a 5.37x speedup for extraction (0.42s direct HTTP vs 2.28s headless browser).
4. **Claim: Cache management is safe and correct.**  
   *Audit Finding:* **VERIFIED WITH DOCUMENTED LIMITATIONS.** SQLite cache enforces WAL mode, thread locking, TTL expiration, gzip compression, and logical size eviction. Single-tenant model safe; multi-tenant deployment would require authorization-keyed cache isolation.
5. **Claim: MCP core scenarios pass.**  
   *Audit Finding:* **VERIFIED FOR ADVERTISED CAPABILITIES.** Official `@modelcontextprotocol/conformance` suite passes all core server-initialize, ping, tools-list, and DNS rebinding scenarios (8/8 applicable). Failures occur only on unadvertised capabilities (prompts, resources, sampling).
6. **Claim: Payload reduction preserves answer-critical facts.**  
   *Audit Finding:* **VERIFIED.** Lexical passage slicing and snippet trimming reduce payload size by 10.5x to 18.3x while preserving factual grounding (80% Answer Support on answerable evaluation queries).
7. **Claim: WebLens performs competitively against Tavily.**  
   *Audit Finding:* **VERIFIED AS COMPLEMENTARY / PARETO-OPTIMAL.** WebLens wins on token economy (18.3x snippet token reduction), zero monetary cost (keyless mode), and extraction speed. Tavily wins on raw search speed (1.82s vs 2.87s) and broad commercial index coverage.
8. **Claim: Conflict retrieval previously scored 0/8.**  
   *Audit Finding:* **REPRODUCED & EXPLAINED.** Previous `queries.jsonl` benchmark scored 0/8 because the benchmark runner evaluated `expect_conflict` against `research.get("conflicts")` or `"status" == "conflicting_sources"`, which were not emitted by default. In the expanded evaluation set with query-level grounding, conflict recall achieved 6/8 (75.0%).
9. **Claim: Previous security test suite reported 147/147 attacks blocked.**  
   *Audit Finding:* **REPRODUCED.** The 147 blocked vectors represent the aggregate of 93 SSRF penetration tests, 35 prompt-injection attack probes, and 19 edge-fuzz test cases.
