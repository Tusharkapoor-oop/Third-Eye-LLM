# WebLens Search Quality Strategy

## 1. Principles of Agentic Search Quality

Web search for autonomous AI agents differs fundamentally from human consumer search:

1. **Tokens Over Links:** AI agents do not click blue hyperlinks. They consume information tokens within a finite context window. The goal is to return dense, relevant, factual passages rather than navigation links.
2. **Authority and Ground Truth Over SEO Ranking:** Commercial search engines frequently rank commercial SEO landing pages or content affiliate farms above primary institutional sources. WebLens actively demotes content farms and boosts primary documentation.
3. **Abstention Over Confabulation:** If a search query refers to a non-existent entity or false premise, returning ungrounded search snippets induces severe downstream LLM hallucinations. WebLens prioritizes verified zero-result detection and premise rejection.

---

## 2. Multi-Provider Consensus & Routing Architecture

WebLens does not rely on a single upstream search provider. It coordinates a failover consensus pool across distinct providers:

```
                          [ Incoming Agent Query ]
                                     |
                                     v
                        [ Query Preprocessing & Clean ]
                                     |
                +--------------------+--------------------+
                |                                         |
                v                                         v
   [ Fast Keyless Providers ]               [ Commercial Fallback ]
   - DuckDuckGo                             - Tavily (Optional)
   - Bing Keyless                           - Brave Search (Optional)
   - Wikipedia API
   - Mwmbl / Mojeek
                |                                         |
                +--------------------+--------------------+
                                     |
                                     v
                        [ Result Consensus Merging ]
                                     |
                        [ Deduplication by Domain/URL ]
                                     |
                        [ Authority & Freshness Scoring ]
                                     |
                        [ Top-K Reranked Candidate List ]
```

### 2.1 Provider Chain Hierarchy
1. **Primary Keyless Cluster:**
   - **Bing Keyless & DuckDuckGo:** Fast general-purpose web discovery.
   - **Wikipedia API:** Instant authoritative factual grounding for entities, historical events, scientific definitions, and geographic data.
   - **Mwmbl / Mojeek:** Independent non-commercial web indices providing unbiased non-tracking alternative coverage.
2. **Secondary / Commercial Cluster (Optional):**
   - **Tavily API:** High-density pre-extracted LLM passages when explicitly configured with an API key.
   - **Brave Search API:** Independent search index fallback for specialized queries.

---

## 3. Query Decomposition and Normalization

### 3.1 Conversational Cleaning
Incoming queries from LLM agents often include conversational framing (e.g. `Can you please search for the latest updates on...`, `What are the core technical differences between asyncio and threading in Python?`).
The `clean_query()` normalizer:
- Strips polite conversational prefixes (`please search for`, `find me information on`).
- Extracts core comparative subjects (`differences between A and B` -> `A and B`).
- Normalizes punctuation and excessive whitespace.

### 3.2 Recursive Multi-Query Decomposition
For complex investigative tasks, `decompose()` breaks a single composite question into 2 to 6 focused sub-queries:
- Example: `"PostgreSQL vs MySQL performance for JSON workloads in 2026"`
  - Sub-query 1: `"PostgreSQL JSON performance benchmark 2026"`
  - Sub-query 2: `"MySQL JSON performance benchmark 2026"`
  - Sub-query 3: `"PostgreSQL vs MySQL JSON execution speed"`

---

## 4. Authority Scoring & Source Whitelisting

WebLens calculates a dynamic composite relevance score $S$ for each candidate URL:

$$S = S_{\text{lexical}} \times W_{\text{authority}} \times W_{\text{freshness}}$$

### 4.1 Institutional Domain Weighting
- **Tier 1 (Multiplier 2.0x):** Government, educational, and supranational portals (`.gov`, `.edu`, `.gov.in`, `.gov.uk`, `who.int`, `un.org`, `worldbank.org`, `sec.gov`).
- **Tier 2 (Multiplier 1.5x):** Peer-reviewed repositories, official technical documentation, and encyclopedias (`wikipedia.org`, `github.com`, `docs.python.org`, `arxiv.org`, `rtings.com`).
- **Tier 3 (Multiplier 1.0x):** Verified news outlets and general commercial domains (`reuters.com`, `bloomberg.com`, `nature.com`).
- **Demoted (Multiplier 0.2x):** Aggregator platforms, user forums, and social networks when searching for authoritative facts (`pinterest.com`, `quora.com`, `buzzfeed.com`).

---

## 5. Premise Validation & Trap Defense

When an agent issues a query based on a false presupposition (e.g., `"When was Windows 14 released?"`, `"Mars Colony One 1982 mission details"`):
1. **Search Snippet Inspection:** The search router evaluates snippet consensus. If all returned hits discuss the impossibility, debunking, or non-existence of the subject, the system flags the entity as unverified.
2. **Evidence Guard (`evidence_guard`):** If zero authoritative primary sources corroborate the premise, WebLens returns an explicit `no_reliable_result` response rather than allowing downstream agents to hallucinate plausible dates or specifications.

