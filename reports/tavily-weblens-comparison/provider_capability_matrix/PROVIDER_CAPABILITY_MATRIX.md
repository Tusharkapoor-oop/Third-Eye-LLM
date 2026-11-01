# WebLens vs Tavily Comparison — Provider Capability Matrix

## Overview
Comparative capability matrix for the three search providers under test: DDGS, Bing, and Tavily API.

## Core Search Capabilities

| Capability | DDGS | Bing | Tavily API |
|------------|------|------|------------|
| **Free (no API key)** | ✅ Yes | ✅ Yes (limited) | ❌ Requires API key |
| **API Key Required** | ❌ No | ⚠️ Optional | ✅ Yes |
| **Maximum Results per Query** | 10 (configurable) | 10 (configurable) | 10 (configurable) |
| **Search Depth Options** | basic, advanced | basic, advanced | basic, advanced |
| **Time Filter** | None (always None) | None (always None) | day, week, month, year |
| **Domain Filtering** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Include Answers** | ❌ No | ❌ No | ❌ No (in pilot) |
| **Include Images** | ❌ No | ❌ No | ❌ No (pilot) |
| **Include Raw Content** | ❌ No | ❌ No | ❌ No (pilot) |

## Token Budget (R1 Prime Requirement)

| Metric | DDGS | Bing | Tavily API |
|--------|------|------|------------|
| **Median Tokens per Query** | 633 | 190 | 1348 |
| **Mean Tokens per Query** | 691 | 191 | 1384 |
| **Token Budget (cl100k)** | Within 600 budget | Well under 600 budget | Exceeds 600 budget (within 2000) |
| **Token Budget (o200k)** | Within 1000 budget | Well under 1000 budget | Exceeds 1000 budget (within 2000) |

## Provider Features

| Feature | DDGS | Bing | Tavily API |
|---------|------|------|------------|
| **HTTP Transport** | stdio-like | stdio-like | HTTPS REST |
| **Authentication** | None | None | Bearer token |
| **Rate Limiting** | Built-in (free tier) | Built-in | Per-key quotas |
| **Timeout (configurable)** | Yes | Yes | Yes (default 10s) |
| **Geographic Targeting** | ❌ No | ❌ No | ✅ Yes |
| **Content Freshness** | Moderate | Moderate | Configurable (day/week/month/year) |
| **Error Handling** | Graceful fallback | Graceful fallback | Graceful fallback |
| **Secret Redaction** | ✅ Yes (harness) | ✅ Yes (harness) | ✅ Yes (harness) |

## API Access & Cost

| Cost Model | DDGS | Bing | Tavily API |
|------------|------|------|------------|
| **Per-Request Cost** | $0 (free) | $0 (free tier) | Variable (per-key pricing) |
| **Monthly Quota** | Unknown (free) | Unknown (free tier) | Account-specific |
| **Per-Query Cost** | $0 | $0 | See Tavily pricing page |
| **Credential Management** | None needed | Optional | Required (env var: TAVILY_API_KEY) |
| **Key Exposure Risk** | N/A | N/A | Must protect in .env |

## Reliability & Uptime

| Metric | DDGS | Bing | Tavily API |
|--------|------|------|------------|
| **Pilot Success Rate** | 100% (5/5) | 100% (5/5) | 100% (5/5) |
| **Availability** | High (peer-to-peer) | High (Microsoft) | Account-dependent |
| **Historical Downtime** | None observed | None observed | N/A (first use) |
| **Failover Behavior** | ✅ Graceful | ✅ Graceful | ✅ Graceful |

## Summary Rankings

| Rank | Provider | Best For | Trade-off |
|------|----------|----------|-----------|
| 1 | **Bing** | Speed, token efficiency | Free tier limitations, optional key |
| 2 | **DDGS** | No-key independence, balance | Slower than Bing, more tokens |
| 3 | **Tavily** | Comprehensive extraction, freshness | API key required, higher cost |

## Key Observations
1. **Bing** offers the best performance-to-cost ratio for free-tier use, with dramatically lower latency and token usage
2. **DDGS** provides complete independence from API keys, at the cost of higher latency and token usage
3. **Tavily** provides the most capable extraction with freshness controls, but requires API key and has higher per-query cost
4. All three providers integrate seamlessly via the WebIntel SearchAggregator and TavilySearchProvider
5. The WebLens MCP can route queries through any of these providers based on the configured strategy