# V10 Analysis

- Records: 10
- Dataset: v10.0.0

## Overall

| Metric | Local | Deployed | Tavily |
|---|---|---|---|
| Graded queries | 10 | 10 | 10 |
| Success rate | 1.0 | 1.0 | 1.0 |
| p50 ms | 3522.4 | 1211.5 | 2324.8 |
| p95 ms | 3649.0 | 1622.6 | 2725.8 |
| P@5 | 0.62 | 0.8 | 0.92 |
| P@1 | 0.8 | 0.8 | 1.0 |
| MRR | 0.85 | 0.9 | 1.0 |
| nDCG@5 | 0.867 | 0.932 | 0.908 |
| Hit@5 | 0.9 | 1.0 | 1.0 |
| Tokens | 206.0 | 266.4 | 1367.4 |
| Credits | 0.0 | 0.0 | 10.0 |

## Per-category P@5

| Category | n | Local | Deployed | Tavily |
|---|---|---|---|---|
| current_events_news | 4 | 0.65 | 0.9 | 0.85 |
| general_factual | 4 | 0.65 | 0.8 | 1.0 |
| technical_research | 2 | 0.5 | 0.6 | 0.9 |

## Paired comparisons

| Comparison | Pairs | Mean delta | 95% CI | W/T/L |
|---|---|---|---|---|
| local_minus_tavily_p5 | 10 | -0.3 | [-0.44, -0.16] | 0/3/7 |
| local_minus_tavily_ndcg5 | 10 | -0.041 | [-0.271, 0.109] | 4/4/2 |
| deployed_minus_local_p5 | 10 | 0.18 | [0.06, 0.32] | 5/5/0 |
| local_minus_deployed_p5 | 10 | -0.18 | [-0.32, -0.06] | 0/5/5 |

## Largest local-vs-Tavily P@5 gaps

- `general_factual_q02` (general_factual): local 0.4 vs Tavily 1.0 | local grades [2, 2, 0, 0, 0] vs [2, 1, 1, 1, 1] | What is the capital city of Australia?
- `general_factual_q03` (general_factual): local 0.4 vs Tavily 1.0 | local grades [2, 2, 0, 0, 0] vs [2, 1, 1, 2, 1] | How many bones are in the adult human body?
- `current_events_news_q01` (current_events_news): local 0.0 vs Tavily 0.4 | local grades [0] vs [2, 0, 1, 0, 0] | What major announcements were made regarding Google Gemini in late 2024 and 2025?
- `current_events_news_q02` (current_events_news): local 0.6 vs Tavily 1.0 | local grades [2, 2, 2] vs [1, 1, 2, 1, 1] | Which company developed the GPT-4 model released in March 2023?
- `technical_research_q01` (technical_research): local 0.4 vs Tavily 0.8 | local grades [0, 2, 2, 0, 0] vs [1, 2, 0, 1, 1] | What is Python PEP 703 and how does it propose to make the Global Interpreter Lock optional?
- `technical_research_q02` (technical_research): local 0.6 vs Tavily 1.0 | local grades [2, 2, 0, 1, 0] vs [1, 1, 1, 2, 1] | What does the HTTP 429 status code indicate?
- `general_factual_q04` (general_factual): local 0.8 vs Tavily 1.0 | local grades [2, 2, 1, 0, 1] vs [2, 1, 1, 1, 1] | What is the tallest mountain above sea level on Earth?
- `current_events_news_q03` (current_events_news): local 1.0 vs Tavily 1.0 | local grades [2, 2, 2, 1, 1] vs [2, 2, 2, 2, 2] | What was the name of the NASA mission that first landed humans on the Moon in July 1969?
- `current_events_news_q04` (current_events_news): local 1.0 vs Tavily 1.0 | local grades [2, 2, 1, 1, 1] vs [2, 2, 1, 1, 1] | Which city hosted the 2024 Summer Olympic Games?
- `general_factual_q01` (general_factual): local 1.0 vs Tavily 1.0 | local grades [2, 2, 2, 2, 2] vs [1, 2, 1, 1, 2] | What year was the Python programming language first released by Guido van Rossum?
