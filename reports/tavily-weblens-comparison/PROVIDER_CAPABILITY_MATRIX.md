# Tavily vs WebLens Provider Capability Matrix

## Comparison Categories

### Category 1: Independent Provider Comparison

| Capability | WebLens (Independent) | Tavily API | Evidence / Notes |
| :--- | :--- | :--- | :--- |
| **Search Engine Backbone** | DuckDuckGo, Mwmbl, Wikipedia | Proprietary Web Crawler / Index | WebLens uses keyless public endpoints |
| **External Credentials Required** | None ($0.00 / query) | Yes (`TAVILY_API_KEY`, billable) | Verified via `test_apps.py` |
| **Output Token Budget Enforced** | Yes (cl100k / o200k caps) | No (returns variable long JSON) | WebLens caps at 600 search tokens |
| **SSRF & DNS Rebinding Defenses** | Yes (strict destination policy) | N/A (hosted API) | 80/80 SSRF penetration tests passed |
| **Offline / Air-Gapped Mode** | Yes (with local index / SearXNG) | No (cloud SaaS only) | Docker container tested locally |

---

### Category 2: Same-Provider Orchestration Comparison (WebLens backed by Tavily)

| Feature | Direct Tavily API | WebLens with Tavily Backend | Value Added by WebLens |
| :--- | :--- | :--- | :--- |
| **MCP Standard Compatibility** | No native MCP HTTP/stdio | Native Streamable HTTP & stdio | Drop-in integration for AI agents |
| **Local SQLite Caching** | None (charges 1 credit every time) | Configurable TTL & 128MB cache | 0 credits consumed on repeated queries |
| **Context Window Token Capping** | Variable payload size | Strict cl100k token enforcement | Protects downstream LLM budget |
| **Prompt Injection Scanning** | None (returns raw scraped text) | Real-time injection quarantine | Strips zero-width & smuggled prompts |
| **Formula Injection Defense** | None (returns raw spreadsheet values) | Automatic `'` sanitization on `=,+,-,@` | Protects CSV/XLSX export from RCE |

---

### Category 3: End-to-End Application Comparison (9 Workflows)

| Workflow | WebLens Native Implementation | Tavily Equivalent / Official Offering | Acceptance Test Status |
| :--- | :--- | :--- | :--- |
| **1. Deep Research** | `weblens.apps.deep_research` | Open-source example (`deep-research`) | PASSED (`test_apps.py`) |
| **2. Company Researcher** | `weblens.apps.company` | Open-source repo (`tavily_company_researcher`) | PASSED (`test_apps.py`) |
| **3. Chat / Answer Engine** | `weblens.apps.chat` | REST API `include_answer=True` | PASSED (`test_apps.py`) |
| **4. Crawl2RAG** | `weblens.apps.crawl2rag` | Open-source repo (`crawl2rag`) | PASSED (`test_apps.py`) |
| **5. Market Researcher** | `weblens.apps.market` | Open-source example app | PASSED (`test_apps.py`) |
| **6. Sheets** | `weblens.apps.sheets` | Open-source repo (`tavily-sheets`) | PASSED (`test_apps.py`) |
| **7. Meeting Prep** | `weblens.apps.meeting` | Open-source repo (`meeting-prep-agent`) | PASSED (`test_apps.py`) |
| **8. WebLens 101** | `weblens.apps.tutorial_101` | Tavily Docs & Cookbook | PASSED (`test_apps.py`) |
| **9. Research Agent Chat** | `weblens.apps.research_chat` | Stateful conversational chat | PASSED (`test_apps.py`) |

