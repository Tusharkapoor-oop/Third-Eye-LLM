# WebLens on Cloudflare Containers

This directory contains the Cloudflare deployment surface for WebLens. The
Python MCP server runs in a Cloudflare Container; a small Worker validates
callers, applies stable tenant affinity, and forwards MCP HTTP traffic.

This is a deployment-ready configuration, not a claim that a paid deployment or
a live production acceptance run has already happened. Cloudflare Containers
require a Workers Paid plan.

## What gets deployed

- `Dockerfile.cloudflare` — lean `linux/amd64` image with the canonical
  `weblens` package, the full MCP profile, and no browser/Redis/hybrid extras.
- `wrangler.jsonc` — one `WebLensContainer` Durable Object class, three fixed
  container instances, `standard-1` (4 GiB / 1/2 vCPU) by default.
- `cloudflare/worker.ts` — edge authentication, CORS preflight, `/healthz`,
  `/readyz`, and `/mcp` forwarding.
- `package.json` / `tsconfig.json` — Wrangler and TypeScript tooling.

The container is not exposed directly. The Worker is the only public surface.

## Prerequisites

- Cloudflare account on the Workers Paid plan
- Node.js 20+ and npm
- Docker (or another Docker-compatible engine) for local container builds
- `wrangler` login

## First deploy

From the repository root:

```bash
npm install
npx wrangler login

# The token clients will send as `Authorization: Bearer ...` or `X-API-Key`.
# Generate one, for example: openssl rand -hex 32
npx wrangler secret put WEBLENS_API_KEY

# Required for the default Cloudflare provider order to use Tavily.
npx wrangler secret put TAVILY_API_KEY

# Optional providers:
# npx wrangler secret put BRAVE_SEARCH_API_KEY
# npx wrangler secret put SEARXNG_URL

npm run deploy
```

For multiple tenants, set `WEBLENS_API_KEYS` instead of a single key. It accepts
a JSON object such as `{"tenant-a":"key-a","tenant-b":"key-b"}` or
`tenant-a=key-a,tenant-b=key-b`. The same value must be used at the edge and in
the container so the container can attach the tenant identity:

```bash
npx wrangler secret put WEBLENS_API_KEYS
```

If `WEBLENS_API_KEY` is absent, the Worker still validates `WEBLENS_API_KEYS`;
do not leave both unset because `/mcp` will fail closed with HTTP 503.

## Verify

```bash
curl -fsS https://weblens-edge.<your-subdomain>.workers.dev/healthz
curl -fsS https://weblens-edge.<your-subdomain>.workers.dev/readyz
```

`/readyz` starts instance 0 and asks the container for `/healthz`. A cold start
can take longer than a warm request.

MCP client configuration:

```json
{
  "mcpServers": {
    "weblens": {
      "url": "https://weblens-edge.<your-subdomain>.workers.dev/mcp",
      "headers": {
        "Authorization": "Bearer <WEBLENS_API_KEY>"
      }
    }
  }
}
```

## Local development

```bash
npm install
cp .dev.vars.example .dev.vars
# fill in a local token and provider keys, then:
npm run dev
```

Wrangler serves the Worker at `http://localhost:8787` and starts the container
through Docker. Do not put real secrets in `wrangler.jsonc` or commit
`.dev.vars`.

> **Windows note:** Wrangler's local container development mode is not
> supported on Windows. Use WSL for `npm run dev`, or validate the Worker with
> `npm run check` and the container with a direct `docker run` as shown above.
> `wrangler deploy` and `wrangler deploy --dry-run` do work from Windows.

## Configuration

| Binding | Purpose |
| --- | --- |
| `WEBLENS_API_KEY` | Secret. Single-client token validated at the edge and by the container. |
| `WEBLENS_API_KEYS` | Secret. Multi-tenant token map validated at the edge and by the container. |
| `TAVILY_API_KEY` | Secret. Passed to the container as an unprefixed provider key. |
| `BRAVE_SEARCH_API_KEY` | Optional secret. |
| `SEARXNG_URL` | Optional secret. |
| `WEBLENS_INSTANCE_COUNT` | Var. Fixed pool size, default `3`, clamped to 1–10. |
| `WEBLENS_CONTAINER_INSTANCE` | Var. `lite`, `basic`, or `standard-1` … `standard-4`. |
| `WEBLENS_MCP_PROFILE` | Var. Defaults to `full`; `core` or `research` reduce tools. |
| `WEBLENS_SEARCH_PROVIDERS` | Var. Defaults to `tavily,mwmbl,wikipedia,bing,yahoo`. |
| `WEBLENS_SUPPLEMENT_PROVIDERS` | Var. Defaults to `stackexchange`. Fills empty slots only when the primary window is thin; it cannot displace a primary hit. |
| `WEBLENS_FUSE_SOFT_TIMEOUT_S` | Var. Defaults to `2.0`. Hosted fast-path deadline; only fires once Tavily fills the visible window. `0` waits for every provider. |
| `WEBLENS_FUSE_GRACE_S` | Var. Defaults to `0.25`. Extra wait for in-flight providers before the fast path cancels the rest. |
| `WEBLENS_FUSE_EARLY_MIN_EXTRA` | Var. Defaults to `0`. Extra distinct Tavily results required beyond `k`. |
| `WEBLENS_FUSE_EARLY_MIN_DOMAINS` | Var. Defaults to `3`. Minimum registrable domains in the Tavily subset. |

Secrets are read by the Durable Object at container start. Updating a secret
does not change the environment of an already-running container; Cloudflare
applies the new value on the next start. Redeploy or let the instance sleep
before relying on a rotated secret.

## Architecture and limits

- **Fixed pool, not autoscaling.** Three named instances are addressed by the
  Worker. Increase `WEBLENS_INSTANCE_COUNT` only when the per-instance cache and
  per-tenant state model is acceptable for your workload.
- **Tenant affinity, not shared state.** A hash of the presented token keeps one
  tenant on one instance. Container replacement or scale-out still means the
  local SQLite cache and stateful-tool state are not a durable shared store.
  Use external storage if you need cross-instance durability.
- **Ephemeral cache.** `WEBLENS_CACHE_DIR=/tmp/weblens` is container-local and
  disappears with the instance. The default SQLite cache is intentionally not a
  distributed cache.
- **No browser extra.** The Cloudflare image does not install Playwright. Tools
  that require a browser degrade; use the browser-enabled container target if
  you need JS rendering.
- **Tavily is paid.** It is first in the Cloudflare provider chain because the
  deployment supplies a key. Remove it from `WEBLENS_SEARCH_PROVIDERS` if you do
  not want paid provider calls; the free fallbacks remain available.
- **Per-instance rate limiting.** WebLens' limiter is not a global distributed
  quota. Add a Cloudflare WAF rate-limiting rule for `/mcp` if you need an edge
  quota before requests reach a container.
- **No LLM in the MCP profile.** The deployment is the deterministic WebLens
  server. It does not turn the evidence engine into an LLM acceptance claim.

## Operations

```bash
npx wrangler tail
npx wrangler containers list
npx wrangler rollback
```

The container health endpoint is `/healthz`; the Worker readiness endpoint is
`/readyz`. Cloudflare's own health check for the container image is defined in
`Dockerfile.cloudflare`.

## Validation performed locally

- `npm run check` — TypeScript type-check of the Worker (passes).
- `npm run deploy:dry-run` — Wrangler builds the container image, bundles the
  Worker, and validates every binding. Last run 2026-11-09: exit 0, image built,
  `WEBLENS_FUSE_*` bindings present, no deployment performed.
- `docker build -f Dockerfile.cloudflare -t weblens-cloudflare:test .` — image
  build and Python import smoke test.

A local build and dry run are not a substitute for a live deployment, a paid
Tavily run at scale, or the separate V10/MCP/Cloud Run acceptance gates.
