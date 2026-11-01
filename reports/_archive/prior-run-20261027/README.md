# Archived prior-run artifacts (2026-10-27)

These files were present before the Stage 7 campaign and contained claims that are not supported by the measured evidence in `reports/tavily-comparison/`.

Examples of unsupported claims in the archived set:

- “UNCONDITIONAL FULL PASS — CERTIFIED FOR PRODUCTION”
- “38/38 SSRF & Metadata probes blocked”
- “401 / 401 Automated Unit Tests Passing”
- “0.0% False Confidence” on unanswerable queries
- a 10,000-query dataset treated as valid ground truth

The Stage 7 campaign measured 38 PASS / 2 FAIL in 40 controlled security cases, 0/18 conflict recall, 45% keyless false confidence on unanswerable rows, and excluded the 10,000-row corpus because its factual labels are placeholders and its partition hashes do not reproduce.

These archived files are retained for historical preservation only. They are **not** current evidence and must not be cited as release certification. The current reports are:

- `reports/tavily-comparison/`
- `reports/redteam/`
- `reports/extreme-benchmark/`

No archived file was deleted.
