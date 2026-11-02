# WebLens Security & Penetration Testing Findings

## Assessment Date
2026-11-01 (last full campaign); 2026-11-02 (SEC-V9-001 appended)

## Scope
Local WebLens MCP server, network layer, token budgeting engine, and isolated sandbox environment (`weblens-lab/`).

---

## Finding SEC-V9-001: Live Tavily API Key Committed to Git-Tracked Reports

### Metadata
- **Finding ID**: SEC-V9-001
- **Severity**: High (live credential disclosure in a public-trackable repository; also contradicts claim CLM-013)
- **Affected Component**: `reports/V8_SESSION_SUMMARY.md`, `reports/tavily-weblens-comparison/cost_analysis/COST_ANALYSIS.md` (both committed in `1c11ac3`)
- **Vulnerability**: Credential leakage — a live development Tavily key (`tvly-dev-…`, value redacted here) was pasted in plaintext into session reports, violating v9 rule 14 and the scan-verified CLM-013 claim ("0 secret hits in 92 files", which was scoped to source files only, excluding markdown reports).

### Discovery method
Working-tree grep of committed markdown for full key value during the 2026-11-02 v9 continuation session; confirmed via `git grep` at HEAD (2 files) and exact-match comparison against `.env` (ENV_MATCH — the disclosed key is the active credential).

### Remediation
1. Both report files redacted to `tvly-dev-…` placeholders.
2. Working-tree scan reopened to include all `.md`/report surfaces, not just source files.
3. **Required user action (rotation)**: the key must be rotated in the Tavily dashboard, because it remains in git history (commits `1c11ac3`) regardless of redaction. History rewrite was not performed autonomously (destructive, not authorized).
4. New key replaces `TAVILY_API_KEY` in `.env` and `weblens/.env` after rotation.

### Status
FIX APPLIED (redaction + coverage expansion); RESIDUAL RISK: key present in git history until rotated.

---

## Finding SEC-V8-001: Token Budget Exhaustion on Continuous Long-Form Pages

### Metadata
- **Finding ID**: SEC-V8-001
- **Severity**: Medium
- **Affected Component**: `src/engine/extract/chunker.py` & `src/engine/research/deep_research.py`
- **Vulnerability**: Context window overflow / token budget boundary violation.

### Preconditions
Caller requests `DeepResearchEngine.research` on topics whose primary Wikipedia or documentation source lacks double newline paragraph breaks (e.g., continuous markdown or prose).

### Exact Test Input
`question = "What is PEP 703?"` with `max_tokens = 2000`.

### Expected Behavior
Total serialized research report JSON must be `<= max_tokens + 200` envelope (<= 2,200 tokens).

### Observed Behavior
`DeepResearchEngine.research` emitted a 3,641 token report (+65.5% over the allowable ceiling), failing `test_deep_research_token_budget[What is PEP 703?]`.

### Root Cause
1. `src/engine/extract/chunker.py` previously claimed to support sentence-level sub-chunking of oversized paragraphs, but omitted implementation. When a document had only 1 paragraph break, the entire 3,165-token text was treated as a single chunk.
2. `src/engine/research/deep_research.py` line 229 evaluated `while rep_tokens > max_tokens and len(report.facts) > 1:`. When a single oversized fact was present (`len == 1`), the loop halted popping, leaving the oversized fact intact.

### Remediation
1. Implemented `_sub_split_paragraph` in `src/engine/extract/chunker.py` using sentence punctuation (`. `, `! `, `? `, `\n`, `; `, ` `) to bound chunks at `<= target_tokens * 4` characters (~720 characters / ~180 tokens).
2. Updated `src/engine/research/deep_research.py` to pop facts while `report.facts` contains any facts, and added progressive summary truncation if metadata overhead exceeds `max_tokens`.

### Regression Verification
- Re-executed `tests/test_token_boundaries.py`:
  - `test_deep_research_token_budget[What is PEP 703?]` PASSED.
  - All 18 boundary tests PASSED in 32.74s.

### Residual Risk
Negligible. Multi-layer safeguards now exist at both chunk generation and report serialization stages.

---

## Security Test Suite Summary

| Category | Suite | Tests Executed | Passed | Failed | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SSRF & Network** | `test_ssrf_penetration.py` | 80 | 80 | 0 | PASS |
| **Prompt Injection** | `test_injection_sanitization.py` | 50 | 50 | 0 | PASS |
| **Canary Key Leakage** | `test_p9_canary_secrets.py` | 3 | 3 | 0 | PASS |
| **Crawler Traps** | `test_crawler_traps.py` | 17 | 17 | 0 | PASS |
| **Tamper Mutation** | `test_gate1_tamper_mutation.py` | 6 | 6 | 0 | PASS |
| **MCP Stress** | `test_mcp_stress.py` | 10 | 10 | 0 | PASS |
| **Token Boundaries** | `test_token_boundaries.py` | 18 | 18 | 0 | PASS (after SEC-V8-001 fix) |
| **TOTAL** | | **184** | **184** | **0** | **100% PASS** |

