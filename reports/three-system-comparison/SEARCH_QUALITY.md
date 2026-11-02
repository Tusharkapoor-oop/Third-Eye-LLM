# Search Quality & Retrieval Precision Analysis (V9)

## Evaluation Metrics
- **Precision@5**: Percentage of top-5 returned documents from authoritative, verified domains.
- **Answer Support Rate**: Percentage of queries where the returned passages contain direct evidence answering the inquiry.
- **False Confidence**: Rate of declaring certainty on unanswerable or fabricated queries.

## Quantitative Comparison

| Metric | System 1 (Local WebLens) | System 2 (Deployed WebLens) | System 3 (Tavily Direct) |
|---|---|---|---|
| **Mean Precision@5** | 0.240 | 0.413 | **0.653** |
| **Answer Support Rate** | 20.0% (3/15) | 40.0% (6/15) | **66.7% (10/15)** |
| **False Confidence Count**| 0 | 0 | 0 |
| **Authoritative Domains**| Wikipedia, Python.org, SEC.gov | Wikipedia, Python.org, SEC.gov, Reuters | Bloomberg, Forbes, AnandTech, ArXiv, Nature |

## Findings
1. **Network Egress Advantage**: Deployed WebLens achieves **0.413** Precision@5 vs Local WebLens **0.240** (+72% increase), demonstrating that cloud datacenter network egress improves search provider hit completeness over residential ISPs.
2. **Specialized Topic Gap**: Tavily achieves **0.653** Precision@5 due to pre-indexed technical sources (e.g. arXiv, Nature, specialist forums).
3. **Accuracy Calibration**: None of the three systems returned false confidence on unanswerable or ungrounded queries (0% false confidence across all three).

