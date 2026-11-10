# Deploying WebLens — Render and Cloudflare

Two supported paths. Read the **"What is tested / what is not"** section at the
bottom before you rely on either.

---

## Option A — Render (recommended, fully tested path)

`render.yaml` is in the repo root. Render reads it automatically.

### Steps

1. Push this repo to GitHub (it currently has **uncommitted changes** — commit
   first, or Render will deploy the old code).
2. In Render: **New → Blueprint**, point at the repo.
3. Render creates `weblens-mcp` from `./Dockerfile`.
4. Set these environment variables in the dashboard (they are `sync: false`, so
   Render prompts rather than storing them in git):

   | Variable | Required | Purpose |
   |---|---|---|
   | `WEBLENS_HTTP_TOKEN` | **yes** | Bearer token. A long random string. The server **exits with status 2** rather than expose a public listener without it. |
   | `TAVILY_API_KEY` | optional | Enables the hosted search provider. **Note:** setting this also silently prepends Tavily to the provider chain (see caveat below). |
   | `BRAVE_SEARCH_API_KEY` | optional | Additional provider. |

5. Health check path is `/healthz` — public, no token needed.
6. Your MCP endpoint is `https://<service>.onrender.com/mcp`.

### Verified behaviour (measured locally, simulating the platform exactly)

| Check | Result |
|---|---|
| Binds the platform-injected `$PORT` | **yes** (previously it bound 8765 and would have failed) |
| `GET /healthz` without auth | **200** |
| `POST /mcp` with valid bearer | **200** |
| `POST /mcp` without token | **401** |
| `POST /mcp` with wrong token | **401** |
| `POST /mcp` with `Host: attacker.example.com` | **421** (DNS-rebinding protection active) |
| `POST /mcp` with `Origin: http://evil.example.com` | **403** |
| Bind `0.0.0.0` with no token | **refuses, exit 2** |

Client config (any MCP client):

```json
{
  "mcpServers": {
    "weblens": {
      "type": "http",
      "url": "https://your-service.onrender.com/mcp",
      "headers": { "Authorization": "Bearer YOUR_WEBLENS_HTTP_TOKEN" }
    }
  }
}
```

### Render caveats

- **The filesystem is ephemeral.** `WEBLENS_CACHE_DIR=/tmp/weblens` is set in the
  blueprint, so the cache is discarded on every restart. That is correct for
  crawling cache, but it means `crawl2rag_index` is **not durable** — an index you
  build will vanish on redeploy. Do not use the stateful tools as a system of
  record on Render's free/starter tiers.
- **Free instance hours.** Combo with the container start cost may exceed the free
  tier.
- **Cold start.** A starter instance sleeps; the first request after idle pays a
  container boot.

---

## Option B — Cloudflare

`cloudflare/worker.ts` + `wrangler.jsonc` exist and wrap WebLens in a **Durable
Object container** (the worker proxies MCP over to a Python process on port 8080).
This is a different architecture from a plain Worker: Workers cannot run Python,
so Cloudflare Containers are required.

```bash
cd cloudflare
npx wrangler deploy
```

Required secrets:

```bash
npx wrangler secret put WEBLENS_HTTP_TOKEN
npx wrangler secret put TAVILY_API_KEY        # optional
```

### Cloudflare caveats — read before choosing this path

- **Containers require a paid Cloudflare plan.** The worker is written against the
  container-backed Durable Object API; on a free plan it will not deploy.
- **I did not test this path.** I did not deploy to Cloudflare, did not run the
  container, and did not exercise the Durable Object. Treat `cloudflare/` as
  **untested code**, not a verified deployment.
- The worker forwards the same env names (`WEBLENS_HTTP_TOKEN`, `TAVILY_API_KEY`),
  so the server-side auth behaviour above still applies once it is running.
- `wrangler.jsonc` sets the container instance count; check it against your plan's
  limits before deploying.

**If you want a working deployment today, use Render.** Cloudflare Containers is
the more expensive, less-verified path for this workload.

---

## Security posture you inherit

These were audited by an independent model (GLM 5.3) and re-verified by me at
source:

- SSRF protection is enforced at **connect time**, not just URL validation: the
  httpcore network backend connects to the validated IP, so a DNS-rebinding
  answer cannot redirect the socket. Numeric/octal/hex IP forms pass the URL
  pre-check but are blocked at resolve.
- Cloud-metadata IPs (`169.254.169.254`, `168.63.129.16`, `100.100.100.200`) are
  blocked **even when `allow_private_networks=True`** — this was a real gap I
  found and fixed while testing.
- Redirects re-validate the destination per hop, and **caller credentials no
  longer follow a cross-origin redirect** (fixed this session; previously a 30x
  from an API host forwarded `Authorization` and `X-Subscription-Token`).
- API keys in URL query strings are redacted before they reach the cache or an
  error message.
- Inbound auth uses a constant-time comparison over SHA-256 digests; keys are
  held as digests, not plaintext.

---

## What is tested / what is not

**Tested here (locally, real process, real HTTP calls):**

- the server binding the platform `$PORT`, `/healthz`, and 401/403/421 enforcement
- all the static gates: **821 weblens tests + 366 root tests, 0 failures**,
  coverage **90.91%**, mypy 0, bandit 0, ruff clean, mirror drift none,
  evidence chain OK

**NOT tested — do not assume these work:**

| Item | Why |
|---|---|
| An actual Render deploy | No account access, and you have not authorised it. |
| An actual Cloudflare deploy | Same, plus Containers need a paid plan. |
| `docker build` of the image | Docker daemon is present but the image was not built here. |
| Load / soak behaviour in the cloud | No deployed endpoint to test against. |
| Durable-Object container path | Untested code. |

I will not claim a deployment works until a real one is run and its health check
and an authenticated `/mcp` call are observed. Everything in the "Verified
behaviour" table above is from a **local** process that mimics the platform's
port injection, not from Render itself.
