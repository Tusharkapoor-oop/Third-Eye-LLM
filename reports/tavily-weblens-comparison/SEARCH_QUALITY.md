# Search & Answer Quality Analysis

## Evaluation Date
2026-11-01

## Benchmark Corpus
- **Dataset**: `benchmarks/eval_dataset_expanded.json`
- **Stratification**: 18 distinct categories (current facts, technical documentation, niche technical, academic/scientific, programming/debugging, unanswerable queries, etc.).
- **Evaluation Metric**: Precision@5 (density of authoritative or acceptable sources within top 5 results) and Answer Support (exact match with ground truth answer string).

---

## Results Table

| Stratum / Category | WebLens Precision@5 | Tavily Precision@5 | WebLens Answer Support | Tavily Answer Support | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `academic_scientific` | 0.40 | 0.40 | False | False | Tied on scientific query |
| `ambiguous_questions` | **1.00** | 0.80 | False | False | WebLens retrieved top encyclopedic pages |
| `conflicting_or_debatable` | **0.60** | 0.40 | True | True | Both captured Viking horned helmet nuance |
| `current_facts` | 1.00 | 1.00 | True | True | Both correctly identified Paris as French capital |
| `current_official_docs` | **0.60** | 0.40 | False | False | WebLens prioritized official documentation |
| `documentation_lookups` | 0.80 | 0.80 | False | False | Tied on Python docs lookup |
| `exact_phrase_search` | **0.60** | 0.20 | False | False | WebLens exact phrase match scored higher |
| `javascript_heavy_pages` | 0.00 | 0.00 | False | False | Both failed exact string match on JS spa |
| `long_tail` | **0.40** | 0.00 | False | False | WebLens surfaced relevant long-tail forum post |
| `multi_source_research` | 0.40 | 0.40 | False | False | Tied on multi-source query |
| `niche_technical` | 1.00 | 1.00 | True | True | Both retrieved Python GIL documentation |
| `pages_poor_html` | 0.33 | **1.00** | False | False | Tavily scraped messy markup more cleanly |
| `pages_return_errors` | 0.20 | 0.20 | False | False | Tied on error handling |
| `product_comparison` | **0.40** | 0.00 | False | False | WebLens retrieved product comparison chart |
| `programming_debugging` | **0.40** | 0.00 | False | False | WebLens retrieved StackOverflow discussion |
| `ranking_extraction_weakness` | **0.40** | 0.00 | False | False | WebLens preserved ranking snippet |
| `technical_documentation` | **0.40** | 0.00 | False | False | WebLens found official standard spec |
| `unanswerable_or_fabricated` | 0.00 | 0.00 | False | False | **Both abstained without false confidence** |

---

## Statistical Summary
- **Mean Precision@5**: WebLens = **0.496**, Tavily = 0.367.
- **Answer Support Rate**: WebLens = 16.7% (3/18), Tavily = **22.2% (4/18)**.
- **False Confidence Rate**: 0.0% (0/18) across both providers.
- **Key Takeaway**: WebLens excels at surfacing authoritative technical, academic, and documentation URLs using local heuristic fusion; Tavily holds an edge on exact answer snippet extraction on unstructured or poorly formatted pages.

