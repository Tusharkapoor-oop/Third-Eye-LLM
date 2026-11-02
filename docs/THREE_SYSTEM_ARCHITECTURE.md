# Three-System Architecture Specification (V9)

This document establishes the architecture, boundaries, configuration, and interfaces for the three systems evaluated in WebLens V9.

## System Topology

```
+--------------------------------------------------------------------------------+
|                             EVALUATION HARNESS                                 |
+--------------------------------------------------------------------------------+
       |                                |                               |
       v                                v                               v
+--------------------+        +--------------------+        +--------------------+
|     SYSTEM 1       |        |     SYSTEM 2       |        |     SYSTEM 3       |
|   Local WebLens    |        |  Deployed WebLens  |        |    Tavily API      |
|     (Windows)      |        |   (GCP Cloud Run)  |        |    (Commercial)    |
+--------------------+        +--------------------+        +--------------------+
| - In-process / CLI |        | - HTTPS Endpoint   |        | - REST API Client  |
| - SQLite cache     |        | - GCP Datacenter   |        | - Proprietary index|
| - Keyless search   |        | - Full MCP Profile |        | - 1 credit / req   |
| - Zero cost ($0.00)|        | - 13 MCP Tools     |        | - Token heavy      |
+--------------------+        +--------------------+        +--------------------+
```

## System 1: Local WebLens MCP
- **Endpoint**: Local process / loopback MCP server (`http://127.0.0.1:8765/mcp`).
- **Runtime**: Windows 11 development machine, Python 3.13.
- **Provider Chain**: Independent keyless engines (`ddg,mwmbl,wikipedia`).
- **Cache**: SQLite-backed logical store at `~/.weblens/cache.db`.
- **Identity**: Independent, offline-capable research engine.

## System 2: Deployed WebLens MCP
- **Endpoint**: `https://weblens-16131012091.us-central1.run.app/mcp`.
- **Runtime**: Google Cloud Run serverless container, Python 3.11-slim, region `us-central1`.
- **Revision**: `weblens-00003-l9q`.
- **Tools Exposed**: All 13 tools under `WEBLENS_MCP_PROFILE=full` (`web_search`, `extract_url`, `crawl_site`, `deep_research`, `company_research`, `market_research`, `market_portfolio`, `crawl2rag_index`, `crawl2rag_query`, `meeting_prep`, `sheets_enrich`, `research_chat`, `tutorial_101`).
- **Transport**: JSON-RPC over HTTP Streamable MCP.
- **Cost**: $0.00 external search provider fees.

## System 3: Tavily Direct API
- **Endpoint**: `https://api.tavily.com/search`.
- **Authentication**: Bearer token via `TAVILY_API_KEY`.
- **Cost Model**: Commercial subscription, $0.005 per credit (1 credit for search, 2 credits for advanced search).
- **Behavior**: Rich proprietary search index returning consolidated answers and web hits.

