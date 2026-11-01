# Tavily Comparison Reports

**Campaign:** `stage7-20261028-a4a64151`  
**Dataset:** 108 frozen hand-labelled queries, 81 dev / 27 sealed test  
**Decision:** CONDITIONAL GO for default keyless local/single-user use; NO-GO for unconditional certification or parity claims

## Required reports

| File | Contents |
|---|---|
| `EXECUTIVE-SUMMARY.md` | Headline results, gates, recommendation |
| `METHODOLOGY.md` | Dataset, systems, metrics, statistics, integrity, limits |
| `QUALITY-RESULTS.json` | Search/research/extraction quality, conflict, abstention |
| `PERFORMANCE-RESULTS.json` | Latency, load, browser, crawl/map |
| `SECURITY-RESULTS.json` | 40 controlled cases, findings, limitations |
| `COST-AND-TOKEN-RESULTS.json` | Credits, tokens, budget accounting |
| `FAILURE-ANALYSIS.md` | Preserved failures and release implications |
| `REPRODUCE.md` | Commands, hashes, verification |
| `VERIFICATION.md` | Test, lint, type-check, secret-scan, and artifact results |

## Supporting evidence

- `PREREGISTRATION.json` — frozen rules, amendments, timing audit, exclusions.
- `data/DATASET-CARD.md` — dataset provenance and limitations.
- `data/` — frozen dataset, manifest, analysis, integrity hashes.
- `raw/` — per-record JSONL evidence and run metadata.
- `work/` — working files.

## Key warnings

- The 500-query and 10,000-query targets were **NOT ACHIEVED**. The 10,000-row synthetic corpus was **EXCLUDED**.
- Pre-registration timing was violated: paid dev search started before the recorded preregistration time.
- Conflict recall is **0/18**; keyless false confidence is **45%** combined and **60%** on the sealed test.
- Two failed retry cases (one medium finding): HTTP 429/503 are not retried.
- No full MCP conformance, browser sandbox isolation, or independent security audit is claimed.
- WebLens-Tavily is a Tavily-backed optimization layer, not an independent search engine.

Prior unsupported “full pass” artifacts are preserved at `../_archive/prior-run-20261027/` and are not current evidence.
