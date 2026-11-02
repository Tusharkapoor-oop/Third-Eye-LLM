# GAP-LEDGER — Quality Loop 2026-11-02

Evidence source: `evidence/raw/quality-loop-20261102/metadata.json`; no aggregate is treated as a 100% item-level pass.

| F# | Field | WebLens measured | Best comparator in supplied V9B | Gap / blocker | Root cause or evidence gap | Disposition |
|---|---|---:|---:|---|---|---|
| F1 | Search hit in top-5 | 88/90 | not derivable from aggregate | 2 misses | keyless provider coverage/query formulation | OPEN |
| F2 | Supported answer | 51/90 corrected rerun; prior report 73/90 | 80/90 corrected rerun | No increase; cycle rejected | scorer and provider chain changed together; causal isolation missing | OPEN |
| F3 | Unsupported claims | UNSUPPORTED | UNSUPPORTED | no answer artifact | baseline is search-only | STRUCTURAL |
| F4 | Trap abstention | 4/10 | 93/100 | 6 local flags | false-confidence policy/provider results | OPEN |
| F5-F10 | Extraction/RAG/research/citations | UNSUPPORTED | UNSUPPORTED | no compatible raw artifacts | required batteries not run | STRUCTURAL |
| F11 | Latency hard ceiling | 99/100; p50 922.7ms | Tavily p50 2381.6ms | one local request >2400ms | tail outlier | OPEN |
| F12 | Tokens | 100/100; mean 425.8 | Tavily mean 1527.3 | second run absent | reproducibility gate | REMEDIATING |
| F13 | Throughput | UNSUPPORTED | UNSUPPORTED | no sustained QPM windows | sequential benchmark | STRUCTURAL |
| F14 | Keyless cost | 100/100 | Tavily 100.0 credits | second run absent | reproducibility gate | REMEDIATING |
| F15 | Reliability | 100/100 | Tavily 1.0 | retry protocol absent | evidence protocol gap | REMEDIATING |
| F16 | Security | partial campaign only | not comparable | auth failure/deployed | frozen vector matrix incomplete | OPEN |
| F17 | Prior-cycle regressions | not fully re-derived twice | not applicable | independent audit absent | reproducibility protocol gap | OPEN |
