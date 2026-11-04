# Search Quality

**Status: PARTIALLY_VERIFIED.** Root search has multi-query planning, canonical
URL handling, authority priors, fallback providers, and token budgets. The live
arena exercised it against real web providers, but scores vary and the run is
not a frozen precision/recall evaluation. Historical V10 metrics are
configuration-scoped and not promoted to the root V14 release.

**Open gates:** frozen held-out Precision@K/MRR/nDCG, provider provenance
consistency, freshness validation, and canonical-stack selection.
