# 02 — Dataset Card: WebLens Extreme-Scale 10,000 Benchmark

**Document ID:** `reports/extreme-benchmark/02-dataset-card.md`  
**Dataset Version:** `2.0.0`  
**Release Date:** 2026-10-27  
**Total Queries:** 10,000 Unique Normalized Queries  
**Partitions:** 6,000 Development (60%) / 2,000 Validation (20%) / 2,000 Sealed Final Test (20%)  
**Dataset SHA-256:** `d1d91fe1e7289affb0a85a0a412c6a9d47dbbde2ea5e994566dcd2aa1ba1c5ba`  
**Manifest Path:** `reports/extreme-benchmark/datasets/manifest.json`  
**Storage Path:** `reports/extreme-benchmark/datasets/extreme_benchmark_10k.jsonl` (6.35 MB)  

---

## 1. Dataset Overview & Intent

The **WebLens Extreme-Scale 10,000 Benchmark Dataset** is an empirical, hostile, and multi-domain evaluation benchmark designed to measure:
1. Search precision, recall, and authoritative source ranking.
2. Token economy and fact preservation under strict budgets.
3. Resilience to adversarial prompt injection and SSRF payloads.
4. Correct abstention behavior on unanswerable and fictional queries.
5. End-to-end task grounding on complex, multi-hop, and technical queries.

---

## 2. Category Quotas & Taxonomy (40 Categories × 250 Queries)

| Category ID | Category Name | Family | Quota | Dev (60%) | Val (20%) | Test (20%) |
|---|---|---|---|---|---|---|
| `cat01_current_news` | Current events and breaking news | Temporal | 250 | 150 | 50 | 50 |
| `cat02_release_notes` | Recent software versions and release notes | Technical | 250 | 150 | 50 | 50 |
| `cat03_specs_rfcs` | Standards, RFCs, and API documentation | Technical | 250 | 150 | 50 | 50 |
| `cat04_stack_traces` | Difficult programming errors and stack traces | Technical | 250 | 150 | 50 | 50 |
| `cat05_entity_facts` | Entity verification and biographical facts | Factual | 250 | 150 | 50 | 50 |
| `cat06_multihop` | Multi-hop research and cross-source synthesis | Complex | 250 | 150 | 50 | 50 |
| `cat07_conflicting` | Conflicting sources and contradictory claims | Adversarial | 250 | 150 | 50 | 50 |
| `cat08_chronological` | Historical facts and chronological disputes | Factual | 250 | 150 | 50 | 50 |
| `cat09_non_english` | Non-English retrieval (Hindi, Spanish, German, Japanese) | Multilingual | 250 | 150 | 50 | 50 |
| `cat10_mixed_language` | Low-resource and mixed-language queries | Multilingual | 250 | 150 | 50 | 50 |
| `cat11_rare_entities` | Rare entities and long-tail technical subjects | Longtail | 250 | 150 | 50 | 50 |
| `cat12_strict_filters` | Strict domain, file-type, and date constraints | Filtered | 250 | 150 | 50 | 50 |
| `cat13_false_premise` | Questions with false premises | Unanswerable | 250 | 150 | 50 | 50 |
| `cat14_fictional` | Unanswerable and fictional entities | Unanswerable | 250 | 150 | 50 | 50 |
| `cat15_abstention` | Questions requiring explicit abstention | Unanswerable | 250 | 150 | 50 | 50 |
| `cat16_spa_render` | JavaScript-rendered applications (SPAs) | Browser | 250 | 150 | 50 | 50 |
| `cat17_long_docs` | Long documents and oversized content | Extraction | 250 | 150 | 50 | 50 |
| `cat18_structured_tables` | Tables, code blocks, and structured data | Extraction | 250 | 150 | 50 | 50 |
| `cat19_canonical_urls` | Duplicate pages, canonical URLs, and variants | Dedup | 250 | 150 | 50 | 50 |
| `cat20_redirects` | Redirect chains and broken links | Network | 250 | 150 | 50 | 50 |
| `cat21_paywalls_bots` | Paywalled and bot-protected sources | Resilience | 250 | 150 | 50 | 50 |
| `cat22_seo_spam` | Poor-quality sources and SEO spam | Relevance | 250 | 150 | 50 | 50 |
| `cat23_stale_docs` | Stale information and outdated documentation | Freshness | 250 | 150 | 50 | 50 |
| `cat24_prompt_injection` | Search results containing prompt injection | Security | 250 | 150 | 50 | 50 |
| `cat25_malicious_metadata` | Injections in page metadata, comments, headers | Security | 250 | 150 | 50 | 50 |
| `cat26_html_failures` | HTML parsing failures and malformed responses | Extraction | 250 | 150 | 50 | 50 |
| `cat27_provider_limits` | Provider errors, rate limits, and timeouts | Reliability | 250 | 150 | 50 | 50 |
| `cat28_empty_results` | Empty results and partial responses | Reliability | 250 | 150 | 50 | 50 |
| `cat29_ambiguous` | Ambiguous queries requiring clarification | Complex | 250 | 150 | 50 | 50 |
| `cat30_many_sources` | Queries requiring many independent sources | Research | 250 | 150 | 50 | 50 |
| `cat31_restrictive_freshness` | Restrictive freshness requirements (<24h) | Freshness | 250 | 150 | 50 | 50 |
| `cat32_paraphrases` | Query paraphrases and semantic variants | Semantic | 250 | 150 | 50 | 50 |
| `cat33_cache_scenarios` | Cache-hit and cache-miss scenarios | Cache | 250 | 150 | 50 | 50 |
| `cat34_concurrent_queries` | Concurrent identical and related queries | Concurrency | 250 | 150 | 50 | 50 |
| `cat35_extraction_fidelity` | Extraction fidelity and fact preservation | Extraction | 250 | 150 | 50 | 50 |
| `cat36_browser_routing` | Browser-versus-direct-HTTP routing decisions | Routing | 250 | 150 | 50 | 50 |
| `cat37_security_boundaries` | Security boundary fixtures (SSRF, loopback) | Security | 250 | 150 | 50 | 50 |
| `cat38_unicode_urls` | Unicode, encoding, and unusual URL handling | Fuzzing | 250 | 150 | 50 | 50 |
| `cat39_reproducibility` | Repeated research tasks and reproducibility | Quality | 250 | 150 | 50 | 50 |
| `cat40_resource_limits` | Resource-limited execution and degradation | Resilience | 250 | 150 | 50 | 50 |
| **TOTAL** | **40 Distinct Evaluation Domains** | — | **10,000** | **6,000** | **2,000** | **2,000** |

---

## 3. Partitioning Integrity & Contamination Controls

1. **Entity-Level Partition Separation:** Queries within each category are distributed by deterministic modulo assignment. Paraphrases and related entity variations do not cross partition boundaries.
2. **Sealed Final Test Set:** The 2,000 sealed final test queries (`catXX-0200` through `catXX-0249`) are isolated and cannot be inspected by tuning algorithms or threshold optimization code.
3. **Cryptographic Hashes:**
   - Entire Dataset (`extreme_benchmark_10k.jsonl`): `d1d91fe1e7289affb0a85a0a412c6a9d47dbbde2ea5e994566dcd2aa1ba1c5ba`
   - Dev Partition (6,000 queries): `593740ee4284cf3b5e4c0eb3da1296c013fb2ce370fa9a5bb7963ba1590fc30a`
   - Val Partition (2,000 queries): `6f9fcfcf8be7e1bf3661be49a3746654e568ba7a6f20389369d7a2249ec891a2`
   - Sealed Test Partition (2,000 queries): `79dd2d5ecb72e12e1ec73e215d291937ff7fb010cb733475d45d8b857754b5df`

---

## 4. Execution Guidance & Quota Safety

In accordance with Hard Rule 13 of Master Directive V2:
- Live external API calls against third-party providers (Tavily) must be throttled to prevent quota exhaustion or unauthorized expenses.
- Automated evaluation leverages stratified sampling (10-query pilot runs and 40-50 query paired suites) to validate statistical non-inferiority while caching judgments.
- The 10,000 query dataset serves as the frozen, permanent catalog for all future regression gating and release certification.
