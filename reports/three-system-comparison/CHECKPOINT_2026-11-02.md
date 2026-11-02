# Three-System Evaluation Checkpoint — 2026-11-02

This is a current pilot record, not a final competitive ranking.

## Method

- One curated query: `CAT01_001`.
- Local WebLens crossed an actual stdio MCP boundary.
- Deployed WebLens crossed the actual HTTPS Streamable HTTP MCP endpoint.
- Tavily used the official direct `/search` endpoint through the protected adapter.
- Raw evidence: `evidence/raw_results/recon_checkpoint_2026-11-02.json`.

## Observed result

| System | Tool transport | Tool count | Search status | Current result |
|---|---|---:|---|---|
| Local WebLens | stdio | 13 | `ok` | PASS (pilot only) |
| Deployed WebLens | HTTPS Streamable HTTP | 13 | `ok` | PASS (pilot only) |
| Tavily Direct | Official REST | n/a | HTTP 401 | BLOCKED/PARTIAL |

The pilot is insufficient to estimate precision, recall, confidence intervals,
cost, or superiority.  Previous reports using different samples are historical
and must not be merged with this checkpoint.

## Identity observations

- Local and deployed server name/version both reported `weblens` / `0.1.0`.
- The deployed root returned HTTPS 200 from Google Frontend.
- An unauthenticated deployed `tools/list` request returned HTTP 200; see the deployed security report.
