# Phase 04: Permanent Test Evidence System

**Status**: OPERATIONAL (verified with a deliberately failing record + restart survival test below)
**Database**: `test-results/database/test_evidence.db` (SQLite; append-only JSONL mirror in `test-results/database/test_evidence.jsonl`)
**Raw records**: `test-results/raw/*.jsonl` (append-only, one JSON object per attempt)

## Design

Every test execution — pass, fail, error, blocked, skipped, inconclusive, or
cancelled — is inserted as a new row. Nothing is ever updated or deleted.
Retries are additional attempt rows, so the original failure always remains.

### Schema (two tables)

- `test_runs` — one row per run: id, suite, source, start/end (UTC), commit SHA,
  Python/platform fingerprint, dataset hash, totals by status, notes.
- `test_cases` — one row per attempt: run_id, case_id, suite, name, timestamp (UTC),
  commit, expected vs actual, **status**, duration, latency metrics (JSON),
  token metrics (JSON), api calls, cost, redacted error, artifact path,
  **artifact SHA-256**, retry count, comparability flag, reason.

### Mandatory statuses implemented and enforced

`PASS, FAIL, ERROR, BLOCKED, SKIPPED, INCONCLUSIVE, CANCELLED, NOT_RUN`
(unrecognized labels are demoted to `INCONCLUSIVE`, never to `PASS`).

### Secret redaction

Error text and latency/token JSON are scanned for `tvly-…`, `sk-…`, `fc-…`,
`Bearer …` and replaced with `[REDACTED]` before insert and before the JSONL write.

### Answers the history queries must support

| Question | Supported by |
|---|---|
| Which tests passed on the current revision? | `test_cases WHERE status='PASS' AND commit_sha=?` |
| What regressed after a change? | previous-FAIL / current-FAIL + commit comparison |
| Which tests never executed? | cases absent across runs (runner manifests) |
| Failures resolved / unresolved | `summary` reports max-timestamp FAILs without later PASS |
| p95 / token deltas | `latency_metrics` / `token_metrics` JSON, compared across runs |

## Parametrized CLI (`testing/runner/evidence.py`)

```
python -m testing.runner.evidence record-pytest <junit.xml> --run-id <id> --suite <s>
python -m testing.runner.evidence record-benchmark <results.json> --kind baseline|benchmark
python -m testing.runner.evidence record-generic --suite SUITE --case ID --status STATUS ...
python -m testing.runner.evidence summary
python -m testing.runner.evidence export-markdown --out reports/test_history.md
```

## Acceptance test (executed, evidence-persistent)

1. **Known-failing record persists across restart:** a synthetic `FAIL` case with
   status `FAIL` was inserted for suite `evidence-selfcheck`, case
   `deliberate_failure` (see `test-results/raw/manual_evself-1591.jsonl`).
   The runner process exited; the record was then read back in a **new process**
   from the SQLite file and found intact with the artifact hash attached.
2. **Passing record alongside:** a `PASS` case `deliberate_success` was added the
   same way; both records remain queryable in the same run — the failure is not
   erased by the pass, and the run totals are exact.
3. **Integrity:** `PRAGMA integrity_check` → `ok`; database plus a timestamped
   backup copy is recomputed from the JSONL mirror, protecting the archive.
   the history from accidental deletion.

The verification transcript is recorded in the database itself under suite
`evidence-selfcheck` so future auditors can re-run the same checks.

## Recorded evidence inventory (populated during this audit)

| Suite | Content | Artifact |
|---|---|---|
| `pytest::main-suite` | all 237 unit/integration/security tests with per-test durations | `test-results/artifacts/junit_main_suite.xml` |
| `benchmark::baseline` | 50-query baseline run incl. 6 gate checks (2 failed) + 40 per-query rows | `reports/baseline_benchmark_results.json` |
| `benchmark::baseline` | 50-query baseline run incl. gate checks (2 legit gate FAILs recorded) | `reports/baseline_benchmark_results.json` |
| `benchmark::postfix` | post-fix benchmark run incl. gate checks | `reports/benchmark_results.json` |
| `pytest::main-suite` | post-fix full root suite (237/237 PASS) | `test-results/artifacts/junit_main_suite.xml` |
| `pytest::weblens-suite` | weblens package suite (154: 153 PASS + 1 skip) | `test-results/artifacts/junit_weblens_suite.xml` |
| `benchmark::providers_comparison_merged` | paired tavily-vs-ddgs subset stats | `reports/benchmark_runs/paired_provider_stats.json` |
| `benchmark::provider_comparison_remainder` | last paired batch (24 queries × 2 providers) | `reports/benchmark_runs/run_3b2d6c3c.jsonl` |
| `provider-comparison` | paired ddgs vs tavily rows (40 labels × 2 providers) | `reports/benchmark_runs/run_<id>.jsonl/.csv` |
| `browser::audit` | browser fallback acceptance tests | `reports/07-browser-vs-http-benchmarks.md` |
| `evidence-selfcheck` | the system's own acceptance tests | raw JSONL above |

Query the current state with `python -m testing.runner.evidence summary`.

## Backup protection

- Raw JSONL duplicates every SQLite row (dual write) — a lost database still
  preserves history.
- `test_history.db.bak-<timestamp>` is refreshed before any bulk maintenance.
