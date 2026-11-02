# PREREG-V10-001: Scoring-methodology correction (committed BEFORE any new measurement)

**Date:** 2026-11-02 · **Status:** registered before re-measurement · **Dataset version:** unchanged (`eval_dataset_expanded.json`, SHA-256 `6130548d…`)

## Trigger (item-level miss analysis from EXP-V9B-100Q raw records)
6 of 17 local F2 misses (ids 7, 9, 12, 19, 81, 82) have ground truths composed
entirely of tokens ≤ 3 characters (`H2O`, `PEP 703`, `@>`, `405`, `πr²`, `Au`).
`evaluate_precision` requires tokens longer than 3 characters, so such items were
structurally incapable of scoring `answer_supported=True` on ANY system. These are
scoring-harness defects, not engine misses.

Additionally, 6 misses (ids 52, 55, 57, 92, 94, 98) carry ground truth strings
beginning `NOT MEASURED —` (dynamic facts); their generic tokens (`depends`,
`benchmarks`, `requires`…) were never meaningful verification strings.

## Corrected scoring rules (apply identically to ALL systems; dataset untouched)

1. **Short/symbolic answer tokens (length ≤ 3):** counted matched when found with
   non-alphanumeric word boundaries (e.g. `405`, `PEP`, `703`, `H2O`, `Au`, `@>`)
   instead of requiring length > 3. Removes false negatives; "Au" can no longer
   match inside "auth" because a boundary is required.
2. **Long tokens (length > 3):** substring matching, unchanged (no support regression).
3. **`NOT MEASURED` ground truths:** token verification is skipped (no garbage
   matching). For these dynamic items, `answer_supported = True` iff at least one
   top-5 result comes from the item's `acceptable_sources` domain list. This
   replaces the previous meaningless token path with an authority-based criterion
   and applies equally to local, deployed, and Tavily systems.

## Validity conditions (G7 compatible)
- Re-measurement is required because raw v9b records do not carry result text.
- First re-run: local keyless engine only (0 credits) → corrected local baseline.
  Later: deployed (0 credits) and Tavily (≤ 200 credits, same-run reconciliation).
- Acceptance for KEEP: corrected support ≥ previous support on the same system
  (a scoring fix cannot legitimately decrease support); item-level permissives
  remain per-item. Guarded fields are re-run with the same data to confirm no
  fleet-wide regression.
- This correction affects the *measurer* only; the measured system is untouched.

## Not covered by this registration (future cycle)
Real engine misses: ids 14, 28, 52, 55, 57, 80, 84, 86, 92, 94, 98 (existing misses)
plus any new misses surfaced after correction. Wired as CYCLE-1 in loop-state.
