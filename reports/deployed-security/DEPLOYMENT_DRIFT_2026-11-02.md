# Deployment Identity Drift — Verified 2026-11-02

## Endpoint
`https://weblens-16131012091.us-central1.run.app` (Cloud Run, revision `weblens-00003-l9q` per V9 audit reports)

## Probes executed 2026-11-02 (curl, UTC)

| Probe | Result | Interpretation |
|---|---|---|
| `GET /` | HTTP 200 in 0.37s — `{"status":"ok","service":"weblens","version":"0.1.0","mcp_endpoint":"/mcp"}` | Service alive and healthy |
| `GET /healthz` | HTTP 404 (Google front-end error page) | Endpoint absent in deployed image |
| `POST /mcp` initialize (JSON-RPC) | HTTP 200 in 0.56s, server name `weblens`, no stack traces | Streamable-HTTP MCP transport works |
| `POST /mcp` tools/list | HTTP 200 — **10 tools**: web_search, extract_url, crawl_site, deep_research, company_research, market_research, market_portfolio, sheets_enrich, meeting_prep, research_chat | Deployed image contains the 9-app tool surface |
| Session header behavior | Server returned **no `mcp-session-id` header**, yet accepted a follow-up request without one | per-session state is not enforced remotely (noted, not reproducible as an identity probe) |

## Findings

1. **Deployed revision is stale relative to local `main`.** Commit `a9bd964` ("fix(serve): enable custom host headers and add /healthz endpoint for Cloud Run") added `/healthz` at `src/weblens/cli.py:189`, but the current deployment answers 404 on `/healthz`. The highlighted v9 reports named revision `weblens-00003-l9q`; a new revision has evidently not been deployed since.

2. **Build lineage is mixed.** The deployed tool set matches `src/weblens/mcp_server.py` (10-tool surface), while the repo also contains a separate `src/server/mcp_server.py` (5-tool surface: web_search, extract_url, crawl_website, web_map, deep_research) plus an additional `weblens/` top-level package variant. Local "System 1" and "System 2" therefore run different code paths than `src/server/mcp_server.py`, and the exact image source for `weblens-00003-l9q` cannot be pinned from the deployed artifact alone (version string `0.1.0` is generic).

3. **Redeployment is a required next action** (not performed autonomously — production deploy is outside this session's authorized scope): `gcloud run deploy weblens --source . --region=us-central1 --project=sewasetu-prod-2026 --quiet` should be run by the owner after the Tavily key rotation (SEC-V9-001), so the new image neither carries the leaked credential nor lags `/healthz`.

4. Adapted **four-tool conformance claim** (`docs/PROTOCOL.md`: four tools) does not match the deployed ten-tool surface; the protocol doc is stale relative to the deployed code path.

## Status
- Deployed availability: PASS (healthy, MCP functional)
- Deployment identity match with local main: FAIL (drift confirmed, documented above)
