# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| `0.1.x` (current) | Yes |
| Older revisions | No — upgrade to the latest revision |

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

1. Use GitHub's **private vulnerability reporting** (Security → Advisories →
   Report a vulnerability) for this repository.
2. Include: affected component/file, reproduction steps or a proof-of-concept,
   impact, and the affected revision (`git rev-parse HEAD` or the Cloud Run
   revision name).
3. You can expect an initial acknowledgement within 3 business days. We will
   coordinate a disclosure date with you after a fix is available.

## Security posture (measured, not assumed)

The current code implements:

- **SSRF defence** — connection-time DNS resolution and IP pinning
  (`weblens/src/weblens/net/ssrf.py`), private/loopback/link-local/metadata
  rejection (IPv4 and IPv6), redirect re-validation on every hop, and a
  Chromium egress proxy for the browser path.
- **Transport authentication** — non-loopback listeners refuse to start without
  `WEBLENS_HTTP_TOKEN` or `WEBLENS_API_KEYS`; bearer/API-key comparison is
  constant-time.
- **Stateful-tool isolation** — `crawl2rag_index`, `crawl2rag_query` and
  `research_chat` are not registered on unauthenticated public listeners; all
  other tools are annotated `readOnlyHint=true`.
- **Rate limiting** — per-tenant token buckets with an LRU bound. By default
  the client IP is the real peer address and `X-Forwarded-For` is **ignored**;
  set `WEBLENS_TRUST_PROXY_HEADERS=true` only behind a trusted proxy that
  appends `X-Forwarded-For` (then the right-most hop is used).
- **Host/Origin validation** — the MCP HTTP transport enables DNS-rebinding
  protection by default with a loopback-only `WEBLENS_ALLOWED_HOSTS`; add your
  public hostnames explicitly, or `*` to opt out (not recommended).
  `WEBLENS_ALLOWED_ORIGINS` additionally constrains browser origins.
- **Outbound destination policy** — private/loopback/link-local/metadata ranges
  (including `169.254.169.254`, Azure `168.63.129.16`, Alibaba
  `100.100.100.200`) are always blocked; `WEBLENS_ALLOW_HOSTS` may narrow
  egress to an allowlist (empty = any public host).
- **robots.txt** — fail-open by default (a broken robots.txt does not stop a
  crawl, and the crawl reports a warning). Set `WEBLENS_ROBOTS_FAIL_CLOSED=true`
  to deny instead.
- **Output safety** — formula-injection defanging for spreadsheet output,
  prompt-injection heuristics, token budgets, and stable error envelopes.
- **Secret hygiene** — tracked-file secret scanning in CI
  (`tests/test_no_tracked_secrets.py`); env files are excluded from git and from
  Docker/Cloud Build contexts.

### Known residual risks

- A live API key exists in **git history** (see `evidence/SECURITY-FINDINGS.md`).
  Rotate the key and purge history if this repository is public.
- Cross-tenant isolation is **UNSUPPORTED** when multiple callers share one
  bearer token: stateful tools share one tenant identity per token.
- Prompt-injection detection is an advisory heuristic, not a security boundary;
  treat retrieved web content as untrusted data.
- The public deployment is intentionally reachable at the IAM layer; application
  authentication is the enforced control, so the bearer token is the secret to
  protect.

## Secure deployment checklist

- [ ] Set `WEBLENS_HTTP_TOKEN` (32+ random bytes, e.g. `openssl rand -hex 32`)
      from a secret manager; never commit it.
- [ ] Never pass `--allow-insecure` in production.
- [ ] Keep `**/.env*` excluded from Docker/Cloud Build contexts.
- [ ] Set `WEBLENS_ALLOWED_HOSTS` to the real service hostnames.
- [ ] Only enable `WEBLENS_TRUST_PROXY_HEADERS` behind a trusted proxy.
- [ ] Keep `WEBLENS_ALLOW_HOSTS` empty unless you need an egress allowlist.
- [ ] Decide `WEBLENS_ROBOTS_FAIL_CLOSED` for your crawl policy.
- [ ] Run the local security suites before deploying:
      `pytest tests/test_security.py tests/test_ssrf_penetration.py weblens/tests/test_ssrf.py`
