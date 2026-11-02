# Deployed MCP Security Plan & Verification

This document specifies the remote security plan, attack surface analysis, and empirical verification for the Deployed WebLens MCP service on Google Cloud Run.

## Target Details
- **Endpoint**: `https://weblens-16131012091.us-central1.run.app`
- **Revision**: `weblens-00003-l9q`
- **Runtime**: Google Cloud Run serverless container

## Attack Surface & Defenses

1. **Transport Security & TLS**:
   - TLS 1.3/1.2 termination managed by Google Cloud Front End.
   - HTTP requests receive 301/308 redirect or are terminated via HTTPS.
   - Clean separation of health check (`/`) and tool invocation endpoint (`/mcp`).

2. **Remote SSRF Probing via Tool Execution**:
   - Attacks attempting to extract GCP metadata (`http://metadata.google.internal/computeMetadata/v1/`) via `extract_url` or `crawl_site` are blocked by WebLens destination policy.
   - Attacks targeting AWS metadata (`169.254.169.254`) are intercepted before TCP connect.
   - Local container loopback (`127.0.0.1:8080`) is blocked from SSRF extraction.

3. **Protocol Fuzzing & Malformed Requests**:
   - Unknown JSON-RPC methods return standard JSON-RPC error objects without container crash or stack trace disclosure.
   - Oversized argument payloads are trapped and bounded by token budgets.

4. **Secret Exfiltration Resistance**:
   - Prompt injection attempts submitted via `deep_research` or search tools fail to leak container environment variables or API keys.

## Test Results
- **Suite**: `weblens-lab/security_lab/run_three_system_security_audit.py`
- **Result**: **10/10 PASSED (100.0%)**

