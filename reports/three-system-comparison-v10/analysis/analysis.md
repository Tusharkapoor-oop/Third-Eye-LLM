# V10 Analysis

- Records: 120
- Dataset: v10.0.0

## Overall

| Metric | Local | Deployed | Tavily |
|---|---|---|---|
| Graded queries | 107 | 107 | 107 |
| Success rate | 0.9 | 0.942 | 1.0 |
| p50 ms | 837.0 | 1037.8 | 1537.4 |
| p95 ms | 1497.3 | 1622.2 | 2673.1 |
| P@5 | 0.553 | 0.471 | 0.74 |
| P@1 | 0.617 | 0.636 | 0.757 |
| MRR | 0.66 | 0.711 | 0.827 |
| nDCG@5 | 0.669 | 0.729 | 0.777 |
| Hit@5 | 0.729 | 0.832 | 0.935 |
| Tokens | 182.3 | 206.2 | 1378.7 |
| Credits | 0.0 | 0.0 | 120.0 |

## Per-category P@5

| Category | n | Local | Deployed | Tavily |
|---|---|---|---|---|
| academic_research | 4 | 0.6 | 0.55 | 0.95 |
| adversarial_injection | 4 | 1.0 | 0.0 | 0.0 |
| ambiguous_questions | 4 | 1.0 | 0.6 | 0.2 |
| company_research | 4 | 0.85 | 0.55 | 0.95 |
| competitive_intelligence | 4 | 0.5 | 0.3 | 0.55 |
| contradictory_sources | 4 | 0.6 | 0.0 | 0.2 |
| conversational_research | 4 | 0.0 | 0.05 | 0.3 |
| crawl2rag | 4 | 0.0 | 0.45 | 0.8 |
| current_events_news | 4 | 0.8 | 0.85 | 0.8 |
| general_factual | 4 | 0.95 | 0.8 | 1.0 |
| healthcare_information | 4 | 0.15 | 0.35 | 0.75 |
| industry_research | 4 | 0.6 | 0.4 | 0.65 |
| insufficient_evidence | 4 | 0.0 | 0.0 | 0.0 |
| legal_policy_research | 4 | 0.6 | 0.6 | 0.75 |
| long_document_extraction | 4 | 0.6 | 0.4 | 0.7 |
| market_research | 4 | 0.45 | 0.5 | 0.9 |
| multihop_reasoning | 4 | 0.85 | 0.5 | 0.75 |
| multilingual_queries | 4 | 0.25 | 0.3 | 0.9 |
| private_kb_retrieval | 4 | 0.55 | 0.55 | 0.55 |
| product_research | 4 | 0.6 | 0.45 | 0.5 |
| programming_developer_docs | 4 | 0.1 | 0.25 | 0.4 |
| public_sector_research | 4 | 1.0 | 0.7 | 1.0 |
| rare_specialized_topics | 4 | 0.7 | 0.45 | 0.55 |
| scientific_research | 4 | 0.65 | 0.5 | 0.95 |
| startup_research | 4 | 0.9 | 0.55 | 0.9 |
| stock_portfolio_research | 4 | 0.1 | 0.25 | 0.8 |
| structured_data_enrichment | 4 | 0.7 | 0.5 | 0.85 |
| technical_research | 4 | 0.65 | 0.6 | 0.9 |
| time_sensitive_questions | 4 | 0.75 | 0.65 | 0.8 |
| website_crawling | 4 | 0.25 | 0.4 | 0.75 |

## Paired comparisons

| Comparison | Pairs | Mean delta | 95% CI | W/T/L |
|---|---|---|---|---|
| local_minus_tavily_p5 | 107 | -0.187 | [-0.265, -0.108] | 24/34/49 |
| local_minus_tavily_ndcg5 | 107 | -0.108 | [-0.189, -0.027] | 48/19/40 |
| deployed_minus_local_p5 | 107 | -0.082 | [-0.142, -0.024] | 25/36/46 |
| local_minus_deployed_p5 | 107 | 0.082 | [0.024, 0.142] | 46/36/25 |

## Largest local-vs-Tavily P@5 gaps

- `crawl2rag_q02` (crawl2rag): local 0.0 vs Tavily 1.0 | local grades [] vs [1, 2, 2, 1, 1] | According to the Python documentation, how do you create a virtual environment with venv?
- `crawl2rag_q03` (crawl2rag): local 0.0 vs Tavily 1.0 | local grades [0, 0, 0, 0, 0] vs [1, 2, 1, 1, 1] | According to the FastAPI documentation, how do you declare a path parameter in a route?
- `healthcare_information_q04` (healthcare_information): local 0.0 vs Tavily 1.0 | local grades [0, 0, 0, 0, 0] vs [1, 1, 1, 1, 1] | What is the key difference between a virus and a bacterium?
- `industry_research_q02` (industry_research): local 0.0 vs Tavily 1.0 | local grades [0, 0, 0, 0, 0] vs [1, 1, 1, 2, 1] | Which are the three largest cloud infrastructure providers by market share?
- `multilingual_queries_q02` (multilingual_queries): local 0.0 vs Tavily 1.0 | local grades [] vs [1, 2, 1, 2, 1] | Quelle est la capitale de l'Allemagne ?
- `stock_portfolio_research_q03` (stock_portfolio_research): local 0.0 vs Tavily 1.0 | local grades [0, 0, 0, 0, 0] vs [1, 1, 2, 1, 2] | On which stock exchange is Microsoft Corporation primarily listed?
- `website_crawling_q04` (website_crawling): local 0.0 vs Tavily 1.0 | local grades [0, 0, 0, 0, 0] vs [1, 1, 1, 1, 1] | What is the difference between an HTTP 301 and 302 redirect?
- `academic_research_q01` (academic_research): local 0.0 vs Tavily 0.8 | local grades [0, 0, 0, 0, 0] vs [1, 2, 1, 0, 2] | Who are the authors of the seminal Transformer architecture paper Attention Is All You Need?
- `competitive_intelligence_q01` (competitive_intelligence): local 0.0 vs Tavily 0.8 | local grades [0] vs [1, 1, 1, 1, 0] | How does Snowflake's cloud architecture compare with Databricks Lakehouse architecture?
- `crawl2rag_q04` (crawl2rag): local 0.0 vs Tavily 0.8 | local grades [0, 0] vs [1, 1, 2, 1, 0] | According to the SQLite documentation, what is FTS5?
- `healthcare_information_q03` (healthcare_information): local 0.2 vs Tavily 1.0 | local grades [1, 0, 0, 0, 0] vs [1, 2, 2, 2, 1] | What does body mass index measure?
- `long_document_extraction_q02` (long_document_extraction): local 0.2 vs Tavily 1.0 | local grades [1, 0, 0, 0, 0] vs [1, 1, 1, 2, 1] | According to the IPCC Sixth Assessment Report, what global temperature limit is central to the Paris Agreement?
- `market_research_q02` (market_research): local 0.0 vs Tavily 0.8 | local grades [0, 0, 0, 0, 0] vs [1, 1, 1, 1, 0] | What does a stock market index measure?
- `multilingual_queries_q01` (multilingual_queries): local 0.0 vs Tavily 0.8 | local grades [] vs [1, 1, 1, 2, 0] | Python ka event loop kya karta hai aur yeh asynchronous programming mein kaise kaam karta hai?
- `multilingual_queries_q04` (multilingual_queries): local 0.0 vs Tavily 0.8 | local grades [] vs [2, 1, 1, 1, 0] | 什么是量子纠缠？
