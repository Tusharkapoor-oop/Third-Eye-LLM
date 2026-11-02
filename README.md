# WebLens: Autonomous Web Intelligence Platform & Model Context Protocol (MCP)

WebLens is a production-grade, local-first and cloud-deployable web intelligence platform designed for autonomous AI agents. Built with strict low-token budgets, verifiable character-span citations, and zero-guess factual grounding, WebLens replaces expensive, heavy third-party search subscriptions with a high-performance retrieval engine and application suite.

WebLens is deployed live on Google Cloud Run and runs locally across Windows, Linux, and macOS.

---

## Live Cloud Deployment

- **MCP Endpoint**: `https://weblens-16131012091.us-central1.run.app/mcp`
- **Health Check**: `https://weblens-16131012091.us-central1.run.app/`
- **Current Revision**: `weblens-00003-l9q`
- **Transport**: JSON-RPC over Streamable HTTP MCP (MCP Specification 2024-11-05 / 2026 standards)
- **Active Tools**: All 13 tools active under `--profile full`

---

## Key Differentiators & Empirical Advantages

1. **2.7x to 3.3x Faster than Commercial APIs**:
   - Local WebLens p50 Latency: **939.5 ms** (3.26x faster than Tavily Direct).
   - Deployed Cloud Run WebLens p50 Latency: **1,115.6 ms** (2.74x faster than Tavily Direct at 3,062.2 ms).
2. **70.7% Fewer Tokens per Request**:
   - Averages **428.2 tokens** on Cloud Run vs **1,459.5 tokens** for Tavily Direct, cutting downstream LLM token consumption costs.
3. **100% Free Search Cost ($0.00)**:
   - Keyless federated search backends (DuckDuckGo, Wikipedia REST, Mwmbl) eliminate recurring per-query API fees.
4. **Zero Fake Accuracy & Verifiable Citations**:
   - No fabricated relevance floats. Every passage contains exact character spans (`span_start`, `span_end`) traceable to the source document.
   - Explicit uncertainty states (`no_reliable_result`, `conflicting_sources`) prevent hallucinations.
5. **Hardened Security & Zero-Trust Architecture**:
   - 100% pass rate on local penetration testing (26/26 tests passed) and remote Cloud Run security audit (10/10 tests passed).
   - Enforced SSRF socket-level IP validation, path traversal boundaries, spreadsheet formula injection defense, and indirect prompt injection quarantine.

---

## Three-System Benchmark Summary

Evaluated across identical queries from the versioned V9 benchmark dataset with interleaved execution:

| Metric | System 1: Local WebLens | System 2: Deployed WebLens | System 3: Tavily Direct API | Advantage |
| :--- | :--- | :--- | :--- | :--- |
| **p50 Latency** | **939.5 ms** | 1,115.6 ms | 3,062.2 ms | **WebLens (2.7x - 3.3x faster)** |
| **Mean Latency** | **1,119.7 ms** | 1,146.3 ms | 3,246.6 ms | **WebLens (2.9x faster)** |
| **p95 Latency** | 3,464.5 ms | **1,380.2 ms** | 4,883.3 ms | **Deployed WebLens (Tighter tail)** |
| **Mean Tokens / Query** | **265.1** | 428.2 | 1,459.5 | **WebLens (-70.7% tokens)** |
| **Search Provider Cost** | **$0.00** | **$0.00** | $0.0050 / query | **WebLens (Zero API cost)** |
| **Precision@5** | 0.240 | 0.413 | **0.653** | **Tavily (+58.1% on niche queries)** |
| **False Confidence Rate** | **0.0% (0/15)** | **0.0% (0/15)** | **0.0% (0/15)** | **Tied (Zero hallucinations)** |
| **Success / Uptime Rate** | 100.0% | **100.0%** | **100.0%** | **Tied** |

---

## All Nine Product Applications

WebLens includes nine built-in product applications, each verified live with 100% pass rates:

1. **Deep Research Agent**: Autonomous multi-hop evidence discovery, query decomposition, and conflict detection with strict 2,000-token boundaries.
2. **Company Researcher**: Corporate intelligence profiles, domain discovery, leadership, products, and SEC/regulatory disclosures.
3. **Conversational Answer Engine (Chat)**: Interactive conversational search with cited passage spans and multi-turn context retention.
4. **Crawl2RAG Knowledge Base**: Bounded polite crawler indexing sites into local SQLite FTS5 with BM25 passage ranking and span citations.
5. **Market Researcher & Portfolio Analyzer**: Financial asset and multi-stock portfolio intelligence sourcing verified metrics from regulatory filings with a strict zero-guess policy.
6. **Sheets Batch Dataset Enricher**: Row-by-row dataset enrichment with defense against spreadsheet formula injection (`=`, `+`, `-`, `@`, `\t`, `\r` neutralized).
7. **Meeting Preparation Agent**: Pre-meeting dossiers from calendar events and public professional records with automated privacy boundary enforcement.
8. **WebLens 101 Tutorial**: Executable developer guide and interactive API walkthrough.
9. **Persistent Research Chat**: Stateful multi-turn research dialogue backed by SQLite session persistence (`sessions` and `messages` tables).

---

## Registered MCP Tools (13 Total)

When running with `--profile full` (default in container deployment), WebLens exposes 13 tools:

| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `web_search` | `query`, `max_results` (1-10), `freshness`, `domains` | Fast web search returning titles, normalized URLs, and snippets. |
| `extract_url` | `url`, `query`, `max_tokens`, `full` | Extracts relevant passages with exact character spans and timestamps. |
| `crawl_site` | `url`, `mode` (`map` \| `crawl`), `max_pages`, `max_depth` | Bounded polite crawling respecting robots.txt and SSRF restrictions. |
| `deep_research` | `query`, `max_tokens` | Multi-hop evidence discovery and conflict analysis. |
| `company_research` | `company` | Structured company profile (leadership, products, competitors, risks). |
| `market_research` | `asset`, `question` | Disclosures and verified metrics from official regulatory filings. |
| `market_portfolio` | `assets` (list of tickers) | Parallel portfolio analysis with aggregated financial disclosures. |
| `crawl2rag_index` | `url`, `max_pages` | Crawls and indexes a documentation site into local SQLite FTS5. |
| `crawl2rag_query` | `question`, `top_k` | Queries local BM25 knowledge base returning passages with cited spans. |
| `meeting_prep` | `meeting_title`, `attendees`, `company_or_org` | Pre-meeting attendee briefing dossier from public professional records. |
| `sheets_enrich` | `rows`, `column_prompts` | Batch-enriches tabular datasets with formula injection protection. |
| `research_chat` | `message`, `session_id` | Multi-turn stateful research dialogue with SQLite session persistence. |
| `tutorial_101` | `step` | Interactive guided walkthrough of core capabilities. |

---

## MCP Client Configuration

### Connecting to Deployed Cloud Run Service

To use the live deployed WebLens endpoint in Claude Desktop, Cline, Roo Code, or Continue:

```json
{
  "mcpServers": {
    "weblens-cloud": {
      "url": "https://weblens-16131012091.us-central1.run.app/mcp"
    }
  }
}
```

### Connecting to Local WebLens MCP Server

In your client configuration (`cline_mcp_settings.json` or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "weblens-local": {
      "command": "python",
      "args": ["-m", "weblens.cli", "serve", "--profile", "full"],
      "cwd": "C:\\path\\to\\weblens",
      "env": {
        "WEBLENS_MCP_PROFILE": "full"
      }
    }
  }
}
```

---

## Installation & Local Execution

### Prerequisites
- Python 3.11+ (Python 3.12 or 3.13 recommended)
- Windows 11, Linux, or macOS

### Setup
```bash
# Clone repository
git clone https://github.com/Tusharkapoor-oop/Third-Eye-LLM.git
cd Third-Eye-LLM

# Install package in editable mode
pip install -e ./weblens -e .
```

### Running the MCP Server
```bash
# Run stdio MCP server (full profile)
python -m weblens.cli serve --profile full

# Run HTTP MCP server locally
python -m weblens.cli serve --http --host 127.0.0.1 --port 8765 --profile full
```

### Running Applications from CLI
```bash
# Company Research
python -m weblens.cli app company "Anthropic"

# Market Analysis
python -m weblens.cli app market "Apple Inc."

# Portfolio Analysis
python -m weblens.cli app market --portfolio "AAPL" --portfolio "MSFT"

# Meeting Preparation
python -m weblens.cli app meeting "Architecture Review" -a "Guido van Rossum" -c "Python Software Foundation"

# WebLens 101 Tutorial
python -m weblens.cli app tutorial --step all
```

---

## Security & Penetration Testing

WebLens is engineered with defensive zero-trust principles:

- **SSRF Prevention**: Connect-time socket IP resolution blocks loopback (`127.0.0.1`, `::1`), RFC 1918 subnets (`10.x`, `172.16.x`, `192.168.x`), and cloud metadata (`169.254.169.254`, `metadata.google.internal`).
- **Spreadsheet Formula Injection Defense**: Defangs cells starting with `=`, `+`, `-`, `@`, `\t`, `\r`, `\n` by prepending `'`.
- **Indirect Prompt Injection Scanner**: Identifies and quarantines instruction override attempts inside untrusted web pages.
- **Audit Verification**:
  - Local Security Audit: 26/26 passed (100%).
  - Deployed Cloud Run Security Audit: 10/10 passed (100%).

To execute the automated security audit suite:
```bash
python weblens-lab/security_lab/run_three_system_security_audit.py
```

To run all nine applications end-to-end:
```bash
python tools/run_all_nine_apps_live.py
```

---

## Security Notice: Zero Secret Leakage

- WebLens operates out of the box with zero required API keys.
- **Never commit `.env` or any real API credentials to Git.**
- The repository `.gitignore` strictly ignores `.env`, `.env.*`, certificates, and temporary credential files.

---

## Documentation Links

- [Three-System Architecture Specification](docs/THREE_SYSTEM_ARCHITECTURE.md)
- [Three-System Executive Benchmark Summary](reports/three-system-comparison/EXECUTIVE_SUMMARY.md)
- [Capability & Feature Matrix](reports/three-system-comparison/CAPABILITY_MATRIX.md)
- [Search Quality & Retrieval Precision](reports/three-system-comparison/SEARCH_QUALITY.md)
- [Latency & Performance Results](reports/three-system-comparison/LATENCY.md)
- [Cost & Token Analysis](reports/three-system-comparison/COST_ANALYSIS.md)
- [Local Security Plan & Verifications](docs/LOCAL_MCP_SECURITY_PLAN.md)
- [Deployed Cloud Run Security Plan](docs/DEPLOYED_MCP_SECURITY_PLAN.md)
- [Dataset Registry & Checksums](evidence/DATASET-REGISTRY.md)
- [Release Gates Report](evidence/RELEASE-GATES.md)
