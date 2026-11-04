# Benchmark Methodology

Current evidence consists of several non-equivalent systems and scorers:
historical V10 four-system reports, frozen datasets, root `quality_arena.py`,
and package-specific tests. They must not be merged into one score.

The next valid V14 benchmark must freeze the canonical stack, dataset hash,
scorer, provider configuration, cache mode, cold/warm policy, raw outputs,
failure taxonomy, and cost authorization before execution. Gemini must be
classified BLOCKED when its key/account is unavailable. Tavily calls require an
explicit budget authorization and exact spend ledger.
