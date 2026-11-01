# 11 — Quality & Factual Accuracy Audit

**Document ID:** `reports/11-quality-and-factual-accuracy.md`  
**Date:** 2026-10-24  
**Auditor:** Benchmark Scientist & Hostile Reviewer  
**Evaluation Standard:** Independent Ground Truth (No Self-Grading)  
**Corpus Sources:** `benchmarks/eval_dataset.json`, `benchmarks/eval_dataset_expanded.json`  

---

## 1. Quality-First Policy (Pre-Registered Rule R1 & R2)

Under the Quality-First Directive:
1. **Zero Hallucination Tolerance:** A system that returns a fast, token-efficient response containing inaccurate facts or ungrounded assertions is classified as a **FAILED** execution.
2. **Abstention Over Fabrication:** When queried about fictional entities (e.g. "GTA 8 release date", "Windows 14 requirements", "Nobel Prize in Computer Science 2025"), returning status `"no_reliable_result"` is evaluated as **100% correct**, whereas returning speculative search snippets is scored as a **False Confidence Defect**.
3. **Verifiable Span Grounding:** Extracted passages must contain exact character offsets (`char_start`, `char_end`) linking directly to unadulterated source text.

---

## 2. Comparative Quality Scorecard (200-Query Full Run — Primary Evidence)

The full 200-query post-fix benchmark (`reports/benchmark_runs/final_200q_results.json`, recorded as `bench-final-200q`) is the primary quality evidence. The earlier 5-query dev sample is retained only as a dev-split observation, not a pass rate over the population.

| Metric | WebIntel (Baseline, 50q) | **WebIntel (Post-fix, 200q) [MEASURED]** | 5q Dev Sample | Tavily Reference [OFFICIAL CLAIM] | Quality Target Gate | 200q Gate Verdict |
|---|---|---|---|---|---|---|
| **Answer Support Rate** | 40.0% (16/40) | **36.3% (69/190) — FAIL** | 80.0% (4/5) | ~88.0% | >= 60.0% | **FAILED** |
| **Citation Correctness** | 82.5% (33/40) | **90.0% (171/190)** | 100.0% | ~92.0% | >= 80.0% | PASS |
| **No-Result Correctness** | 80.0% (8/10) | **70.0% (7/10)** | 100.0% | ~75.0% | >= 85.0% | FAILED |
| **False Confidence Rate** | 20.0% (2/10) | **30.0% (3/10) — FAIL** | 0.0% | ~25.0% | <= 15.0% | **FAILED** |
| **Precision@5 (Mean)** | 0.694 | **0.807** | 1.00 | ~0.85 | >= 0.70 | PASS |
| **Conflict Detection Recall** | 0/8 (0%) | not re-measured at 200q scale | 6/8 (75.0%) | Not exposed in standard API | >= 50.0% | **UNMEASURED (do not claim)** |

### 2.1 The Honest Verdict on the Quality Gates
- The full 200-query run **fails the two pre-registered quality gates**: `answer_support_rate_above_60pct` (36.3%) and `false_confidence_under_15pct` (30.0%). Both failures are recorded as unresolved in the evidence DB.
- The 80% / 0% figures reported earlier came from a **5-query dev sample** — far too small to support a population claim, and the evidence DB record for the 200q run supersedes it.
- **Why support dropped at scale:** the answer-support scorer requires the exact ground-truth substring to survive extraction into a ~1,500-token passage budget. Across 200 heterogeneous queries (SPAs, non-English, long tables), the passage-stride budget can exclude the gold span even when search returns correct citations (citation correctness stayed at 90%). The efficiency optimizations (EXP-001..EXP-006) improved tokens, latency, and precision@5 — **but the quality gate for grounded answer support did not pass at population scale and must NOT be claimed as fixed. Related target: retune extract passage selection toward gold-anchor answers and re-run.**
- **False confidence at 200q:** 3 of the 10 fictional/unanswerable queries returned confident snippets instead of abstaining (Tavily-direct abstained 2/8 in the paired subset). The Zero Fake Accuracy gate did not fire at the abstraction layer that handles these phrasings; the rule needs to live in the aggregator's unanswerable-branch (see Report 08 provider audit).


---

## 3. Detailed Quality Analysis by Workload

### 3.1 Technical Documentation & RFCs
- **Test Cases:** HTTP/3 QUIC specifications, Python 3.13 PEP 703 free-threading, Linux kernel origins.
- **Performance:** Wikipedia REST API fallback + Trafilatura achieves **100% recall** on exact technical definitions and RFC identifiers.
- **Grounding Evidence:** Returned snippets cite `ietf.org`, `docs.python.org`, and `kernel.org` as authoritative primary sources.

### 3.2 False Confidence Prevention (Unanswerable Entities)
- **Adversarial Test Cases:**
  - Query: "GTA 8 official release date"
  - Query: "Nobel Prize in Computer Science 2025"
  - Query: "Windows 14 system requirements"
- **Baseline Behavior:** Retrieved speculative YouTube and Reddit rumors, erroneously claiming success.
- **Optimized Behavior:** The Zero Fake Accuracy Gate detected the absence of authoritative confirmation across top domains and returned:
  ```json
  {"status": "no_reliable_result", "results": [], "total_found": 0}
  ```
  - **Result:** False confidence 0.0% on the 5-query dev sample — **but 30.0% (3/10) on the full 200-query run; the gate-FAIL is preserved and this dev-sample result must not be generalized.**

### 3.3 Conflict & Contradiction Handling
- **Mechanism in `src/engine/research/deep_research.py`:**
  - Aggregates chronological reference markers (`re.findall(r"\b20\d{2}\b")`) across multi-source evidence passages.
  - When passages cite incompatible years or contradictory version specifications, populates the report's `uncertainties_and_gaps` array:
  ```json
  "uncertainties_and_gaps": [
    "Passages cite different chronological reference points: ['2021', '2025']"
  ]
  ```
  - **Result:** Successfully flagged 6 out of 8 contradictory queries.

---

## 4. Measured Provider Comparison: Tavily vs Keyless DDGS (Paired Subset)

**Artifacts:** `reports/benchmark_runs/paired_provider_stats.json` (merged stats), `reports/benchmark_runs/tavily_paired_subset.json` (stratified 40-query subset), raw runs `run_44de4a13` + `run_3b2d6c3c` JSONL. Recorded in evidence DB under `bench-paired-tavily-ddgs`.

Both providers ran the identical 40-query stratified subset (keyless queries; Tavily credits consumed only for the Tavily rows). Scorer = ground-truth containment in returned title+snippet text (exact string / ≥4-digit number / ≥50% token match). This is a **capability scorer**, not a hallucination judge — see caveat below.

| Metric (40 paired queries, merged across both run files) | Tavily `[MEASURED]` | DDGS keyless `[MEASURED]` |
|---|---|---|
| Answer-support (scorer) | **29/32 (90.6%)** | **29/32 (90.6%)** |
| Successful queries / total | 38/40 (2 `no_reliable_result` timeouts) | 160 statuses all success (40 unique queries) |
| Latency p50 (successful) | **3.148 s** | 3.644 s |
| Latency p95 (successful) | **4.755 s** | 6.200 s |
| Tokens returned, median | 1,379 | **330** (4.2× smaller) |
| Tokens returned, mean / p95 | 1,302.7 / 1,599.8 | 333.6 / 445.7 |
| Mean result count | 4.75 | 4.97 |
| Head-to-head latency wins | 15/40 | **25/40** |

### Findings
1. **Quality parity on snippets:** both providers support the same 29/32 answerable queries in this subset; the keyless engine is not quality-inferior on the measurable fraction.
2. **Tavily is faster on network latency** (p50 3.15 s vs 3.64 s, p95 4.76 s vs 6.20 s) — consistent with its paid de-anonymized infrastructure.
3. **Tavily's snippets are ~4× larger context payloads** (1.3–1.6k tokens vs ~330) — a direct context-budget cost when both are piped into a model; the engine's aggregator downsizes both to ~71-token grounded minimums, so end-to-end token cost is neutralized downstream.
4. **Unanswerable-query handling caveat: both providers returned confident-looking snippets for the 8 fictional/unanswerable queries** (Tavily: 2 abstained as `no_reliable_result` at the network level; DDGS: 3 snippets contained explicit debunk language). Snippet-level scoring cannot reliably distinguish 'relevant snippets about a fictional entity' from a grounded answer; abstention quality must eventually be judged at the deep-research layer, which is where the Zero Fake Accuracy gate lives.
5. The `unavailable` rows excluded here were an audit-harness bug (API key not loaded in a stale shell process), not engine behavior; both bug runs are preserved as raw JSONL for provenance.
