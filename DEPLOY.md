# Deploy WebLens to Cloudflare

Cloudflare only. The Render blueprint was removed.

---

## Read this first: two hard blockers

Neither is a code problem, and neither can be fixed from inside this environment.

### Blocker 1 — Docker Desktop is not running

```bash
docker info      # → failed to connect ... open //./pipe/dockerDesktopLinuxEngine
```

Cloudflare **Containers** build a `linux/amd64` image from `Dockerfile.cloudflare`.
Wrangler shells out to the Docker CLI to build it, and it refuses to even
dry-run without a working daemon. Start Docker Desktop and confirm:

```bash
docker info --format '{{.ServerVersion}}'
```

### Blocker 2 — wrangler is not authenticated

```bash
npx wrangler whoami      # → You are not authenticated. Please run `wrangler login`.
```

Authenticate once:

```bash
npx wrangler login
```

Then check the account can use **Containers**: this configuration deploys a
Durable Object–managed container, which requires a **paid Cloudflare plan**. The
free plan cannot run it.

---

## What is already prepared and verified

Everything below was checked in this session.

| Item | State |
|---|---|
| `wrangler.jsonc` | parses; `name: weblens-edge`, `main: cloudflare/worker.ts`, 1 container, 1 Durable Object, 10 vars |
| `cloudflare/worker.ts` | **`tsc --noEmit` passes**, 0 errors |
| `Dockerfile.cloudflare` | `$PORT` fixed, healthcheck port-agnostic, non-root UID 10001 |
| Worker auth logic | **11/11 behaviours correct** (see below) |
| Secrets | correctly **absent** from `vars`; must be set via `wrangler secret put` |

### Worker auth verified behaviourally

I extracted the worker's auth functions and exercised them directly:

| Case | Expected | Result |
|---|---|---|
| valid bearer | allow | OK |
| lowercase `bearer` | allow | OK |
| extra spaces | allow | OK |
| `X-API-Key` header | allow | OK |
| wrong token | deny | OK |
| no header | deny | OK |
| empty bearer | deny | OK |
| `Basic` scheme | deny | OK |
| token as prefix | deny | OK |
| token + suffix | deny | OK |
| **no keys configured** | deny (fail closed) | OK |

Implementation: SHA-256 digest comparison with a constant-time XOR loop, so
token length and content do not leak through timing. `/mcp` returns **503
`server_misconfigured`** if no key is set, rather than running open.

---

## Deploy steps

### 1. Start Docker Desktop, then authenticate

```bash
docker info --format '{{.ServerVersion}}'     # must print a version
npx wrangler login
npx wrangler whoami                            # must print your account
```

### 2. Set the required secret

`/mcp` will not serve without this — by design.

```bash
npx wrangler secret put WEBLENS_API_KEY
# paste a long random value when prompted
```

Optional extras:

```bash
npx wrangler secret put TAVILY_API_KEY
npx wrangler secret put BRAVE_SEARCH_API_KEY
```

Generate a strong token:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 3. Dry-run first (validates the container build without deploying)

```bash
npx wrangler deploy --dry-run --outdir dist
```

This now works only once Docker is running. If it succeeds, the image builds.

### 4. Deploy

```bash
npx wrangler deploy
```

Wrangler prints the worker URL, of the form
`https://weblens-edge.<your-subdomain>.workers.dev`.

### 5. Verify the deployment (do not skip)

```bash
# health — no auth needed
curl -s https://weblens-edge.<subdomain>.workers.dev/healthz

# readiness — 200 only when a key is configured AND the container answers
curl -s https://weblens-edge.<subdomain>.workers.dev/readyz

# auth must reject
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST https://weblens-edge.<subdomain>.workers.dev/mcp \
  -H 'content-type: application/json' -d '{}'          # expect 401

# MCP handshake with the token
curl -s -X POST https://weblens-edge.<subdomain>.workers.dev/mcp \
  -H "Authorization: Bearer $WEBLENS_API_KEY" \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}'

# tools/list — expect 14 tools, NOT 2
curl -s -X POST https://weblens-edge.<subdomain>.workers.dev/mcp \
  -H "Authorization: Bearer $WEBLENS_API_KEY" \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

**The `tools/list` check is the important one.** A correct WebLens deployment
returns **14** tools:

```
web_search, extract_url, crawl_site, deep_research, evidence_synthesis,
company_research, market_research, market_portfolio, meeting_prep,
sheets_enrich, crawl2rag_index, crawl2rag_query, research_chat, tutorial_101
```

If you see **`add`, `calculate`** you are looking at the Cloudflare calculator
template, not this project — that is exactly what happened with
`remote-mcp-server-authless.anyunkown8.workers.dev`.

### 6. Point your MCP client at it

```json
{
  "mcpServers": {
    "weblens": {
      "type": "http",
      "url": "https://weblens-edge.<subdomain>.workers.dev/mcp",
      "headers": { "Authorization": "Bearer YOUR_WEBLENS_API_KEY" }
    }
  }
}
```

---

## Architecture (why this is not a plain Worker)

Workers cannot run Python. `wrangler.jsonc` therefore declares:

- a **container** built from `Dockerfile.cloudflare`, running
  `python -m weblens.cli serve --http --host 0.0.0.0 --port $PORT --profile full`
- a **Durable Object** (`WebLensContainer`) that owns the container and forwards
  HTTP to its TCP port
- the **worker** (`export default`) that handles `/healthz`, `/`, `/readyz`,
  `/mcp`, enforces bearer auth, and routes each token to a stable instance
  (`affinityIndex`) so a tenant's session sticks to one container

Instance count is `WEBLENS_INSTANCE_COUNT` (default 3, max 10), size is
`WEBLENS_CONTAINER_INSTANCE` (`standard-1`).

---

## Known caveats

- **Paid plan required.** Containers are not on the free tier.
- **Cold start.** A container that has gone idle pays a boot cost on the first
  request. `INACTIVITY_TIMEOUT_MS` is 2 hours in the worker.
- **Container filesystem is ephemeral.** `WEBLENS_CACHE_DIR=/tmp/weblens`, so the
  cache resets on restart and `crawl2rag_index` is **not durable**. Do not treat
  the stateful tools as a system of record here.
- **`WEBLENS_SEARCH_PROVIDERS` in `wrangler.jsonc` lists `tavily` first.** If you
  do not set `TAVILY_API_KEY`, Tavily is marked unavailable and the keyless
  providers carry the load — correct, but expect higher latency.
- **Do not reuse an "authless" worker name.** WebLens enforces a token; deploying
  it onto the authless calculator's hostname would confuse clients and reuse a
  URL that is already public.

---

## What I did NOT verify

| Item | Why |
|---|---|
| An actual `wrangler deploy` | Not authenticated; you have not authorised a deploy. |
| The container image building | Docker Desktop is not running. |
| `wrangler deploy --dry-run` passing | Blocked by the same Docker requirement. |
| Live `/healthz`, `/readyz`, `/mcp` on Cloudflare | No deployment exists yet. |
| Container cold-start and concurrency behaviour | Needs a live deployment. |
| Load/soak behaviour | Same. |

The worker's **TypeScript compiles** and its **auth logic is proven correct**.
The container build and the live behaviour are **unverified** until Docker runs
and a real deploy happens.
