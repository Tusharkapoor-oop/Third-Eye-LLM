# WebLens Best Known Good (BKG) Platform Configuration

## 1. Authoritative Release Baseline

This document specifies the authoritative, production-verified Best Known Good (BKG) configuration for the WebLens web intelligence platform. Any future modification, optimization, or refactoring must meet or exceed these empirical baselines.

---

## 2. Baseline System State

- **Active Git Commit:** `1209abb` (Clean working tree on `main` and `master`)
- **Remote Repository:** `https://github.com/Tusharkapoor-oop/Third-Eye-LLM.git`
- **Python Runtime:** Python 3.11+ / Python 3.13.15
- **Cryptographic Ledger:** 45 verified entries in `evidence/ledger.jsonl`
- **Ledger Head Hash:** `0b3a8c1b87f61e48d8a21686299d60c6c0631fb7f14f620e533b854e416d3850`
- **Unit & Integration Tests:** 252 passing tests (`pytest tests/`) across unit, integration, stress, and security batteries.

---

## 3. Production Deployment Configuration

- **Provider:** Google Cloud Run (Fully Managed Serverless Container)
- **Service Name:** `weblens`
- **Region:** `us-central1`
- **Active Revision:** `weblens-00003-l9q`
- **Live Endpoint URL:** `https://weblens-16131012091.us-central1.run.app/mcp`
- **Health Check URL:** `https://weblens-16131012091.us-central1.run.app/`
- **Active Profile:** `--profile full` (All 13 core and specialized intelligence tools enabled)
- **Transport:** Streamable HTTP / Server-Sent Events (SSE) JSON-RPC 2.0
- **Ingress / TLS:** Managed HTTPS / TLS 1.3 termination with HSTS
- **Egress Boundary:** Socket-level DestinationPolicy blocking RFC 1918, loopback, and metadata IPs

---

## 4. Empirical Performance Baselines

The following performance figures represent verified measurements on the 100-query benchmark dataset (`eval_dataset_expanded.json`, SHA-256 `6130548d...`):

| Metric | Deployed WebLens (Cloud Run) | Local WebLens MCP | Tavily Direct API |
|---|---|---|---|
| **p50 Latency** | **1,094.0 ms** | 3,548.8 ms (Local keyless) | 2,001.1 ms |
| **p90 Latency** | **1,395.8 ms** | 3,623.7 ms | 2,651.2 ms |
| **p95 Latency** | **1,590.8 ms** | 3,678.3 ms | 2,803.6 ms |
| **Mean Latency** | **1,159.9 ms** | 3,571.5 ms | 2,044.1 ms |
| **Mean Tokens / Query** | **425.5 tokens** | **297.4 tokens** | 1,486.6 tokens |
| **Answer Support Rate** | **87.0%** (87/100) | 56.0% (56/100) | 90.0% (90/100) |
| **Cost per 100 Queries** | **$0.00 (0 credits)** | **$0.00 (0 credits)** | $0.50 (100 credits) |
| **Security Audit Pass Rate**| **100% (10/10 probes)** | **100% (26/26 probes)** | Not audited |

---

## 5. Defensive & Security Policies

1. **SSRF DestinationPolicy (`src/weblens/net/ssrf.py`):**
   - Blocks IPv4: `0.0.0.0/8`, `10.0.0.0/8`, `127.0.0.0/8`, `169.254.0.0/16`, `172.16.0.0/12`, `192.168.0.0/16`, `224.0.0.0/4`, `240.0.0.0/4`, `255.255.255.255/32`.
   - Blocks IPv6: `::/128`, `::1/128`, `fc00::/7`, `fe80::/10`, `ff00::/8`.
   - DNS resolution pinning: Hostname resolved to IP before socket connect and validated.
   - Redirect tracking: Intercepts and validates each hop in 30x redirect chains.

2. **Spreadsheet Defense (`src/weblens/apps/sheets.py`):**
   - Prepends single quote (`'`) to any cell value starting with `=`, `+`, `-`, `@`, `\t`, `\r`, or `\n`.

3. **Prompt Injection Scanner (`weblens/src/weblens/security/injection.py`):**
   - Regex patterns covering instruction overrides, system overrides, role hijacking, and credential exfiltration.
   - 35/35 adversarial vectors blocked in unit testing.

