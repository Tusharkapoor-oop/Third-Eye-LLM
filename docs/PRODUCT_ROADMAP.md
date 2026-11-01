# WebLens Product Roadmap

## 1. Vision & Strategy
Transform WebLens from a local search and extraction MCP tool into a comprehensive, verified, privacy-preserving web intelligence platform. WebLens provides local-first, zero-fabrication research engines capable of competing directly with commercial cloud research agents while maintaining full user data ownership and strict security boundaries.

---

## 2. Release Phases & Milestones

### Phase 1: Cryptographic Integrity & Evidence Architecture (Completed - Milestone 1.0)
- **Status:** PASS - VERIFIED
- **Deliverables:**
  - `tools/evidence_run.py`: Canonical JSON execution ledger with SHA-256 output and artifact hashing.
  - `tools/verify_evidence.py`: Cryptographic ledger hash chain verification.
  - `tools/lint_report.py`: Automated report linter enforcing 100% metric traceability, n/confidence intervals, and forbidding marketing claims.
  - `evidence/prereg.md`: Pre-registered hypothesis and dataset digests.
  - Full quarantine of defective legacy reports into `reports/_withdrawn/`.

### Phase 2: Core Retrieval & Defensive Hardening (Completed - Milestone 1.1)
- **Status:** PASS - VERIFIED
- **Deliverables:**
  - Multi-provider search routing (DuckDuckGo, Wikipedia, Brave, Tavily).
  - Robust SSRF protection (`DestinationPolicy`) blocking IPv4/IPv6 private, loopback, and metadata ranges.
  - Passage chunking and lexical relevance scoring (`weblens.extract.passages`).
  - Playwright browser proxy architecture with egress filtering.
  - MCP server schema optimization (732 cl100k tokens across 4 tools, staying under the 1,000 token limit).

### Phase 3: Mandated Applications Program (Current - Milestone 2.0)
- **Status:** IN PROGRESS
- **Deliverables:**
  - **Milestone 2.0a: Knowledge & Synthesis Infrastructure**
    - `weblens.apps.crawl2rag`: Website-to-knowledge-base pipeline with SQLite FTS5/BM25 indexing and exact text citation.
    - `weblens.apps.deep_research`: Recursive multi-hop research planner with claim-level evidence spans and conflict detection.
  - **Milestone 2.0b: Structured Intelligence Applications**
    - `weblens.apps.company`: Corporate intelligence profiling with entity disambiguation.
    - `weblens.apps.market`: Factual financial research engine with strict numeric verification and disclaimers.
  - **Milestone 2.0c: Productivity & Interaction**
    - `weblens.apps.sheets`: Tabular dataset enrichment with formula injection sanitization.
    - `weblens.apps.chat`: Multi-turn conversational research agent with session context budgeting.
  - **Milestone 2.0d: Privacy-Preserving Briefings & Onboarding**
    - `weblens.apps.meeting`: Meeting preparation agent operating strictly on public professional records.
    - `weblens.apps.tutorial` ("WebLens 101"): Interactive, runnable developer learning modules.

### Phase 4: Autonomous Improvement Loop (Milestone 2.1)
- **Status:** PLANNED
- **Deliverables:**
  - Systematic cycle-by-cycle optimization of retrieval recall, tail-fact extraction, and latency.
  - Multi-lingual prompt injection detection expansions.
  - Real-time Tavily paired subset benchmark comparisons under strict credit caps.

---

## 3. Architecture Constraints & Budgets
- **MCP Schema Budget:** Core profile $\le 1,000$ `cl100k_base` tokens. Tool profiles (`core`, `research`, `full`) ensure small-model tool selection is not degraded.
- **Credit Spending:** Tavily API spend capped at 60% of remaining account quota (max 600 credits).
- **Execution Environment:** Windows 11 Home (local execution), isolated test containers for red-team fuzzing.
- **Quality Gates:** Zero fabricated citations; all factual claims backed by exact text spans and retrieval timestamps.
