# Tavily Direct Integration & Account Auditing

## Architecture
WebLens evaluation lab integrates with Tavily via the official REST API client in `weblens-lab/adapters/tavily_adapter/adapter.py`.

## Capabilities
- Search (`POST https://api.tavily.com/search`)
- Extract (`POST https://api.tavily.com/extract`)
- Account Usage Telemetry (`GET https://api.tavily.com/usage`)

## Key Findings & Comparison
- **Latency**: Tavily p50 latency is **3,062.2 ms**, whereas Deployed WebLens is **1,115.6 ms** (WebLens is 2.74x faster).
- **Token Efficiency**: Tavily averages **1,459.5 tokens** per search response, whereas WebLens averages **428.2 tokens** (WebLens uses 70.7% fewer tokens).
- **Cost**: Tavily consumes 1 credit per search request ($0.005 estimated cost). WebLens operates at **$0.00** search cost.
- **Precision**: Tavily achieves **0.653** Precision@5 on specialized queries vs WebLens **0.413**.

