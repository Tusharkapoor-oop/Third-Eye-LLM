# V14 Autonomous Verification Reproduction Guide

## Environment Prerequisites

All commands must be executed from the repository root using the project virtual environment on Windows PowerShell:

```powershell
uv venv
uv pip install -e .
```

## 1. Run Complete Automated Verification Suite (61 Tests)

```powershell
uv run pytest tests/test_01_static_and_deps.py tests/test_02_mcp_protocol.py tests/test_03_security_boundaries.py tests/test_04_fuzz_and_chaos.py tests/test_05_extraction_quality.py tests/test_06_performance_stress.py tests/test_07_live_quality_arena.py tests/test_v14_document_generation.py tests/test_v14_event_and_dashboard.py tests/test_v14_geo_mapping.py tests/test_v14_crawl_and_research_lifecycle.py tests/test_v14_browser_agent.py tests/test_v14_integrated_workflows.py
```

Expected result:
```text
======================== 61 passed in ~78s ========================
```

## 2. Static Analysis & Security SAST

```powershell
uv run ruff check server.py security.py config.py schemas.py extractor.py reranker.py query_engine.py search_pipeline.py crawl_engine.py research_engine.py cache.py document_generator.py event_store.py geo_mapper.py browser_agent.py
uv run bandit -ll server.py security.py config.py schemas.py extractor.py reranker.py query_engine.py search_pipeline.py crawl_engine.py research_engine.py cache.py
```

Expected result:
- Ruff: 0 errors
- Bandit: 0 High, 0 Medium vulnerabilities

## 3. FastMCP Server STDIO Protocol Verification

```powershell
uv run pytest tests/test_02_mcp_protocol.py
```

Expected result:
- 5 tools registered with lowercase identifier syntax
- Flat schema without ambiguous `anyOf` / `oneOf`
- Combined schema token tax: **597 tokens** (< 800 budget)
- Zero non-JSON-RPC stdout output
