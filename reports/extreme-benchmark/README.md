# Extreme-Scale Benchmark — Truthful Equivalent

**Overall status:** PARTIAL  
**Delivered:** 108 frozen queries (81 dev / 27 sealed test)  
**Not achieved:** 500-query and 10,000-query campaigns  
**Excluded:** prior 10,000-row synthetic corpus  
**Decision:** CONDITIONAL GO for default keyless local/single-user use; NO-GO for unconditional certification

| File | Purpose |
|---|---|
| `00-scope-and-feasibility.md` | What was requested, what exists, why 500/10k were not reached |
| `01-dataset-audit.md` | Exact defects in the 10k synthetic corpus |
| `02-quality-results.md` | 108-query quality results |
| `03-performance-and-cost.md` | Latency, load, crawl/map, tokens, credits |
| `04-security-and-failure-results.md` | 40 controlled cases and product failures |
| `05-release-decision.md` | Gate table and final decision |
| `reproduce.md` | Commands and audit reproduction |
| `results/summary.json` | Machine-readable summary and NOT ACHIEVED statuses |

This directory is not a claim that 10,000 queries were run. It is the honest equivalent at the largest verified scale available.

Prior “unconditional full pass” artifacts are retained at `../_archive/prior-run-20261027/` and are not current evidence.
