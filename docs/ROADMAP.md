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

### Phase 5: Quality-First Autonomous Optimization (Current - Milestone 2.2 / V11)
- **Status:** IN PROGRESS - ACTIVE
- **Deliverables:**
  - Institutional domain authority weighting (`.gov`, `.gov.in`, `.gov.uk`, `worldbank.org`, `un.org`, `rtings.com`).
  - Search query normalization stripping over-constraining comparison suffixes.
  - Ten formal architecture, product identity, and quality specifications in `docs/`.
  - Comprehensive quality field registry (F1-F17) with two-run reproducibility requirements.

---

## 3. Future Development Horizon (Milestones 2.3 - 3.0)

| Target Phase | Feature / Objective | Architecture Impact | Target Gate |
|---|---|---|---|
| **Milestone 2.3** | Dense + Sparse Hybrid Search | Embeddings via local ONNX runtime alongside BM25 in Crawl2RAG. | Recall@5 >= 95% on technical docs. |
| **Milestone 2.4** | Multi-Lingual Injection Defense | Expanded regex and heuristic rules for Spanish, Chinese, Russian, and Arabic payloads. | Detection Recall >= 85% with 0.00% FPR. |
| **Milestone 2.5** | Distributed Multi-Tenant MCP | Ingress API key authentication, per-tenant rate limits, and Redis cache layer. | 1,000 QPM sustained under 2,000 ms p95. |
| **Milestone 3.0** | Autonomous Evidence Synthesis | Agentic multi-hop hypothesis testing with automated contradiction resolution. | Verified claim support >= 95% on complex research. |

