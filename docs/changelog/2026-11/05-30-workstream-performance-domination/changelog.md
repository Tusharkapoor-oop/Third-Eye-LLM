# Changelog: 30-Workstream Performance Domination Evaluation

**Date:** 2026-11-05  
**Commit Base:** `044cf4a` (origin/main)  
**Scope:** Comprehensive 30-workstream quality evaluation, security audit, penetration testing, Tavily benchmarking, and remediation

---

## Summary

Executed a 30-workstream performance domination evaluation covering architecture, search, extraction, crawling, deep research, citations, hallucination resistance, model integration, Tavily comparison, MCP protocol, security, penetration testing, performance, test infrastructure, and evidence reproducibility.

**Final Verdict:** PASS WITH LIMITATIONS

---

## Code Fixes Applied (7)

1. **FIX-001:** Synchronized `src/weblens/extract/passages.py` with canonical `weblens/src/weblens/extract/passages.py` -- added missing `spread_chunks()` function.
2. **FIX-002:** Improved paragraph boundary chunking in `src/engine/extract/chunker.py` to retain tail paragraphs on long documents.
3. **FIX-003:** Added `exec` signal forwarding to `Dockerfile` CMD for clean container shutdown.
4. **FIX-004:** Added `defusedxml>=0.7.1` to `pyproject.toml` dependencies.
5. **FIX-005:** Added missing `import os` to `src/engine/extract/extractor.py`.
6. **FIX-006:** Switched `mapper.py` and `bing_provider.py` to `defusedxml` for XML parsing (remediated Bandit B314).
7. **FIX-007:** Added `addopts = "--timeout=60"` to `pyproject.toml` to prevent indefinite socket hangs.

## Reports Generated (31)

- 30 workstream reports: `reports/domination/agent01_*.md` through `agent29_*.md`
- 1 master synthesis: `reports/domination/master_domination_report.md`
- 1 machine-readable summary: `reports/domination/domination_summary.json`

## Key Findings

- 350 tests collected across 39 files; core suites 100% pass
- 100/100 SSRF penetration vectors blocked
- 38/38 prompt injection vectors quarantined
- 10/10 hallucination false-premise traps correctly abstained
- Arena quality gate missed (81.6 vs 90.0 target) due to recency query weakness
- WebLens outperforms Tavily on factual density (8.23x), token efficiency (85%), deep research quality (+22 pts)
- Tavily outperforms WebLens on raw P@5 snippet retrieval and multi-hop latency

## Deployment Status

- **Cloud Run Service:** `weblens`
- **Revision:** `weblens-00008-t5p` (serving 100% traffic)
- **Endpoint:** `https://weblens-16131012091.us-central1.run.app/`
- **Health Check:** HTTP 200 OK (`{"status":"ok","service":"weblens","version":"0.1.0","mcp_endpoint":"/mcp"}`)
- **Container Image:** `gcr.io/sewasetu-prod-2026/weblens:b3a0b62` (built via Cloud Build `8a8dc86f-893a-41cf-a36d-e4e279904a15`)

## Remaining Gaps

- Arena recency query quality (P1)
- Cloud Run ingress authentication (P1)
- HSTS headers (P2)
- Non-root container user (P3)

