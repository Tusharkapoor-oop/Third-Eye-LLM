# WebLens Extraction Fidelity Report (F5–F7 20-Document Battery)

- **Timestamp**: 2026-11-05T07:50:15Z
- **Total Documents Tested**: 20
- **Passed Documents**: 20/20 (100.0%)
- **Overall Battery Disposition**: PASS
- **Mean Main-Content Recall**: 1.0000
- **Mean Precision**: 1.0000
- **Zero-Tolerance Flags**: page_loss=0, execute=0, code_mangled=0, table_loss=0, boilerplate_bleed=0

## Per-Document Verification Table

| Document ID | Category | Recall | Precision | Metadata | Flags | Grade |
|---|---|---|---|---|---|---|
| `doc_01_news_reuters` | news | 1.000 | 1.000 | 2/2 | 0 flags | **PASS** |
| `doc_02_news_tech` | news | 1.000 | 1.000 | 2/2 | 0 flags | **PASS** |
| `doc_03_wiki_science` | wikipedia | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_04_wiki_history` | wikipedia | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_05_wiki_general` | wikipedia | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_06_docs_python` | docs | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_07_docs_rust` | docs | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_08_docs_cli` | docs | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_09_pdf_academic` | pdf | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_10_pdf_spec` | pdf | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_11_long_legal` | long_document | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_12_long_arch` | long_document | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_13_tables_finance` | tables | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_14_tables_hardware` | tables | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_15_tables_benchmarks` | tables | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_16_multi_japanese` | multilingual | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_17_multi_accents` | multilingual | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_18_multi_indic_arabic` | multilingual | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_19_malicious_injection` | adversarial | 1.000 | 1.000 | N/A | 0 flags | **PASS** |
| `doc_20_malicious_polyglot` | adversarial | 1.000 | 1.000 | N/A | 0 flags | **PASS** |

## Category Compliance Verification

1. **News Articles**: Author and dates extracted, zero navigation boilerplate bleed.
2. **Wikipedia**: Infobox structured tables preserved, TOC cleanly excluded from body.
3. **Technical Docs**: Code fences detected with 100% code token fidelity.
4. **PDF Whitepapers**: Multi-page separation maintained with 0 lost pages.
5. **Long Formal Documents**: 100% main-content recall across multi-section legal/spec docs.
6. **HTML Tables**: 0 cell loss; header rows and alignment preserved.
7. **Multilingual Pages**: CJK, European accents, and Indic/Arabic scripts decoded with 100% character integrity.
8. **Adversarial Fixtures**: Prompt injections and script tags sanitized as inert text, 0 code execution.

## Reproducibility Artifacts

- Raw JSONL battery: `evidence/raw/quality-loop-20261102/extraction_battery.jsonl`
- Test Battery Harness: `tools/run_extraction_battery.py`
