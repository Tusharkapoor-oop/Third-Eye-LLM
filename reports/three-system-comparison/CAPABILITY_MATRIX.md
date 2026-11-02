# Capability & Workflow Comparison Matrix (V9)

This matrix compares native provider features and composed applications across the three systems.

| Capability / Workflow | System 1 (Local WebLens) | System 2 (Deployed WebLens) | System 3 (Tavily Direct) |
|---|---|---|---|
| **Direct Web Search** | Native (DDG, Mwmbl, Wikipedia) | Native (Cloud Run MCP) | Native (Tavily API) |
| **Passage Span Extraction** | Native (Exact character offsets) | Native (`extract_url` MCP) | Native (`raw_content` extract) |
| **Polite Bounded Crawling** | Native (Robots.txt & SSRF safe) | Native (`crawl_site` MCP) | External / Limited |
| **Deep Research Agent** | Native (Multi-hop recursive) | Native (`deep_research` MCP) | Requires External LLM Orchestration |
| **Company Researcher** | Native (Domain discovery & SEC) | Native (`company_research` MCP) | Requires External Prompt Engineering |
| **Market Researcher & Portfolio**| Native (Multi-stock portfolio) | Native (`market_portfolio` MCP) | Financial raw search only |
| **Sheets Batch Enrichment**| Native (Formula injection defense)| Native (`sheets_enrich` MCP) | Raw API without CSV/formula defense |
| **Meeting Preparation** | Native (Calendar event ingestion) | Native (`meeting_prep` MCP) | Raw person search only |
| **Crawl2RAG Knowledge Base**| Native (Local SQLite FTS5/BM25) | Native (`crawl2rag_query` MCP) | External vector database required |
| **Persistent Research Chat** | Native (SQLite session state) | Native (`research_chat` MCP) | Stateless REST endpoint |
| **Interactive Tutorial 101** | Native (Runnable guided guide) | Native (`tutorial_101` MCP) | Documentation site only |
| **SSRF Private IP Defense** | Enforced at TCP connect | Enforced at Cloud Run container | N/A (Cloud-hosted service) |
| **Formula Injection Defense** | Enforced (`'`, `+`, `-`, `@`, `\t`, `\r`)| Enforced in MCP tool | Not provided natively |
| **Token Budget Guarantee** | Strict truncation (<2000 tok) | Strict truncation (<2000 tok) | Variable payload sizes |
| **Deployment Platform** | Local Windows machine | Google Cloud Run (us-central1) | Tavily Cloud Infrastructure |
| **Pricing / Cost** | $0.00 (Keyless) | $0.00 (Keyless) | $0.0050 / search request |

