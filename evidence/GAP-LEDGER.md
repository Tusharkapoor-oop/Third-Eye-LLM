# GAP-LEDGER — Quality Loop 2026-11-02

Evidence sources:
- `evidence/raw/quality-loop-20261102/metadata.json`
- `evidence/raw/quality-loop-20261102/extraction_battery.jsonl`
- `reports/local-security/local_security_results_v2.json`
- `reports/EXTRACTION_FIDELITY_REPORT.md`

| F# | Field | WebLens measured | Best comparator in supplied V9B | Gap / blocker | Root cause or evidence gap | Disposition |
|---|---|---:|---:|---|---|---|
| F1 | Search hit in top-5 | 88/90 | not derivable from aggregate | 2 misses | keyless provider coverage/query formulation | OPEN |
| F2 | Supported answer | 51/90 corrected rerun; prior report 73/90 | 80/90 corrected rerun | No increase; cycle rejected | scorer and provider chain changed together; causal isolation missing | OPEN |
| F3 | Unsupported claims | UNSUPPORTED | UNSUPPORTED | no answer artifact | baseline is search-only | STRUCTURAL |
| F4 | Trap abstention | 4/10 | 93/100 | 6 local flags | false-confidence policy/provider results | OPEN |
| F5 | Extraction main-content recall & noise | 20/20 PASS (100%) | UNSUPPORTED | 0 flags; recall 1.00, precision 1.00 | Measured across 20-doc battery; TOC stripped, 0 boilerplate bleed | CLOSED |
| F6 | Extraction fidelity (code/tables/HTML) | 20/20 PASS (100%) | UNSUPPORTED | 0% code mangled, 0% cell loss | Evaluated with code fences, multi-column tables, normalized escapes | CLOSED |
| F7 | PDF multi-page separation & 0 lost pages | 20/20 PASS (100%) | UNSUPPORTED | 0 lost pages | Multi-page text extraction verified via PyMuPDF backend | CLOSED |
| F8 | Retrieval / RAG (BM25 Recall@5) | UNSUPPORTED | UNSUPPORTED | no compatible raw artifacts | dedicated RAG battery not yet executed | STRUCTURAL |
| F9 | Deep research sub-question coverage | UNSUPPORTED | UNSUPPORTED | no compatible raw artifacts | multi-hop evidence evaluation pending | STRUCTURAL |
| F10 | Citation fidelity & SHA-256 integrity | UNSUPPORTED | UNSUPPORTED | no compatible raw artifacts | citation logging battery pending | STRUCTURAL |
| F11 | Latency hard ceiling | 99/100; p50 922.7ms | Tavily p50 2381.6ms | one local request >2400ms | tail outlier | OPEN |
| F12 | Tokens | 100/100; mean 425.8 | Tavily mean 1527.3 | second run absent | reproducibility gate | REMEDIATING |
| F13 | Throughput | UNSUPPORTED | UNSUPPORTED | no sustained QPM windows | sequential benchmark | STRUCTURAL |
| F14 | Keyless cost | 100/100 | Tavily 100.0 credits | second run absent | reproducibility gate | REMEDIATING |
| F15 | Reliability | 100/100 | Tavily 1.0 | retry protocol absent | evidence protocol gap | REMEDIATING |
| F16 | Security audit (SSRF, injection, MCP) | 38/38 PASS (100% local) | not comparable | 0 local findings | Local MCP suite passes 38/38 (0 FAIL, 0 UNVERIFIED) | CLOSED (Local) |
| F17 | Prior-cycle regressions | not fully re-derived twice | not applicable | independent audit absent | reproducibility protocol gap | OPEN |
