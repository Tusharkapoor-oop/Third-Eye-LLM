# Financial Efficiency & Cost Analysis

## Overview
Evaluating financial overhead and API consumption between WebLens local keyless orchestration and Tavily's commercial cloud API.

---

## 1. Unit Economics

| Operational Scale | WebLens Independent | Tavily API (Commercial Plan) | Savings with WebLens |
| :--- | :--- | :--- | :--- |
| **Cost Per Query** | **$0.00** | $0.005 (1 credit) | 100% |
| **Cost Per 1,000 Queries** | **$0.00** | $5.00 | $5.00 (100%) |
| **Cost Per 100,000 Queries** | **$0.00** | $500.00 | $500.00 (100%) |
| **Monthly Subscription Required** | None (Open Source / Local) | $20 - $500+ / mo | Full elimination of fixed overhead |
| **Quota Exhaustion Risk** | None | Yes (Hard limit stops agent) | Zero operational stoppage risk |

---

## 2. Token Budget & Downstream LLM Inference Cost

Downstream AI agents pay for input tokens consumed when processing tool outputs.

- **WebLens Mean Output Tokens**: **387.2 tokens / search result**.
- **Tavily Mean Output Tokens**: **1,432.4 tokens / search result** (+270% larger payload).
- **Inference Cost Impact** (assuming downstream Gemini 1.5 Pro / GPT-4o at $2.50 / 1M input tokens):
  - WebLens: ~$0.00097 per query in LLM input cost.
  - Tavily: ~$0.00358 per query in LLM input cost (+269% more expensive to process).
- **Total Combined Cost Per 1,000 Queries (API + Downstream Tokens)**:
  - WebLens: **$0.97**
  - Tavily: **$8.58** (WebLens is 8.8x cheaper overall).

