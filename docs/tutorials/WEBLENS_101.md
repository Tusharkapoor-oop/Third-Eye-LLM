# WebLens 101: Developer Tutorial & Agent Integration Guide

## 1. Introduction
WebLens is a local-first, evidence-first web intelligence and research platform designed for autonomous AI coding agents, developers, and researchers.

This tutorial provides step-by-step instructions for running WebLens on Windows 11 with VS Code, Roo Code, Cline, and Continue.

---

## 2. Quickstart Installation

```powershell
# 1. Clone repository and navigate to workspace
git clone https://github.com/your-org/weblens.git
cd "Broswer for ai agnets"

# 2. Create and activate a Python virtual environment (Python 3.11+ required)
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Install WebLens in editable mode
pip install -e weblens/
```

---

## 3. Step-by-Step Learning Modules

### Module 1: System Health & Provider Audit
Verify your local engine configuration:
```powershell
python -m weblens.cli doctor
```

### Module 2: Keyless Live Web Search
Query the live web using keyless multi-provider search:
```powershell
python -m weblens.cli search "Python asyncio event loop" --max-results 3
```

### Module 3: Query-Focused Passage Extraction
Extract verbatim passages with exact character offsets from a specific webpage:
```powershell
python -m weblens.cli extract https://docs.python.org/3/library/asyncio.html --query "Event loop"
```

### Module 4: Bounded Site Mapping & Crawling
Map website URLs while strictly respecting `robots.txt`:
```powershell
python -m weblens.cli crawl https://example.com --mode map --max-pages 5
```

### Module 5: Autonomous Deep Research
Execute a multi-hop deep research query with contradiction detection and source citations:
```powershell
python -m weblens.cli research "Comparison of SQLite FTS5 vs DuckDB BM25"
```

### Module 6: Running the Full Applications Suite
Run the verified tutorial script:
```powershell
python weblens/examples/tutorial_101.py
```

---

## 4. MCP Integration for Coding Agents

### Roo Code / Cline Configuration (`cline_mcp_settings.json`):
```json
{
  "mcpServers": {
    "weblens": {
      "command": "python",
      "args": ["-m", "weblens.cli", "serve"],
      "disabled": false,
      "autoApprove": [
        "web_search",
        "extract_url",
        "crawl_site",
        "deep_research"
      ]
    }
  }
}
```

### Continue Configuration (`config.json`):
```json
{
  "experimental": {
    "modelContextProtocolServers": [
      {
        "name": "weblens",
        "command": "python",
        "args": ["-m", "weblens.cli", "serve"]
      }
    ]
  }
}
```

