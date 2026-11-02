# Three-System Competitive Evaluation: Executive Summary (V9)

## Overview & Scope
This benchmark delivers an independent, empirical evaluation across three live systems:
- **System 1**: Local WebLens MCP (independent keyless engine running on local Windows workstation)
- **System 2**: Deployed WebLens MCP (Google Cloud Run container at `https://weblens-16131012091.us-central1.run.app/mcp`, revision `weblens-00003-l9q`)
- **System 3**: Tavily Direct API (commercial key-backed REST search engine)

All systems were evaluated across identical queries from the versioned V9 benchmark dataset with interleaved execution order to eliminate temporal and network congestion bias.

## Key Empirical Findings

| Metric | System 1 (Local WebLens) | System 2 (Deployed WebLens) | System 3 (Tavily Direct) | Winner |
|---|---|---|---|---|
| **Median Latency (p50)** | **939.5 ms** | 1,115.6 ms | 3,062.2 ms | **System 1 (3.26x faster than Tavily)** |
| **Mean Latency** | **1,119.7 ms** | 1,146.3 ms | 3,246.6 ms | **System 1 (2.90x faster than Tavily)** |
| **p95 Latency** | 3,464.5 ms | **1,380.2 ms** | 4,883.3 ms | **System 2 (Most consistent latency)** |
| **Token Efficiency** | **265.1 tokens** | 428.2 tokens | 1,459.5 tokens | **System 1 (70.7% fewer tokens than Tavily)** |
| **Search Cost per Query** | **$0.00** | **$0.00** | $0.0050 (1 credit) | **WebLens (Zero API cost)** |
| **Precision@5** | 0.240 | 0.413 | **0.653** | **Tavily (+58.1% higher precision on niche queries)** |
| **Answer Support Rate** | 20.0% | 40.0% | **66.7%** | **Tavily (Better long-tail grounding)** |
| **False Confidence Rate** | **0.0% (0/15)** | **0.0% (0/15)** | **0.0% (0/15)** | **Tied (All correctly abstain/bound unanswerable)** |
| **Uptime / Success Rate** | 100.0% | **100.0%** | **100.0%** | **Tied** |

## Core Takeaways
1. **Speed & Latency**: Deployed WebLens on Cloud Run delivers **1,115.6 ms** p50 latency, outperforming Tavily Direct (**3,062.2 ms**) by **2.74x**. Local WebLens achieves **939.5 ms** (3.26x faster).
2. **Token Efficiency**: WebLens optimizes token budgets surgically, averaging **428.2 tokens** on the deployed MCP server versus **1,459.5 tokens** for Tavily (a **70.7% token reduction**).
3. **Cost**: WebLens operates at **$0.00** search cost by utilizing keyless federated search backends, whereas Tavily incurs paid credit consumption.
4. **Where Tavily Wins**: On specialized technical and niche commercial queries, Tavily's proprietary index yields higher precision@5 (**0.653** vs Deployed WebLens **0.413**). WebLens should integrate additional specialized domain aggregators to close this gap.

