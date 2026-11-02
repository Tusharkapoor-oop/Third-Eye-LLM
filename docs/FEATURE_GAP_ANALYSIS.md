# WebLens Feature Gap Analysis vs. External Systems

## 1. Executive Summary

This evaluation contrasts WebLens (Local MCP and Deployed Cloud Run) against leading external commercial web-intelligence solutions: **Tavily Direct API**, **Google Gemini Search Grounding**, and **Perplexity AI**.

WebLens is engineered as self-hosted, sovereign infrastructure for autonomous agents. While commercial cloud APIs offer proprietary crawl indexes and managed LLM summaries, WebLens delivers zero vendor lock-in, deterministic verbatim evidence provenance, local caching, and native client-side egress security.

---

## 2. Four-System Feature Comparison Matrix

| Capability | WebLens (Local & Deployed) | Tavily Direct API | Google Gemini Grounding | Perplexity AI API |
|---|---|---|---|---|
| **Primary Interface** | Open Model Context Protocol (MCP) & Python SDK | REST JSON API & Python SDK | Gemini Interactions / GenerateContent API | REST JSON API |
| **API Key Requirement** | Optional (100% operational on keyless providers) | Mandatory (Paid credits) | Mandatory (Google Cloud / AI Studio key) | Mandatory (Perplexity API key) |
| **Verbatim Span Anchors** | Full support (Character start/end offsets) | Partial (Text snippets) | Grounding chunks with URI metadata | Citations with line references |
| **Document Hash Provenance** | Cryptographic SHA-256 for all fetched content | None | None | None |
| **SSRF & DNS Pinning** | Native `DestinationPolicy` with RFC range blocking | Cloud-managed opaque sandbox | Google-managed cloud egress | Cloud-managed opaque sandbox |
| **Prompt Injection Defense** | Native scanner & quarantine payload | Server-side proprietary filter | Safety ratings and system instructions | Server-side proprietary filter |
| **Crawler Trap Resistance** | Native heuristics (calendar, recursion, loop defense) | Server-side crawling limits | Not exposed as a site crawler | Not exposed as a site crawler |
| **Local Knowledge Base (Crawl2RAG)** | Built-in SQLite FTS5 / BM25 indexer | Requires external vector database | Requires Vertex AI Search / File API | None |
| **Batch Tabular Data Enrichment** | Built-in async worker pool with formula sanitization | Supported via Tavily Sheets integration | Via custom Python scripting | Via custom scripting |
| **Self-Hosted Deployment** | Local process, Docker, Google Cloud Run, Kubernetes | Proprietary SaaS only | Proprietary Google Cloud only | Proprietary SaaS only |
| **Cost per 100 Queries** | $0.00 (Self-hosted keyless) | $0.50 - $1.00 (Paid credits) | $0.0035/search grounding call + tokens | $0.20 - $1.00 + model tokens |

---

## 3. Detailed Gap Analysis & Technical Trade-offs

### 3.1 Web Discovery Coverage
- **Tavily:** Leverages a proprietary web index optimized for LLMs with low-latency search results and pre-extracted answers.
- **Gemini Search Grounding:** Directly queries Google Search's global web index, offering freshness and deep international coverage.
- **WebLens Status:** Dispatches to multiple keyless search backends (Bing, DuckDuckGo, Wikipedia, Mojeek). While slightly lower in raw hit volume on obscure long-tail queries than Google, WebLens achieves 87% answer support on Deployed Cloud Run without incurring commercial API fees.

### 3.2 Citation Fidelity & Auditability
- **Commercial Competitors:** Typically return an answer string alongside 3 to 5 candidate URLs without specifying exactly which byte span in the original HTML document supported the claim.
- **WebLens Advantage:** WebLens returns character-span anchors (`char_start`, `char_end`) alongside raw document SHA-256 hashes, allowing an autonomous agent to cryptographically prove that the cited text existed in the source document at the timestamp of retrieval.

### 3.3 Security, SSRF, and Host Isolation
- **Commercial Competitors:** Run on proprietary infrastructure where egress IP controls, internal network exposure, and payload inspection are black-box operations.
- **WebLens Advantage:** Enforces zero-trust architecture. Downstream agents can run WebLens in air-gapped or VPC environments with strict egress whitelists, guaranteed DNS pinning against rebinding attacks, and automated prompt-injection quarantine.

---

## 4. Remediation & Convergence Roadmap

1. **Long-Tail Coverage Expansion:** Integrate additional public search endpoints to eliminate the remaining coverage gap on obscure dynamic facts.
2. **Hybrid Dense/Sparse RAG:** Enhance `Crawl2RAG` with optional lightweight local ONNX embeddings alongside BM25 for domain-specific technical documentation retrieval.
3. **Multi-Hop Search Decomposition:** Further tune the research engine to automatically branch into contrasting sub-queries for nuanced comparative analysis.

