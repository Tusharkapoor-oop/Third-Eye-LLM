# GAP-LEDGER — "Where do we lack" (v10 loop)

Seeded from EXP-V9B-100Q raw records (2026-11-02, same-run competitor numbers). Updated per cycle.

| F# | Field | Our model (measured, pre-correction) | Best competitor (same run) | Gap | Root cause | Cycle fix | Disposition |
|---|---|---|---|---|---|---|---|
| F1 | Search: ≥1 relevant in top-5 | 80/100 answerable (P@5 0.688) | Tavily 90/100 (0.756) | −10 items | 6 structural scorer defects + 11 real retrieval misses | PREREG-V10-001 corrected measurer; engine fix pending | REMEDIATING |
| F2 | Answer support | 0.80 | 0.90 | −0.10 | same as F1 | PREREG-V10-001 + Cycle-1 | REMEDIATING |
| F3 | Hallucination 0% | not yet item-audited | — | unmeasured | claim-level audit not yet run | pending | OPEN |
| F4 | Abstention 0 flags | 6 flags (heuristic; trap wording) | Tavily 7 flags | parity-ish | retrieval exposure to fabricated entities | pending audit | OPEN |
| F7 | p50/ceiling latency | 922.7 ms p50 (PASS zone) | Tavily 2381.6 | leading | — | protect (G2) | CLOSED (protect) |
| F8 | RAG recall 100% | unmeasured | — | unmeasured | no harness wired | pending | OPEN |
| F10 | Citation fidelity | unmeasured | — | unmeasured | no claim-level audit yet | pending | OPEN |
| F11 | Latency ceiling 100%<2.4s | unmeasured per-item | — | unmeasured | rerun | pending | OPEN |
| F12 | Tokens ≤600 mean/100% | 425.8 mean (baseline) | Tavily 1527 | leading | — | protect (G2) | CLOSED (protect) |
| F14 | $0 keyless | 0 credits baseline | Tavily 1 c/q | leading | — | protect (G2) | CLOSED (protect) |
| F15 | Reliability 100% | local 1.00, deployed 0.99 (1 graceful abstention) | Tavily 1.00 | deployed −1 | no_reliable_result abstention (graceful) | verify per-item | REMEDIATING |
| F16 | Security 100% blocked | 184/184 historical suites | n/a | — | standing suites | rerun before final | REMEDIATING (retest queued) |

Notes:
- Competitor numbers identical-same-run as required.
- G2 guardrails protect F7/F12/F14 while F1/F2 open.

*Preregistered scorer correction (2026-11-02, before re-measurement): ids 7, 9, 12, 19, 81, 82 are covered by PREREG-V10-001 (scoring availability was true for every system).*
