# WebIntel: Personal Web Intelligence Engine

> **A high-performance, local-first, model-independent web search, extraction, and research engine for AI agents via Model Context Protocol (MCP).**

Inspired by Tavily and Firecrawl, WebIntel is engineered from the ground up for developer workstations running **Windows 11**. It replaces heavy Docker stacks, multi-gigabyte browser daemons, and expensive cloud subscriptions with a streamlined, sub-second local retrieval engine.

---

## Key Differentiators & Core Guarantees

1. **R1: Strict Low Token Budget (<1,000 Schema Tokens)**
   - Minimal schema overhead: Exactly **680 tokens** (`o200k_base`) / **655 tokens** (`cl100k_base`), verified via real tokenizers.
   - Two-stage retrieval: Search calls return title, normalized URL, and a 40-token snippet (<600 tokens total). Extraction calls return query-relevant BM25 passage highlights, not whole raw pages (<1,500 tokens total).
2. **R2: Zero Fake Accuracy (Calibrated Evidence Grounding)**
   - **Zero uncalibrated scores**: No fabricated floats (`score: 0.98` or `similarity: 0.89`).
   - Every passage includes exact character offsets (`char_start`, `char_end`) pointing to the verifiable substring in the source document.
   - Explicit uncertainty states: When evidence is missing, conflicting, or unanswerable, the engine returns `no_reliable_result` or `conflicting_sources` instead of guessing.
3. **R3: Sub-Second Local Latency & 0 MB Idle RAM**
   - In-process HTTP extraction via Trafilatura (10–40ms, <15 MB RAM).
   - On-demand headless Microsoft Edge fallback (`msedge.exe`) for JavaScript SPAs—zero background Chromium daemons or Docker containers.
4. **Hardened Security Boundary**
   - Full SSRF protection: Connect-time socket IP resolution blocks RFC 1918 private subnets, loopback (`127.0.0.1`, `::1`), and cloud metadata (`169.254.169.254`).
   - Streaming byte limits (10 MB cap) and cycle/trap-proof recursive crawling.
5. **Universal MCP 2.x Compatibility**
   - Implements MCP Specification revision `2026-07-28` (`mcp==2.3.0`).
   - Dual output representation: Emits standard `content` (serialized JSON) and modern `structured_content` with registered `outputSchema` for compatibility across Cline, Roo Code, Continue, Claude Desktop, and Ollama/LM Studio agents.

---

## Architecture Overview

```
                      +---------------------------------------+
                      |       MCP Client (Cline / Roo /       |
                      |    Continue / Ollama / LM Studio)     |
                      +-------------------+-------------------+
                                          | JSON-RPC (STDIO / HTTP)
                                          v
                      +---------------------------------------+
                      |      WebIntel Server (MCP 2.x)        |
                      |   - 5 Minimal Tools (680 schema toks) |
                      |   - Dual Output (Text + Structured)   |
                      +-------------------+-------------------+
                                          |
                 +------------------------+------------------------+
                 |                                                 |
                 v                                                 v
    +-------------------------+                       +-------------------------+
    |    SearchAggregator     |                       |    DocumentExtractor    |
    | - DuckDuckGo / Bing     |                       | - Trafilatura (15ms)    |
    | - Wikipedia REST (0ms)  |                       | - PyMuPDF (PDF Docs)    |
    | - Brave API / SearXNG   |                       | - Edge Fallback (SPAs)  |
    | - Dedupe & URL Cleaner  |                       | - Token-Aware Chunker   |
    +-------------------------+                       | - BM25 Passage Scorer   |
                                                      +-------------------------+
                                                                   |
                                                      +------------v------------+
                                                      | Exact Span Grounding    |
                                                      | char_start / char_end   |
                                                      +-------------------------+
```

---

## Tool Catalog

| Tool Name | Parameters | Purpose & Contract |
| :--- | :--- | :--- |
| `web_search` | `query`, `count` (1-10, def 5), `freshness`, `domains`, `max_tokens` (def 600) | Provider-agnostic web search. Returns normalized URLs, titles, and concise snippets. |
| `extract_url` | `url`, `query`, `mode` (`passages` \| `full_markdown`), `max_tokens` (def 1500) | Extracts main content. In `passages` mode, runs BM25 ranking to return top passages with exact character spans. |
| `crawl_website` | `seed_url`, `max_depth` (1-3, def 2), `max_pages` (1-20, def 10), `query` | Bounded recursive website crawler with cycle detection and politeness tracking. |
| `web_map` | `url`, `limit` (def 50) | Fast discovery of domain URL structure via sitemap XML parsing and seed links. |
| `deep_research` | `topic`, `max_depth` (def 2), `max_queries` (def 4) | Multi-step autonomous research engine: breaks query into targeted searches, aggregates evidence, and highlights gaps. |

---

## Installation & Setup on Windows 11

### Prerequisites
- Windows 11 (64-bit)
- Python 3.11+ (Python 3.13 recommended)
- `uv` package manager (recommended) or standard `pip`

### Step 1: Clone & Install Dependencies
```powershell
# Navigate to project directory
cd "C:\Users\ACER\Downloads\Broswer for ai agnets"

# Using uv (fastest)
uv sync

# Or using standard pip
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

### Step 2: Environment Configuration
Copy `.env.example` to `.env` (optional—the engine operates out of the box with 0 external API keys):
```powershell
cp .env.example .env
```
Supported environment variables:
```env
# Optional external search keys (engine falls back to free providers automatically)
BRAVE_SEARCH_API_KEY=
SEARXNG_URL=

# Engine Performance & Limits
DEFAULT_SEARCH_TOKENS=600
DEFAULT_EXTRACT_TOKENS=1500
MAX_STREAM_BYTES=10485760
HTTP_TIMEOUT_SEARCH=8.0
HTTP_TIMEOUT_FETCH=8.0
```

---

## MCP Client Configuration

### 1. Cline & Roo Code (`cline_mcp_settings.json`)
Add the following to your Cline or Roo Code MCP configuration file (`%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`):

```json
{
  "mcpServers": {
    "webintel": {
      "command": "python",
      "args": ["-m", "src.server.mcp_server"],
      "cwd": "C:\\Users\\ACER\\Downloads\\Broswer for ai agnets",
      "disabled": false,
      "autoApprove": [
        "web_search",
        "extract_url",
        "web_map"
      ]
    }
  }
}
```

### 2. Continue.dev (`config.json`)
Add to `~/.continue/config.json`:
```json
{
  "experimental": {
    "modelContextProtocolServers": [
      {
        "transport": {
          "type": "stdio",
          "command": "python",
          "args": ["-m", "src.server.mcp_server"],
          "cwd": "C:\\Users\\ACER\\Downloads\\Broswer for ai agnets"
        }
      }
    ]
  }
}
```

### 3. Streamable HTTP Mode (Remote or Sidecar)
To run WebIntel as a persistent background service over HTTP:
```powershell
python -m src.server.mcp_server --transport http --port 8000
```

---

## Running Benchmarks & Regression Gates

The engine includes a single-command benchmark runner that executes the 50-query labelled evaluation set, verifies token budgets, measures p50/p95 latency, and enforces regression gates:

```powershell
# Run full 50-query benchmark suite
python -m benchmarks.run_benchmarks

# Run quick 5-query smoke test
python -m benchmarks.run_benchmarks --sample 5
```

### Regression Gates:
- Tool Schema Overhead $\le$ 1,000 tokens
- Search Call Returned Tokens $\le$ 650 tokens
- Extract Call Returned Tokens $\le$ 1,500 tokens
- Answer-Support Rate $\ge$ 60%
- False-Confidence Rate $\le$ 15%
- Zero uncalibrated scores anywhere in the payload

---

## Running the Automated Test Suite

```powershell
python -m pytest tests/ -v
```
All 32 test suites cover:
- SSRF and Private IP blocking (`tests/test_security.py`)
- Extraction and BM25 span grounding (`tests/test_extract.py`)
- Crawling and trap detection (`tests/test_crawler.py`)
- Official MCP protocol roundtrips (`tests/test_mcp_protocol.py` & `tests/test_mcp_e2e.py`)
- In-memory search deduplication and ranking (`tests/test_search_engine.py`)

---

## License & Architecture Records
- See [`docs/RESEARCH_REPORT.md`](file:///c:/Users/ACER/Downloads/Broswer%20for%20ai%20agnets/docs/RESEARCH_REPORT.md) for primary source citations and the full evidence ledger.
- See [`docs/COMPETITOR_MATRIX.md`](file:///c:/Users/ACER/Downloads/Broswer%20for%20ai%20agnets/docs/COMPETITOR_MATRIX.md) for deep evaluations of Tavily, Firecrawl, Exa, Brave, SearXNG, and Playwright MCP.
- See [`docs/ARCHITECTURE_DECISIONS.md`](file:///c:/Users/ACER/Downloads/Broswer%20for%20ai%20agnets/docs/ARCHITECTURE_DECISIONS.md) for ADRs and 3-axis Pareto trade-off tables.
- See [`docs/THREAT_MODEL.md`](file:///c:/Users/ACER/Downloads/Broswer%20for%20ai%20agnets/docs/THREAT_MODEL.md) for comprehensive security analysis and attack mitigations.
