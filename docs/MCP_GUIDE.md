# WebLens Model Context Protocol (MCP) Guide

## 1. Overview & Architecture
WebLens implements the official Model Context Protocol (MCP) specification (`mcp>=2.3.0`). It exposes compact, read-only tools designed to minimize context-window overhead while maximizing reasoning precision for AI agents.

### 1.1 Measured Schema Token Overhead
- **Total Registered Tools:** 4 (`web_search`, `extract_url`, `crawl_site`, `deep_research`)
- **Tokenizer:** `cl100k_base` (`tiktoken`)
- **Measured Schema Cost:** **732 tokens** (measured in EXP-006).
- **Pre-Registered Budget:** 1,000 tokens (leaving 268 tokens headroom).

---

## 2. Tool Definitions

### `web_search`
- **Description:** Search the live web. Returns titles, URLs, snippets and dates. No relevance scores.
- **Parameters:**
  - `query` (string, required): Search query.
  - `max_results` (integer, 1–10, default 5): Number of results to return.
  - `freshness` (enum: `day`, `week`, `month`, `year`, optional): Recency filter.
  - `domains` (array of strings, optional): Restrict search to specific domains.
  - `exclude_domains` (array of strings, optional): Exclude specific domains.
  - `max_tokens` (integer, 120–2000, optional): Hard output token budget.

### `extract_url`
- **Description:** Extract query-relevant passages from one URL, with URL, fetch time and exact span.
- **Parameters:**
  - `url` (string, required): Target HTTP(S) URL.
  - `query` (string, optional): Search term for query-focused passage scoring.
  - `max_tokens` (integer, 200–8000, optional): Token budget.
  - `full` (boolean, default false): Return full cleaned page text.

### `crawl_site`
- **Description:** Map a site's URLs (mode=map) or extract bounded pages (mode=crawl). Respects robots.txt.
- **Parameters:**
  - `url` (string, required): Start URL.
  - `mode` (enum: `map`, `crawl`, default `map`): Crawling mode.
  - `max_pages` (integer, 1–30, default 10): Maximum pages to visit.
  - `max_depth` (integer, 0–3, default 2): Maximum link depth.
  - `query` (string, optional): Extraction query term.
  - `max_tokens` (integer, 300–8000, optional): Output token budget.

### `deep_research`
- **Description:** Collect verbatim evidence from multiple sources. Reports gaps, conflicts and stale sources.
- **Parameters:**
  - `query` (string, required): Research question.
  - `max_tokens` (integer, 300–8000, optional): Output token budget.

---

## 3. Client Configuration Examples

### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "weblens": {
      "command": "python",
      "args": ["-m", "weblens.cli", "serve"],
      "env": {
        "BRAVE_API_KEY": "your_brave_key_here",
        "TAVILY_API_KEY": "your_tavily_key_here"
      }
    }
  }
}
```

### Cursor (`cursor_mcp.json`)
```json
{
  "mcpServers": {
    "weblens": {
      "command": "python",
      "args": ["-m", "weblens.cli", "serve"]
    }
  }
}
```

