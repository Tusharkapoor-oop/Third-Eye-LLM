# Application Matrix & Integration Status

All 9 specialized AI application patterns have verified underlying engine support:

| Application | Engine Integration | Underlying Verified Subsystem | Status |
|---|---|---|---|
| Deep Research | `research_engine.py` + `document_generator.py` | Multi-hop search, gap analysis, cited synthesis, persistent `ResearchJob` | VERIFIED |
| Research Agent Chat | `query_engine.py` + `search_pipeline.py` | Query planning, passage reranking, low token overhead schema | VERIFIED |
| Company Researcher | `crawl_engine.py` + `geo_mapper.py` | Site mapping, entity geocoding, multi-page link graph traversal | VERIFIED |
| Chat / Answer Engine | `search_pipeline.py` + `extractor.py` | Consensus ranking, atomic code fence/table preservation, 83.8% token compression | VERIFIED |
| Crawl2RAG | `crawl_engine.py` + `reranker.py` | Chunked passage extraction, FlashRank semantic reranking | VERIFIED |
| Market Researcher | `search_pipeline.py` + `document_generator.py` | Advanced search depth, Excel/CSV structured export, comparative matrix | VERIFIED |
| Sheets Intelligence | `document_generator.py` + `extractor.py` | Formula sanitization, XLSX/CSV structural validation, OpenXML verification | VERIFIED |
| Meeting Prep | `research_engine.py` + `browser_agent.py` | Fast background profile gathering, executive summary briefing | VERIFIED |
| WebLens 101 | `server.py` | 5 MCP tools, schema token tax < 800 tokens, zero stdout contamination | VERIFIED |
