# WebLens Next Action & Priority Execution Plan

## 1. Executive Summary

This document specifies the prioritized next engineering and evaluation actions for the WebLens platform in accordance with strict engineering standards.

---

## 2. Prioritized Action Matrix

| Priority | Action Item | Target Subsystem | Expected Outcome | Verification Command |
|---|---|---|---|---|
| **P1** | Two-Run Reproducibility Benchmark on Deployed WebLens | `weblens-lab/evaluations/` | Execute two consecutive runs of the 100-query benchmark on Cloud Run to satisfy the Quality Loop two-run reproducibility requirement. | `python weblens-lab/evaluations/run_three_system_benchmark.py --dataset benchmarks/eval_dataset_expanded.json --sample 100` |
| **P2** | Measure Held-Out F1 Impact of ccTLD & Comparison Normalization | `src/weblens/search/router.py` | Verify that the newly added Tier 1 ccTLD rules (`.gov.in`, `.gov.uk`) and trailing comparison stripping resolve queries 52 and 94 to 100% Top-5 hit rate. | `pytest tests/test_search_engine.py` |
| **P3** | Gemini Native Tool Composition Benchmark | `weblens-lab/adapters/gemini_adapter/` | Evaluate Gemini 2.5 Flash agent composing WebLens MCP tools on 50 multi-hop reasoning questions when live key is supplied. | `python weblens-lab/adapters/gemini_adapter/test_gemini_integration.py` |
| **P4** | Crawl2RAG Hybrid Dense/Sparse Retrieval | `src/weblens/apps/crawl2rag.py` | Integrate lightweight local ONNX embedding model alongside SQLite FTS5 BM25 to boost semantic recall on non-keyword documentation. | `pytest tests/test_both_stack_comparison.py` |
| **P5** | International Prompt Injection Corpus Expansion | `weblens/src/weblens/security/injection.py` | Expand regex scanner patterns to detect indirect prompt injections in Spanish, French, and German. | `pytest tests/test_injection_sanitization.py` |

---

## 3. Immediate Next Execution Step

1. Commit and push all current V11 report and evidence documentation to the remote repository.
2. Maintain zero secret exposure throughout all future benchmark executions.
3. Keep working tree clean and synchronized across both `main` and `master`.

