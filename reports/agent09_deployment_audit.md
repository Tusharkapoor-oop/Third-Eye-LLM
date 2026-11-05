# Agent 09: Cloud Run & Deployment Architecture Audit Report

## 1. Executive Summary & Audit Verdict

This audit provides an exhaustive evaluation of the containerization, deployment architecture, entrypoints, and Cloud Run security posture of the WebLens Model Context Protocol (MCP) server.

### Overall Verdict: CONDITIONAL PASS / HARDENING REQUIRED BEFORE PRODUCTION
- **Docker Containerization & Port Binding**: **PASS (FUNCTIONAL)** -- Container builds cleanly, exposes port 8080, and dynamically binds `$PORT` as required by Cloud Run.
- **SSRF Defense & Internal Network Isolation**: **PASS (ROBUST)** -- Verified 100% block rate on AWS metadata, GCP metadata, container loopback, IPv6 loopback, and local files.
- **Transport Security & HSTS**: **FAIL** -- Missing `Strict-Transport-Security` header on Cloud Run endpoint.
- **Edge Authentication & Authorization**: **FAIL** -- Endpoint is deployed unauthenticated (`--allow-unauthenticated=True`) with `--allow-insecure`, permitting arbitrary public callers to execute tools.
- **Rate Limiting & Abuse Defense**: **FAIL** -- No application-level or edge rate limiting is enforced; repeated burst calls are processed without HTTP 429.
- **CI/CD Pipeline**: **FAIL / MISSING** -- `cloudbuild.yaml` is absent; production releases have relied on ad-hoc, untracked local workstation deployments.
- **Process Lifecycle & Signal Forwarding**: **WARNING** -- Container entrypoint uses `sh -c` without `exec`, trapping `SIGTERM` and preventing graceful shutdown.

### Target Deployment Parameters
- **Target URL**: `https://weblens-16131012091.us-central1.run.app/mcp`
- **Active Service**: `weblens`
- **GCP Project**: `sewasetu-prod-2026`
- **Region**: `us-central1`
- **Active Deployed Revision**: `weblens-00006-l9h` (preceded by `weblens-00005-mzl` and `weblens-00003-l9q`)

---

## 2. Docker Containerization Audit (`Dockerfile`)

### 2.1 Base Image and Layer Composition
- **Base Image**: `python:3.11-slim` (minimal Debian-based runtime).
- **Package Installation**:
  ```dockerfile
  RUN apt-get update && apt-get install -y --no-install-recommends       build-essential       curl       sqlite3       && rm -rf /var/lib/apt/lists/*
  ```
- **Finding (Defect)**: `build-essential` (gcc, g++, make, libc-dev) is installed in the runtime layer and never removed. Because this is a single-stage build, compiler toolchains and development headers remain inside the production container image. This adds ~150MB of unnecessary bloat and substantially widens the attack surface in the event of arbitrary command execution.
- **Remediation**: Transition to a multi-stage Docker build where binary wheels are compiled in a `builder` stage, or purge `build-essential` in the same layer after `pip install`.

### 2.2 User Context and Privilege Separation
- **Current State**: No `USER` directive is declared in `Dockerfile`. The container runs as `root` (UID 0).
- **Finding (Security Risk)**: Running containers as `root` violates the principle of least privilege. Although Google Cloud Run executes containers within a sandboxed gVisor runtime, running as an unprivileged user mitigates container escape risks, prevents unauthorized filesystem writes, and conforms to CIS Docker Benchmark guidelines.
- **Remediation**: Declare `USER appuser` (UID 10001) with appropriate filesystem permissions.

### 2.3 Build Context and Artifact Ingestion
- **Copy Directives**:
  ```dockerfile
  COPY README.md pyproject.toml /app/
  COPY weblens/ /app/weblens/
  COPY src/ /app/src/
  COPY *.py /app/
  ```
- **Finding**: Copying wildcard `*.py` from the root directory injects root-level development, test, and evaluation scripts (`run_tavily_eval.py`, `quality_arena.py`, `server.py`, etc.) directly into `/app`.
- **Ignore Rules (`.dockerignore` and `.gcloudignore`)**:
  Both `.dockerignore` and `.gcloudignore` correctly exclude sensitive credential patterns:
  - `.env`, `.env*`, `*.key`, `*.pem`, `.git`, `.venv`, `reports`, `evidence`, `benchmarks`.
  - This prevents local `.env` secrets from leaking into the container image or Google Cloud Storage source staging buckets during source deploys.

### 2.4 Entrypoint Command and Signal Handling
- **Current Entrypoint**:
  ```dockerfile
  CMD ["sh", "-c", "python -m weblens.cli serve --http --host 0.0.0.0 --port ${PORT:-8080} --profile full --allow-insecure"]
  ```
- **Findings**:
  1. **Missing `exec`**: Wrapping the command in `sh -c` without `exec` spawns `/bin/sh` as PID 1 and Python as PID 2. In POSIX shells, `/bin/sh` does not automatically propagate `SIGTERM` signals to child processes. When Cloud Run scales down an instance or rolls out a new revision, it sends `SIGTERM` followed by a 10-second grace period before `SIGKILL`. Without `exec`, the Python process never receives `SIGTERM`, resulting in abrupt termination without running Starlette/Uvicorn shutdown hooks, closing SQLite connections, or flushing WAL logs.
  2. **Flag `--allow-insecure` Hardcoded**: This flag forces `TransportSecuritySettings(enable_dns_rebinding_protection=False, allowed_hosts=['*'], allowed_origins=['*'])` and allows unauthenticated HTTP requests on public interfaces.
  3. **Stateful Tool Degradation**: Because `--allow-insecure` is active without `--token`, `src/weblens/cli.py` line 176 computes `allow_stateful = False`. Consequently, `crawl2rag_index`, `crawl2rag_query`, and `research_chat` are omitted at runtime on Cloud Run.

### 2.5 Port Binding and Health Check Parity
- **Port Handling**:
  - `ENV PORT=8080`, `WEBLENS_HTTP_PORT=8080`, `EXPOSE 8080`.
  - The entrypoint uses `${PORT:-8080}`, dynamically binding to the port injected by Cloud Run. This adheres strictly to the Cloud Run container runtime contract.
- **Healthcheck**:
  ```dockerfile
  HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3       CMD curl -f http://localhost:${PORT:-8080}/ || exit 1
  ```
  - While Google Cloud Run ignores the Dockerfile `HEALTHCHECK` instruction (using its own TCP/HTTP startup probes), this directive ensures readiness validation in local Docker and Docker Compose workflows.
  - Both `GET /` and `GET /healthz` return HTTP 200 JSON with status `ok`.

---

## 3. CI/CD & Deployment Pipeline Audit (`cloudbuild.yaml`)

### 3.1 Status of `cloudbuild.yaml`
- **Verification Result**: **FILE NOT FOUND**.
- **Evidence**:
  - `Get-ChildItem` search and `git log --all --full-history -- cloudbuild.yaml` confirmed that `cloudbuild.yaml` has never existed in the repository.
- **Current Deployment Method**:
  - Review of `deploy_v10.log` and `deploy_v10b.log` demonstrates that deployments were executed manually from developer workstations via:
    ```powershell
    gcloud run deploy weblens --source . --region=us-central1 --project=sewasetu-prod-2026 --allow-unauthenticated=True --cpu=1 --memory=512Mi --port=8080 --timeout=300 --quiet
    ```
- **Deployment Risks Identified**:
  1. **No Automated Quality Gate**: Production releases bypass automated test execution, linting, and type verification.
  2. **Vulnerability Scanning Absence**: Container images are built directly via Cloud Run source build without automated CVE scanning or Software Bill of Materials (SBOM) generation.
  3. **Deployment Drift**: As documented in `reports/deployed-security/DEPLOYMENT_DRIFT_2026-11-02.md`, manual deployment previously resulted in revision `weblens-00003-l9q` lagging behind `main` (returning HTTP 404 on `/healthz` for multiple days).
  4. **Lack of SLSA Provenance**: Absence of an official Cloud Build trigger prevents Binary Authorization enforcement and build attestation.

---

## 4. Server Architecture & Entrypoint Divergence

### 4.1 Comparison: `server.py` vs `src/weblens/cli.py` & `src/weblens/mcp_server.py`

| Dimension | Legacy App (`server.py`) | Canonical App (`src/weblens/cli.py` & `mcp_server.py`) |
| :--- | :--- | :--- |
| **Identity & Version** | `MyWebEngine` v2.0.0 | `weblens` v0.1.0 |
| **Tool Surface** | 5 core tools (`web_search`, `extract_url`, `web_map`, `crawl_website`, `deep_research`) + optional extended browser tools | 10 modular tools (`web_search`, `extract_url`, `crawl_site`, `deep_research`, `company_research`, `market_research`, `market_portfolio`, `meeting_prep`, `sheets_enrich`, `tutorial_101`) |
| **Port Binding** | Hardcoded default to `CONFIG.port` (`8765`), no `$PORT` env interpolation | Dynamic CLI argument and environment binding (`--port ${PORT:-8080}`) |
| **Authentication** | None | Built-in `_BearerAuth` ASGI middleware |
| **Security Controls** | Relies on internal pipeline classes | Explicit SSRF `DestinationPolicy`, transport security, and tenant isolation |
| **Cloud Run Match** | Incompatible without manual flag mapping | Native compatibility via `serve --http` |

### 4.2 Entrypoint Path Clarification
- The audit prompt requested verification of `src/weblens/cli/server.py`.
- **Finding**: `src/weblens/cli/server.py` does not exist as a separate file. The canonical HTTP serving implementation is in `src/weblens/cli.py` (via `_serve_http` and the `serve` subcommand), backed by `src/weblens/mcp_server.py` (which builds the FastMCP / MCPServer instance).
- **Dockerfile Lineage**: Line 43 of `Dockerfile` correctly targets `python -m weblens.cli serve ...`, ensuring that only the canonical `weblens` package is executed in Cloud Run.

---

## 5. Cloud Run Security Posture Verification

The deployment security posture was audited against `reports/deployed-security/deployed_security_results_v2.json`, `CHECKPOINT_2026-11-02.md`, and live probe scripts in `weblens-lab/security_lab/`.

### 5.1 HTTP Strict Transport Security (HSTS)
- **Status**: **FAIL** (`deployed_hsts_header`: FAIL, severity: Low).
- **Analysis**:
  - The Cloud Run service endpoint terminates TLS via Google Front End (GFE) and correctly redirects HTTP to HTTPS (status 302).
  - However, GFE does not inject the `Strict-Transport-Security` header by default.
  - The application lacks ASGI/Starlette middleware to add `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`.
  - **Remediation**: Add HSTS header injection middleware in `_serve_http` in `src/weblens/cli.py`.

### 5.2 Edge Authentication & Authorization
- **Status**: **FAIL** (`deployed_unauthenticated_initialize`: FAIL, `deployed_bogus_bearer_accepted`: FAIL, severity: High).
- **Analysis**:
  - The service is deployed with `--allow-unauthenticated=True`.
  - The container runs with `--allow-insecure` and no `WEBLENS_HTTP_TOKEN`.
  - Consequently, any client on the public internet can call `POST /mcp` to initialize sessions and execute tools (`web_search`, `extract_url`, `deep_research`, etc.).
  - When `--token` is absent, the `_BearerAuth` middleware is bypassed completely, meaning even bogus or empty Bearer tokens return HTTP 200.
  - **Risk**: Open invocation leads to unbudgeted cost accumulation (Tavily, Gemini, and NVIDIA API usage) and potential denial of service.
  - **Remediation**: 
    1. For private internal agent communication: enforce Cloud Run IAM authentication (`--no-allow-unauthenticated`).
    2. For public web MCP clients: configure `WEBLENS_HTTP_TOKEN` via Google Secret Manager and omit `--allow-insecure`.

### 5.3 Rate Limiting & Abuse Prevention
- **Status**: **FAIL** (`deployed_rate_limit_metadata`: FAIL, severity: Medium).
- **Analysis**:
  - 20 rapid `tools/list` requests were executed without receiving an HTTP 429 Too Many Requests response.
  - No application-level rate limiting exists in `src/weblens/cli.py`.
  - Cloud Run auto-scaling settings (`--max-instances`) prevent runaway instance counts, but individual instances will process requests until saturation.
  - **Remediation**: Implement in-memory token-bucket or sliding-window rate limiting per IP / API key (e.g. `slowapi` or custom ASGI rate limiter).

### 5.4 SSRF & Network Egress Protection
- **Status**: **PASS (100% Robust)**.
- **Audit Results**:
  - Probing AWS metadata (`http://169.254.169.254/latest/meta-data/`): **BLOCKED** (`non-public destination: 169.254.169.254`).
  - Probing GCP metadata (`http://metadata.google.internal/computeMetadata/v1/`): **BLOCKED** (`blocked hostname: metadata.google.internal`).
  - Probing container loopback (`http://127.0.0.1:8080/admin`): **BLOCKED** (`non-public destination: 127.0.0.1`).
  - Probing IPv6 loopback (`http://[::1]:8080/`): **BLOCKED** (`non-public destination: ::1`).
  - Probing local file scheme (`file:///etc/passwd`): **BLOCKED** (`invalid URL`).
  - Public web control (`https://example.com/`): **PASS** (HTTP 200, clean passage extraction).
- **Implementation Validation**: `src/weblens/net/ssrf.py` enforces connection-time IP validation via `DestinationPolicy`. Hostnames are resolved to IP addresses before connection, private and non-routable IP ranges (RFC 1918, RFC 3927, RFC 4193, loopback) are rejected, and connections are pinned to the validated IP.

### 5.5 Stateful Tool Isolation & Multi-Tenancy
- **Status**: **PASS (Defensively Mitigated)**.
- **Analysis**:
  - The SQLite database backing Crawl2RAG and persistent chat is local to the container filesystem.
  - To prevent cross-tenant data leakage on an unauthenticated public endpoint, `src/weblens/cli.py` automatically disables stateful tools (`crawl2rag_index`, `crawl2rag_query`, `research_chat`) when unauthenticated.
  - `deployed_security_results_v2.json` recorded `deployed_cross_tenant_crawl2rag` as `UNSUPPORTED` because the tools are not registered, verifying that isolation by surface reduction is functional.

---

## 6. Environment Parity & Secret Management

### 6.1 Configuration Parity Analysis

| Variable | Local Development | Docker Compose | Cloud Run Production | Status |
| :--- | :--- | :--- | :--- | :--- |
| `PORT` | 8765 | 8080 | 8080 (injected) | Compliant |
| `WEBLENS_HTTP_HOST` | 127.0.0.1 | 0.0.0.0 | 0.0.0.0 | Compliant |
| `WEBLENS_MCP_PROFILE` | core / full | full | full | Compliant |
| `TAVILY_API_KEY` | In `.env` | `${TAVILY_API_KEY:-}` | Not injected in deploy logs (fallback active) | Parity Gap |
| `GEMINI_API_KEY` | In `.env` | `${GEMINI_API_KEY_1:-}` | Not injected in deploy logs (fallback active) | Parity Gap |
| `WEBLENS_HTTP_TOKEN` | Optional | Not set | Not set | Security Gap |

### 6.2 Secret Ingestion Practice
- In `deploy_v10.log`, the `gcloud run deploy` command was invoked without `--set-secrets` or `--set-env-vars`.
- While this prevented secrets from leaking in deploy logs or container images, the Cloud Run instance runs without API keys, forcing WebLens into fallback provider mode (`ddg`, `mwmbl`, `wikipedia`).
- **Remediation**: Use Google Cloud Secret Manager to inject API keys and authentication tokens directly into the Cloud Run container environment.

---

## 7. Hardening Recommendations & Implementation Blueprint

### Recommendation Priority Matrix

| Priority | Area | Recommendation | Implementation File / Command |
| :--- | :--- | :--- | :--- |
| **P0** | **Signal Handling** | Use `exec` in CMD to ensure clean `SIGTERM` shutdown | `Dockerfile` |
| **P0** | **Authentication** | Require bearer token authentication for public Cloud Run endpoint | `src/weblens/cli.py`, Secret Manager |
| **P1** | **Transport (HSTS)** | Add `Strict-Transport-Security` header middleware | `src/weblens/cli.py` |
| **P1** | **Container Security** | Drop root privileges (`USER appuser`) and multi-stage build | `Dockerfile` |
| **P1** | **CI/CD Automation** | Create version-controlled `cloudbuild.yaml` pipeline | `cloudbuild.yaml` |
| **P2** | **Rate Limiting** | Implement token-bucket rate limiting on `/mcp` | `src/weblens/cli.py` |
| **P2** | **Build Footprint** | Purge `build-essential` and remove dev scripts from container | `Dockerfile` |

---

### Implementation Artifact 1: Hardened `Dockerfile`

```dockerfile
# Stage 1: Build wheels with build-essential
FROM python:3.11-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends     build-essential     sqlite3     && rm -rf /var/lib/apt/lists/*

COPY README.md pyproject.toml /build/
COPY weblens/ /build/weblens/
COPY src/ /build/src/

RUN pip install --no-cache-dir --user ./weblens .

# Stage 2: Minimal runtime image without compilers
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PYTHONPATH=/app/src:/app     PORT=8080     WEBLENS_HTTP_HOST=0.0.0.0     WEBLENS_HTTP_PORT=8080     WEBLENS_MCP_PROFILE=full

WORKDIR /app

# Install curl and sqlite3 runtime only
RUN apt-get update && apt-get install -y --no-install-recommends     curl     sqlite3     && rm -rf /var/lib/apt/lists/*     && groupadd -g 10001 appgroup     && useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local
COPY --chown=appuser:appgroup src/ /app/src/
COPY --chown=appuser:appgroup README.md pyproject.toml /app/

ENV PATH=/home/appuser/.local/bin:$PATH

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3     CMD curl -f http://localhost:${PORT:-8080}/healthz || exit 1

# Use exec to ensure Python receives SIGTERM for graceful connection draining
CMD ["sh", "-c", "exec python -m weblens.cli serve --http --host 0.0.0.0 --port ${PORT:-8080} --profile full"]
```

---

### Implementation Artifact 2: Production `cloudbuild.yaml`

```yaml
steps:
  # 1. Run unit and security tests before build
  - name: 'python:3.11-slim'
    id: 'run-security-tests'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        pip install --no-cache-dir pytest pytest-asyncio httpx pydantic pydantic-settings
        pip install --no-cache-dir ./weblens .
        pytest tests/test_security.py tests/test_ssrf_penetration.py -v

  # 2. Build hardened container image via Docker
  - name: 'gcr.io/cloud-builders/docker'
    id: 'build-image'
    args:
      - 'build'
      - '-t'
      - 'us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/weblens:$COMMIT_SHA'
      - '-t'
      - 'us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/weblens:latest'
      - '.'

  # 3. Push image to Artifact Registry
  - name: 'gcr.io/cloud-builders/docker'
    id: 'push-image'
    args:
      - 'push'
      - '--all-tags'
      - 'us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/weblens'

  # 4. Deploy to Cloud Run with Secret Manager references and health checks
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    id: 'deploy-cloud-run'
    entrypoint: 'gcloud'
    args:
      - 'run'
      - 'deploy'
      - 'weblens'
      - '--image=us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/weblens:$COMMIT_SHA'
      - '--region=us-central1'
      - '--platform=managed'
      - '--cpu=1'
      - '--memory=512Mi'
      - '--timeout=300'
      - '--max-instances=10'
      - '--set-secrets=WEBLENS_HTTP_TOKEN=weblens-mcp-token:latest,TAVILY_API_KEY=tavily-api-key:latest'
      - '--quiet'

images:
  - 'us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/weblens:$COMMIT_SHA'
  - 'us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/weblens:latest'

options:
  logging: CLOUD_LOGGING_ONLY
```

---

### Implementation Artifact 3: Application Middleware Hardening (`src/weblens/cli.py`)

To enforce HSTS and security headers at the application level:
```python
class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"x-frame-options", b"DENY"))
                message["headers"] = headers
            await send(message)

        return await self.app(scope, receive, send_wrapper)
```
