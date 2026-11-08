# WebLens Product & Engineering Roadmap

## 1. Vision & Strategy

WebLens is an evidence-first web-intelligence infrastructure tool designed specifically for autonomous AI agents, multi-agent frameworks, and external LLM workflows. It delivers sovereign, verifiable, zero-guess factual retrieval over standard Model Context Protocol (MCP) and JSON APIs without requiring expensive commercial API subscriptions.

---

## 2. Release Milestones & Status

### Phase 1: Cryptographic Integrity & Evidence Architecture (Completed - Milestone 1.0)
- **Status:** PASS - VERIFIED
- **Deliverables:**
  - `tools/evidence_run.py`: Canonical JSON execution ledger with SHA-256 output and artifact hashing.
  - `tools/verify_chain.py`: Cryptographic ledger hash chain verification.
  - `evidence/ledger.jsonl`: 45-entry immutable SHA-256 blockchain-style log.
  - Full quarantine of unverified legacy reports into `reports/_withdrawn/`.

### Phase 2: Core Retrieval & Defensive Hardening (Completed - Milestone 1.1)
- **Status:** PASS - VERIFIED
- **Deliverables:**
  - Multi-provider search routing (Bing, DuckDuckGo, Wikipedia, Mojeek, Mwmbl, optional Tavily/Brave).
  - Robust SSRF protection (`DestinationPolicy`) blocking IPv4/IPv6 private, loopback, link-local, and metadata ranges.
  - Passage chunking and lexical relevance scoring (`weblens.extract.passages`).
  - Headless browser proxy architecture with socket-level egress filtering.
  - Compact MCP server schema (732 cl100k tokens across core tools, staying under the 1,000-token limit).

### Phase 3: Nine Specialized Agent Applications (Completed - Milestone 2.0)
- **Status:** PASS - VERIFIED
- **Deliverables:**
  - `weblens.apps.crawl2rag`: Website-to-knowledge-base pipeline with SQLite FTS5/BM25 indexing and exact text citation.
  - `weblens.apps.deep_research`: Recursive multi-hop research planner with claim-level evidence spans and conflict detection.
  - `weblens.apps.company`: Corporate intelligence profiling with entity disambiguation and official domain selection.
  - `weblens.apps.market`: Factual financial research engine with strict numeric verification and disclaimers.
  - `weblens.apps.sheets`: Tabular dataset enrichment with formula injection sanitization.
  - `weblens.apps.chat`: Multi-turn conversational research agent with session context budgeting.
  - `weblens.apps.meeting`: Meeting preparation agent operating strictly on public professional records.
  - `weblens.apps.tutorial` ("WebLens 101"): Interactive, runnable developer learning modules.
  - Verified across 18 synthetic fixtures: all 9 applications passing 100%.

### Phase 4: Production Cloud Deployment & Four-System Benchmark Lab (Completed - Milestone 2.1)
- **Status:** PASS - VERIFIED
- **Deliverables:**
  - Deployed on Google Cloud Run (`https://weblens-16131012091.us-central1.run.app/mcp`) under `--profile full`.
  - Four-System comparative evaluation suite (Local WebLens, Deployed WebLens, Tavily Direct, Google Gemini).
  - Comprehensive local and remote penetration audits: 36/36 security attack vectors blocked.
  - Pre-commit secret scanning and zero credential leak policy verified.

### Phase 5: Quality-First Autonomous Optimization (Completed locally - Milestone 2.2 / V11)
- **Status:** PASS - LOCAL; PRODUCTION GATES OPEN
- **Deliverables:**
  - Institutional domain authority weighting (`.gov`, `.gov.in`, `.gov.uk`, `worldbank.org`, `un.org`, `rtings.com`).
  - Search query normalization stripping over-constraining comparison suffixes.
  - Ten formal architecture, product identity, and quality specifications in `docs/`.
  - Comprehensive quality field registry (F1-F17) with two-run reproducibility requirements.

### Phase 6: Fetch Resilience & Repeat-Query Performance (Current - Milestone 3.1)
- **Status:** LOCAL GATE PASS - PRODUCTION GATE OPEN
- **Deliverables:**
  - Bounded stale-on-error cache fallback for page fetches. Transient timeouts, protocol resets, and retryable 5xx/429 responses can reuse an expired entry inside a configurable grace window; 4xx and blocked/oversized responses are never masked.
  - Stale responses preserve the original `fetched_at`, are marked `stale`, and surface `stale_cache_used` (extraction) or `stale_source:<domain>` (research).
  - A real per-attempt fetch deadline reserves part of the caller budget for the HTTP/1.1 fallback, so one slow HTTP/2 stream cannot consume the whole research timeout.
  - A short-TTL search-result cache avoids repeat provider calls for identical queries; failed and partial searches are not cached.
  - `weblens-lab/evaluations/run_resilience_benchmark.py` measures all three behaviors in-process.

---

## 3. Future Development Horizon (Milestones 2.3 - 3.1)

| Target Phase | Feature / Objective | Architecture Impact | Target Gate |
|---|---|---|---|
| **Milestone 2.3** | Dense + Sparse Hybrid Search | Embeddings via local ONNX runtime alongside BM25 in Crawl2RAG. | Recall@5 >= 95% on technical docs. |
| **Milestone 2.4** | Multi-Lingual Injection Defense | Expanded regex and heuristic rules for Spanish, Chinese, Russian, and Arabic payloads. | Detection Recall >= 85% with 0.00% FPR. |
| **Milestone 2.5** | Distributed Multi-Tenant MCP | Ingress API key authentication, per-tenant rate limits, and Redis cache layer. | 1,000 QPM sustained under 2,000 ms p95. |
| **Milestone 3.0** | Autonomous Evidence Synthesis | Agentic multi-hop hypothesis testing with automated contradiction resolution. | Verified claim support >= 95% on complex research. |
| **Milestone 3.1** | Fetch Resilience & Repeat-Query Performance | Bounded stale-on-error cache fallback, per-attempt fetch deadlines across HTTP/2 + HTTP/1.1, and a short-TTL search-result cache. | Transient-failure recovery > 0 without masking 4xx; repeat-query provider calls reduced; no stale provenance rewrite. |

### Local implementation status (2026-11-08)

Milestones 2.3, 2.4, and 2.5 are implemented and locally gated. None is
production-accepted until the redeployed revision passes the official gates.

For 2.5 specifically, the local ingress benchmark (in-process ASGI, synthetic
handler, 1,000 paced requests over 59.949 s) returned 1,000/1,000 HTTP 200s at
1,000.9 QPM with p95 1.77 ms; a 10,000-request, 10-tenant burst returned
10,000/10,000 HTTP 200s at 1,248 rps with p95 1.40 ms. That covers API-key auth,
tenant binding, failure limiting, tenant rate limiting, and security headers
only. It excludes MCP tool dispatch, provider/network latency, and the real HTTP
transport, so the production gate remains open.

Milestone 3.0 is implemented as a deterministic, LLM-free synthesis layer
(`weblens.research.synthesis`). It generates polar, comparison, numeric, and
definition hypotheses; classifies claim stance with lexical rules; resolves
contradictions by source tier, recency, and independent-domain support; and
runs bounded follow-up hops (1-3) for insufficient or conflicting evidence.
`weblens synthesize` and the `evidence_synthesis` MCP tool in the `research` /
`full` profiles expose it.

The local curated synthesis gate (11 cases, 21 hypotheses) matches 21/21
verdicts, 11/11 expected statuses, and 20/20 claim citations with URL, fetch
timestamp, and character span. A live spot check also exposed and fixed a
numeric false positive: a WhatsApp paragraph sharing only "maximum" and "size"
was accepted as SQLite evidence. Numeric claims now need a topic anchor when the
question has one (in the claim, heading, or source URL), and the selected numeric
group prefers the subject that matches the query. The corrected SQLite query
returns `ok`, `supported`, and "281 terabytes" with no gaps; it still reports one
`fetch_failed:FetchError`. The asyncio query remains `partial` with
`no_source_for:expires`; the latest rerun completed in 8.24 s (the earlier run
took 13.5 s) and did not repeat the fetch-failure warning.

Re-test measurements (2026-11-08):

- Hybrid retrieval: Recall@5 0.9048 BM25-only vs 1.0 hybrid on 21 queries over
  20 Python documentation pages (112 passages, all-MiniLM-L6-v2); gate pass.
- Multilingual injection: recall 1.0 and false-positive rate 0.0 on 50 payloads
  and 50 benign items across English, Spanish, Chinese, Russian, and Arabic.
- Dense matrix cache: 83.65x to 143.44x faster at 1,000-50,000 rows; at 50,000
  rows 3,730.649 ms rebuild vs 31.08 ms cached (120.03x).
- Milestone 3.1 resilience (100 samples per metric): stale recovery 100/100,
  opt-out failures visible 100/100, 404 masking 0/100, deadline fallback 100/100,
  and 1 provider call for 100 repeated searches instead of 100.
- Canonical suite: 402 passed.

These are local synthetic/curated measurements, not production acceptance. The
production gates, live Redis behavior, and the larger scale/adversarial matrices
remain open. The SQLite and asyncio checks are single-query live smokes, not a
benchmark.

