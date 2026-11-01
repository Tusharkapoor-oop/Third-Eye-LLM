# WebLens Isolated Sandbox Architecture

## Purpose
The `weblens-lab/` sandbox provides a dedicated, reproducible, and strictly isolated testing environment for executing evaluations, running paired A/B benchmarks against Tavily, and conducting authorized security red-team penetration tests without risk to production services or host files.

---

## 1. Directory Structure

```text
weblens-lab/
├── sandbox/
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── .env.example
│   ├── config/              # Isolation verification & boundary checks
│   ├── fixtures/            # Adversarial test payloads & mock pages
│   ├── datasets/            # Versioned evaluation query sets
│   ├── applications/        # Workflow harness configurations
│   ├── services/            # Mock servers (SSRF fixtures, DNS rebinding)
│   ├── logs/                # Isolated run logs
│   ├── reports/             # Generated test and evaluation summaries
│   ├── temporary/           # Ephemeral DBs, cache, and scratch files
│   └── security/            # Security test configurations
├── adapters/
│   ├── common_interface/   # ResearchProvider ABC and standardized schemas
│   ├── weblens_adapter/     # WebLens local MCP adapter (independent & assisted)
│   └── tavily_adapter/      # Official Tavily REST API adapter
├── evaluations/             # Evaluation suites (search, latency, quality, etc.)
├── security_lab/            # Defensive test suites (SSRF, injection, auth, etc.)
└── reports/                 # Cross-platform comparison reports
```

---

## 2. Isolation Guarantees

### A. Data & File Isolation
- **Storage Boundaries**: SQLite databases and cache entries are scoped exclusively to `weblens-lab/sandbox/temporary/`.
- **Teardown Safety**: The cleanup handler verifies path containment before unlinking files, preventing modification or deletion of root repository files.
- **Path Traversal Containment**: Directory access attempts escaping `weblens-lab/` are rejected.

### B. Network & SSRF Boundaries
- **Egress Policy**: Outbound HTTP requests from the sandbox pass through `DestinationPolicy`.
- **Blocked Ranges**: All IPv4 loopback (`127.0.0.0/8`), private RFC1918 ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local metadata (`169.254.169.254`), and IPv6 (`::1`, `fc00::/7`, `fe80::/10`) are blocked at connection time and after each redirect.
- **DNS Rebinding Guard**: Hostnames resolving to private IPs are intercepted and blocked before connection.

### C. Resource Boundaries
- **Container Limits**: Defined in `docker-compose.yml`:
  - CPU: 2.0 cores
  - Memory: 2048 MB limit
  - Cache: 128 MB logical payload cap (`WEBLENS_CACHE_MAX_BYTES=134217728`)
  - Concurrency: Max 8 simultaneous connections, per-host cap of 2.

### D. Secret Management
- **Zero Hardcoded Keys**: Real credentials are read strictly from process environment (`TAVILY_API_KEY`).
- **Git Protection**: `.gitignore` strictly ignores `.env`, `.env*`, and `weblens-lab/sandbox/.env`.
- **Masking**: All reports and log files redact credential patterns (`tvly-...`).

