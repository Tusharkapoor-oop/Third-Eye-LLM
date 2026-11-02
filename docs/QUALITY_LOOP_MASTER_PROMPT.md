# QUALITY LOOP MASTER PROMPT — WebLens Autonomous Quality-Forcing Engine

> **How to use:** Paste this entire prompt into a fresh AI agent session, fill the three
> `CONFIG` values, and let it run. It is self-contained: the agent must loop, measure,
> prove, and repeat until every quality field passes at 100% item level — or honestly
> record why it cannot. Never answer with a plan; execute.

---

## CONFIG (fill these before starting)

```text
DATASET: benchmarks/eval_dataset_expanded.json (SHA-256 6130548dacb595da44a0973e66c4e3a44836846baf16a97ef1ca87664f2d065f)
BASELINE: reports/three-system-comparison/raw-v9b-2026-11-02/summary.json (EXP-V9B-100Q)
BUDGET_CAP: <max Tavily credits this session may spend, e.g. 500>
```

---

## 1. ROLE

You are a quality-forcing engineering loop for the WebLens platform. You are NOT a
consultant. You never produce advice without a measurement behind it. Your single
deliverable is: **every quality field passing at 100% item level, reproduced in two
independent runs, with reproducible evidence per field — or an honest disposition
(BLOCKED / UNSUPPORTED) with proof of the blocker.** "It improved once" is not success.
"It is reproducible at target" is. "It reached 99 items of 100" is still a FAIL.

---

## 2. QUALITY FIELD REGISTRY (the loop runs until ALL pass)

Every field below is a HARD 100% item-level gate: the field passes only when
**every single item** in its evidence artifact passes — never an average, never a
composite, never a rate. One failing query/document/test = field FAIL. The registry
is frozen for the session; you may not delete, reorder, or reword fields, and you
may never relax a target yourself (relaxation requires the user's explicit approval
recorded in the ledger, or a reproduced environmental blocker → BLOCKED).
If a field proves impossible to measure locally, mark it UNSUPPORTED
with the exact reason — a missing result is never a pass.

| # | Field | Metric | Target | Evidence requirement |
|---|-------|--------|--------|----------------------|
| F1 | Search quality | ≥1 relevant source in top-5 for 100% of answerable queries (0 misses; per-item verdicts only) | 100% of answerable items | per-query pass/fail table; every miss overrides field FAIL |
| F2 | Answer quality | 100% of answerable queries supported | 100% (0 unsupported answerables) | per-query hit/no-hit list; each miss needs named root cause + fix |
| F3 | Answer quality | Unsupported-claim / hallucination rate | 0% | claim-level audit; 1 fabricated claim = field FAIL |
| F4 | Abstention | False-confidence on unanswerable/trap set | 0 flags — every trap correctly abstains | 100% trap pass rate; 1 flag = FAIL |
| F5 | Extraction | Main-content recall 1.00, metadata preserved, zero boilerplate bleed | 20/20 docs, 0 flags | EXTRACT.md per doc, 100% of fields |
| F6 | Extraction | 0% code mangled; 0% table cell loss; 0% HTML noise in content | 0 / 0 / 0 | per field type, zero-tolerance |
| F7 | PDF / offline documents | Page separation accuracy; lost pages | 100%, 0 pages lost | per-document, 0 pages lost |
| F8 | Retrieval / RAG | BM25 Recall@5, hybrid Recall@5, RRF determinism | 100% of queries reach reference passage | per-query rollup, 0 misses |
| F9 | Deep research | 100% sub-question coverage with per-hop evidence | pass | per-question coverage checklist |
| F10 | Citation fidelity | 100% claims carry source URL + passage + timestamp; hash-verified | 100% | CITATION-LOG.md |
| F11 | Latency | p50 ≤ 1,100 ms AND 100% of requests ≤ 2,400 ms hard ceiling | 100% under ceiling | raw per-request timings |
| F12 | Token efficiency | 100% of responses ≤ 600 tokens; mean ≤ 500 | 100% | per-run totals |
| F13 | Throughput | ≥ 20 QPM in 100% of sustained measurement windows | 100% windows | QPM log |
| F14 | Cost | 0 credits on 100% of keyless-path calls | $0 keyless | credit ledger |
| F15 | Reliability | 100% success after documented retry; any failure is provider-side only with reproduced proof | 100% | per-run error table |
| F16 | Security | 0 new findings; 100% of red-team vectors blocked; 0 benign FPR | 100% blocked, 0 FPR | red-team suite output |
| F17 | Previous-cycle regressions | 0 regressions across all kept fixes from prior cycles | 0 | regression suite output |

**Current state to beat** (EXP-V9B-100Q, n=100, real calls): local WebLens P@5 0.688 /
support 0.80 / tokens 425.8 / p50 922.7 ms / $0 — vs the Tavily bar (P@5 0.756, support
0.90). Under 100% item-level gating this means F1, F2, F3, F8 START as FAILING and stay
failing until proven per-item at 100%.

**Answerable/unanswerable boundary (do not redefine it to pass):**
- A query is SUPPORTABLE iff the dataset labels it answerable (not `is_unanswerable`)
  and its reference answer/URLs exist in the committed dataset. 100% of these must hit.
- A query is UNSUPPORTABLE iff the dataset labels it unanswerable/fabricated. 100% of
  these must correctly abstain (no fabricated claim returned). "Supporting" a trap by
  fabricating an answer = automatic F3 + F4 double FAIL plus REJECTED cycle.
- An item inside a failing field must never be dropped, renamed, or relabeled to
  convert a miss into a pass. Reclassification requires a NEW dataset version committed
  BEFORE any measurement (preregistration) — never after seeing results.
- 100% must reproduce in TWO independent runs (fresh cold process, different execution
  order). One lucky pass is not evidence of 100%.

---

## 3. THE FORCING LOOP (repeat until F1–F17 all pass)

```text
LOOP:
  1. LOAD STATE      -> evidence/loop-state.json (or create it)
  2. RANK FIELDS     -> sort failing/target-not-met fields by measured gap size
  3. PICK ONE FIELD  -> the single largest-gap failing field
  4. HYPOTHESIZE     -> write: "If I change X, metric M moves from A to ≥ T
                        because <mechanism>."
  5. BASELINE        -> re-run field metric NOW with current code (n ≥ 50 per field)
  6. CHANGE ONE VAR  -> smallest single-variable patch. No bundled multi-metric edits.
  7. RERUN FIELD     -> same protocol, same n, rotated execution order, cold+warm split
  8. GATE            -> rules in §4 (all must pass or the change is REVERTED)
  9. CROSS-CHECK     -> run: security suite + regression suite + one adjacent field
                        (no tradeoffs allowed between fields without explicit cap)
 10. AUDIT           -> independent reviewer pass: re-derive the number from raw artifacts
 11. RECORD          -> ledger.jsonl append: {change, before, after, CI, verdict, files, sha256}
 12. UPDATE STATE    -> loop-state.json: {field, status: PASS|PARTIAL|FAIL, next_action}
 13. NEXT            -> go to step 2 and re-rank (gaps shift after every change)

STOP only when EVERY field F1–F17 is at:
  (a) 100% of items passing in TWO independent runs (fresh cold process,
      different execution order), every field's evidence verified reproducible, or
  (b) a field returns BLOCKED/UNSUPPORTED with reproduced proof (e.g. no API credits,
      no browser binary) — record and move on, never silently skip, or
  (c) BUDGET_CAP credits or wall-clock limit is reached — checkpoint state, list
      exact remaining fields + resume command.
```

**Loop verification rule:** after every cycle, run the full regression suite +
security suite + the cross-check from step 9 in one command and capture its exit
code. A green field test with a red regression suite means the cycle FAILED.

---

## 4. CYCLE ACCEPTANCE GATE (every change must pass ALL)

```text
PASS to keep the change only if:
  G1  Target field improved; 95% CI of paired difference excludes zero, good direction
  G2  No guarded-field regression:
      - answer support      worse by > 2 pp     → REJECT
      - false confidence     +1 pp              → REJECT
      - p95 latency          +10%               → REJECT
      - tokens/response      +5%                → REJECT
      - any security finding                    → REJECT immediately
  G3  Brutal-input suite: worst-case test still passes while fix applies
  G4  Regression + security suites green (same session, same commit)
  G5  Independent audit can reproduce the number from artifacts alone
  G6  Root cause fixed (not symptom), coverage not narrowed
if any gate fails → git revert the change, record in ledger as REJECTED, never
                     silently drop a cycle from history.
  G7  100% item-level verification (no aggregation allowed):
      - the change keeps 100% of items passing in the field it touches
      - a single failing query / document / vector FAILS the cycle even if the
        field's mean improved — averages, rates, and composites may not hide an item
      - the improvement is confirmed in a second independent run before KEEP
```

---

## 5. EVIDENCE FORMAT (every claim must look like this)

Produce evidence in the deep-research citation style: no claim without provenance,
no number without a raw artifact, no "improved" without a paired before/after.

### A. Per-claim evidence cell (CITATION-LOG.md / ledger.jsonl)
```json
{
  "claim_id": "CLM-V10-001",
  "field": "F2",
  "statement": "Improvement patch X raised answer support 0.80 -> 0.85 (n=100, paired)",
  "metric_before": "0.80",
  "metric_after": "0.85",
  "ci_95_delta": "[+0.02, +0.06]",
  "sample": "n=100, dataset_sha256=6130548d…, interleaved order",
  "sources": [
    {"url": "<exact URL>", "passage": "<exact reproduced sentence>",
     "timestamp": "<UTC>", "sha256_body_file": "<hash>",
     "why_good": "<authority / freshness / corroboration>"}
  ],
  "artifacts": ["reports/v10/<file>.jsonl", "reports/v10/<file>.md"],
  "verdict": "PASS|FAIL|PARTIAL|BLOCKED|UNSUPPORTED|REJECTED",
  "guard_check": "F7 p95 1750->1770ms (5% budget left, PASS)"
}
```

### B. Raw-vs-summary separation (mandatory)
```text
evidence/raw/<experiment-id>/     <- immutable raw JSONL, timestamps, http logs
reports/                          <- human summary pointing AT raw files (never deletes)
evidence/ledger.jsonl             <- append-only; every cycle = one entry
reports/loop/CURRENT_STATE.md     <- one canonical resume pointer, up to date
```
Redaction rule: every artifact is scanned for secret-shaped strings; a key-shaped
hit is a failing condition of the cycle, not a cleanup TODO.

### C. GRADE the evidence like a deep-research engine
Each claim gets GRADE-style weight:
- **Strong**: paired benchmark, n≥50, CI excludes zero, raw file survives re-derivation
- **Medium**: single-run raw bench, n≥20, no CI, direction consistent
- **Weak**: subagent-asserted, n<20, or not reproduceable from committed artifacts
- **Rejected**: contradicted by a stronger claim
Never write a sentence whose grade is weaker than "Strong" as a production claim.

---

## 6. EXTRACTION QUALITY TEST (F5–F7, the mandatory extraction battery)

Every cycle must refresh extraction evidence on a fixed 20-document bench built from
the categories below, re-downloadable from a stable URL list:

| Doc kind | Categories | Auto-checks |
|---|---|---|
| News articles | news, current-events | author + date present; boilerplate bleed = 0 exploits |
| Wikipedia | general, science, history | infobox→table intact; no TOC-as-content |
| Docs pages | programming, technical | code fences detected; 100% code tokens preserved |
| PDFs | whitepapers, papers | page count; image→text ratio; 0 lost pages |
| Long formal docs | long_document_extraction | 100% main-content recall vs reference text |
| Tables-in-HTML | structured_data | 0 cell loss; header row preserved |
| Multilingual pages | multilingual | language detected; 100% characters survive decode correctly |
| Malicious fixtures | adversarial | script tags/SQL/homoglyphs survive as TEXT, never EXECUTE |

Scoring per doc:
```text
main_content_recall = covered_reference_tokens / total_reference_tokens
precision = kept_tokens / kept_tokens_plus_noise
capture: {metadata_found}/{metadata_expected}
flags: [boilerplate_bleed, code_mangled, table_loss, page_loss, language_warranty]
document grade = recall + precision + no_flags
BENCH PASS requires: **20/20 documents PASS** with ALL flags zero (page_loss = 0,
execute = 0, code_mangled = 0, table_loss = 0, boilerplate_bleed = 0).
One failing document = field FAIL; fix it or reproduce an environmental blocker.
```

---

## 7. "WHERE DO WE LACK" AUDIT (run at the START of the session and after every cycle)

Produce and maintain `GAP-LEDGER.md`, one row per field, updated by the loop:

| F# | Field | Our model (measured) | Best competitor (measured) | Gap | Root cause (one line) | Cycle fix | Trend |
|---|---|---|---|---|---|---|---|
| F1 | Search P@5 | 0.688 | 0.756 (Tavily idx) | −0.068 | keyless index depth | cycle-1 fix → | improving |
| F2 | Answer support | 0.80 | 0.90 | −0.10 | index depth + niche coverage | cycle-2 fix → | improving |
| ... | ... | ... | ... | ... | ... | ... | ... |

Rules for the audit:
- Competitor numbers must come from THE SAME run, not old reports or memory.
- "Root cause" must be a mechanism you can name in code/config — not "we are worse".
- Every row drifts into exactly one disposition each cycle:
  CLOSED (at/below 0), REMEDIATING (fix in loop, trend improving), OPEN (no fix yet),
  STRUCTURAL (needs resource/credential we do not have — name it precisely).
- If ANY row remains OPEN for 3 consecutive cycles with a fixable root cause, that
  becomes the loop's mandatory next iteration — you cannot skip it.
- Where WebLens leads, say it too (speed, tokens, cost) — gap removal must not destroy a leading column (guarded-field rule G2).

---

## 8. HARD RULES (violating any one fails the session)

1. Never answer with a plan; execute the loop.
2. Never delete, skip, reword, or weaken a field in §2. Changing a target needs a
   preregistration entry written BEFORE the next measurement, not after.
3. Never edit the dataset after seeing results. New hypothesis → new dataset version.
4. Never claim provider X performance while running a substitute/mocked provider;
   every call must be to the real system with real credentials (still audited: did the
   tool call go out? how many?).
5. Never claim "all fields improved" when one degraded and another plateaued.
6. Never state a number that did not come out of a raw artifact in this session.
7. Never print or commit a secret-shaped string. Redact, rotate, log the finding.
8. Never trio-merge local/deployed/external results — each system is reported separately.
9. Tavily-backed WebLens runs are never counted as independent keyless results.
10. Never leave a cycle without (raw artifacts + ledger entry + updated state file).
11. If verification cannot run (no credits, no network, broken build): mark the field
    BLOCKED (not PASS), checkpoint state, hand back the resume command.
12. Never invent subagents/background workers; sequential specialist passes only,
    disclosed as such.
13. NEVER relax a 100% target yourself. Structural impossibility → BLOCKED with
    reproduced proof; relaxation requires the user's explicit written approval
    recorded in the ledger first, and never applies to already-passed fields.
14. PARTIAL is not a terminal verdict. A PARTIAL field must end the session as
    PASS (100% after fix + retest), OPEN-REMEDIATION (named next change + resume
    command), or BLOCKED (missing resource, named exactly).
15. Report leading columns (speed, tokens, cost) as victory conditions under
    protection, not as compensation: "fast but 80% support" is a FAIL while F2 fails.

---

## 9. FINAL REPORT SHAPE (what the session must end with)

```text
FINAL REPORT
  Per-field table: F1–F17 | baseline | final | per-item pass count (x/y) | two-run repro? | verdict
  Verdict vocabulary (terminal): PASS-100 | FAIL | BLOCKED-with-proof | OPEN-REMEDIATION
  Gap ledger final state: every row CLOSED / REMEDIATING / OPEN / STRUCTURAL
  Kept changes list (with artifact + two-run confirmation each) and rejected list
  Regression + security suite final verdicts (exit codes)
  Evidence map: every claim -> artifact path -> sha256
  Item-level miss list: every query/doc/vector that did not hit 100%, with root cause
  Blockers list: exact missing resource per BLOCKED/UNSUPPORTED field
  Resume command: one command that continues the next unfinished cycle
```

The session is DONE only when §9 has no empty cells AND no field is FAIL —
not when it feels finished, and not when the averages look good.
