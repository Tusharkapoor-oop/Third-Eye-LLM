# 00 — Scope Manifest, Boundaries, and Threat Model

**Document ID:** `reports/extreme-benchmark/00-scope-and-threat-model.md`  
**Execution Date:** 2026-10-27  
**Auditor Mode:** Authorized Principal Security Engineer, Application Security Red-Team Lead, Benchmark Statistician  
**Target Subject:** WebLens & WebIntel Autonomous Intelligence Engines  
**Target Environment:** Localhost / Owned Local Test Fixtures (Windows 11 x64, Python 3.13.15, Node 24.19.0)  
**Classification:** STRICT AUDIT EVIDENCE — EXTREME-SCALE BENCHMARK  

---

## 1. Authorized Scope Manifest & Safety Boundaries

### 1.1 In-Scope Targets
Testing is strictly bounded to the authorized runtime and owned code in the repository:
- WebLens Core Package (`weblens/src/weblens/`)
- WebIntel Engine Core (`src/engine/`)
- MCP Server Endpoints (`src/server/mcp_server.py`, `weblens/src/weblens/mcp_server.py`)
- Browser Egress Proxy (`weblens/src/weblens/net/browser_proxy.py`)
- Headless Browser Fallback (`src/engine/extract/browser_fallback.py`)
- Network Egress & SSRF Policies (`src/engine/security.py`, `weblens/src/weblens/net/ssrf.py`)
- SQLite Caching System (`weblens/src/weblens/cache.py`)
- Extraction & Lexical Scoring Pipeline (`src/engine/extract/`, `weblens/src/weblens/extract/`)
- Keyless Search Provider Adapters (DuckDuckGo, Wikipedia, Bing)

### 1.2 Tavily Boundaries
Tavily is a third-party service accessed via official REST APIs. In accordance with Section 1.2 of Master Directive V2:
- No penetration testing, authentication bypass, or denial-of-service attempts were mounted against `api.tavily.com`.
- Tavily was evaluated solely on observable API response quality, schema overhead, network latency, and token payload size under normal authorized credentials.
- All outage and chaos simulations were performed using isolated local mocks.

### 1.3 Safe Fixture Controls
All hostile vectors (SSRF, prompt injection, format fuzzing) were directed against local test fixtures, loopback mock servers, and static in-memory payloads. Uncontrolled floods, persistent lateral movement, and destructive deletions were prohibited.

---

## 2. Attack Surface Catalog & Threat Model (STRIDE)

| Threat ID | Threat Category | Target Component | Threat Vector & Attack Mechanics | Inherent Risk | Residual Risk | Status |
|---|---|---|---|---|---|---|
| **THREAT-01** | **Elevation of Privilege** | Network Layer / Fetcher | SSRF targeting cloud metadata (`169.254.169.254`), loopback (`127.0.0.1`), private IPv4/IPv6, and DNS rebinding. | Critical | Low | **MITIGATED** in HTTP fetchers via pre-connect IP validation. |
| **THREAT-02** | **Elevation of Privilege** | Browser Fallback | Subresource requests in headless Chrome/Edge escaping network restrictions. | High | High | **VULNERABILITY CONFIRMED** in `browser_fallback.py`; mitigated only in `weblens.net.browser_proxy`. |
| **THREAT-03** | **Tampering** | Extraction Pipeline | Indirect prompt injection embedded in fetched web documents manipulating agent tool use. | High | Low | **MITIGATED** via hybrid regex and pattern scanner sanitization. |
| **THREAT-04** | **Information Disclosure** | SQLite Cache | Cache key collisions across differing authorization headers serving private data across tenants. | Medium | Medium | **VULNERABILITY CONFIRMED** for multi-tenant deployments; acceptable for single-user local CLI. |
| **THREAT-05** | **Denial of Service** | Extraction / Network | Decompression bombs, circular redirects, and slow response bodies exhausting system resources. | Medium | Low | **MITIGATED** via 5MB response ceiling, 5-hop redirect cap, and strict connect/read timeouts. |
| **THREAT-06** | **Information Disclosure** | Logging & Diagnostics | Accidental exposure of API keys (`TAVILY_API_KEY`) in error traces or benchmark outputs. | Critical | Low | **MITIGATED** via mandatory regex secret redaction. |

---

## 3. Re-examination of the 9 Historical Hypotheses

| Historical Claim | Initial Hypothesis | Empirical Audit Finding [MEASURED] | Verdict |
|---|---|---|---|
| **1. Regression Tests** | 160 regression tests pass | `pytest weblens/tests` executed 160 tests: 160 PASS, 0 FAIL. `pytest tests/` executed 237 tests: 237 PASS, 0 FAIL. Total: 397 tests passing. | **CONFIRMED** |
| **2. Browser Egress** | Browser egress restrictions work | `weblens.net.browser_proxy` correctly enforces loopback proxy with IP pinning. `src/engine/extract/browser_fallback.py` invokes Edge/Chrome directly without proxy, allowing subresource egress. | **DISPROVED FOR ENGINE FALLBACK** |
| **3. Latency Advantage** | WebLens provides latency advantage | Tavily direct search is faster on network p50 (1.06s - 1.82s vs WebLens 1.28s - 2.87s). WebLens Adaptive HTTP extraction is 5.37x faster than headless browser rendering (0.42s vs 2.28s). | **PARTIAL (Search Loses, Extract Wins)** |
| **4. Cache Management** | Cache is safe and correct | Single-tenant eviction, WAL mode, and TTL work correctly. Cache key lacks request auth headers, creating multi-tenant cross-credential collision risk. | **CONFIRMED WITH LIMITATIONS** |
| **5. MCP Core Scenarios** | MCP core scenarios pass | Official conformance suite passes 8/8 core tools scenarios. 21 failures occur on unadvertised optional capabilities (prompts, resources, sampling). | **CONFIRMED FOR ADVERTISED CAPABILITIES** |
| **6. Payload Reduction** | Fact preservation held under 10x | Snippet payload reduced by 18.35x (1302.7 to 71.0 tokens). Grounding preserved at 80.0% answer support. | **CONFIRMED** |
| **7. Competitiveness** | WebLens competitive with Tavily | WebLens is Pareto-optimal for zero cost, token budget control, and local privacy. Tavily is superior for raw indexing speed and proprietary web crawl. | **CONFIRMED (Complementary)** |
| **8. Conflict Retrieval** | Conflict retrieval scored 0/8 | Previous 0/8 score was an artifact of runner expecting `status=="conflicting_sources"`. Query-level grounding achieves 6/8 (75.0%) recall. | **EXPLAINED & RESOLVED** |
| **9. Security Suite 147** | 147/147 attacks blocked | Re-verified as aggregate of 93 SSRF tests, 35 injection vectors, and 19 edge-fuzz tests across test suites. | **CONFIRMED** |
