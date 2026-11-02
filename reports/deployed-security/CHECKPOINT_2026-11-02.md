# Deployed MCP Security Checkpoint — 2026-11-02

## Scope

Non-destructive probes against the declared HTTPS Cloud Run MCP endpoint:
TLS/root response, unauthenticated capability discovery, four SSRF targets,
unknown JSON-RPC method handling, and a controlled prompt-injection query. No
load test, credential guessing, or third-party attack was performed.

## Result

`evidence/raw_results/safe_security_campaign_2026-11-02.json` recorded:

- PASS: TLS, four SSRF probes, malformed/unknown MCP method, prompt-injection secret check.
- FAIL: unauthenticated `tools/list` was accepted with HTTP 200.

The endpoint is therefore **not release-ready under a mandatory remote-auth
policy**. This external observation does not prove internal Cloud Run IAM,
tenant isolation, cache isolation, or server-side secret safety; those remain
UNVERIFIED without authorized deployment telemetry/configuration.
