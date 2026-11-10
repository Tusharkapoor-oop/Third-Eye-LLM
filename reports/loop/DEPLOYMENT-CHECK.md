# Deployed endpoint check — conclusion

**Endpoint:** `https://remote-mcp-server-authless.anyunkown8.workers.dev/mcp`
**Checked:** 2026-11-10 14:30 IST
**Method:** normal MCP protocol requests only (`initialize`, `tools/list`,
`tools/call`). No attack traffic was sent to Cloudflare or any third party.

---

## Verdict: this endpoint is NOT WebLens

It is alive and healthy, but it is the **Cloudflare "remote-mcp-server-authless"
calculator template**, not this project.

### Evidence

| Probe | Result |
|---|---|
| `initialize` → `serverInfo.name` | **"Authless Calculator"**, version **1.0.0** |
| `initialize` → `protocolVersion` | `2025-06-18` (and it renegotiates to `2025-11-25` when asked for an unsupported one) |
| `tools/list` | **2 tools: `add`, `calculate`** |
| `tools/call calculate {multiply,7,6}` | returned **"42"** |
| `tools/call web_search` | **`-32602 Tool web_search not found`** |
| `tools/list` total | **2** — WebLens `full` profile has **14**: `web_search`, `extract_url`, `crawl_site`, `deep_research`, `evidence_synthesis`, `company_research`, `market_research`, `market_portfolio`, `meeting_prep`, `sheets_enrich`, `crawl2rag_index`, `crawl2rag_query`, `research_chat`, `tutorial_101` |
| `GET /mcp` | 405 with `Allow`-style CORS headers — correct for Streamable HTTP |
| `GET /` | 404 |
| Authentication | **none** — `tools/list` returns 200 with no token (hence "authless") |

The worker hostname is `remote-mcp-server-authless.<subdomain>.workers.dev`.
Our `wrangler.jsonc` declares `"name": "weblens-edge"`, which would deploy to
`weblens-edge.<subdomain>.workers.dev`. **Those are different workers.**

### What this means

- No WebLens code is running at that URL. Nothing about WebLens's search,
  extraction, crawling, research or MCP profile is being served there.
- The two suites, the security fixes, the deployment hardening and the
  `render.yaml` I added are **not** deployed anywhere. They are in the working
  tree, uncommitted.
- Therefore **no quality claim about WebLens can rest on this deployment.** The
  earlier gate results still describe the local tree, not this URL.

---

## The deployed calculator does pass basic protocol checks

For completeness, since you asked for a quality check of what *is* up:

| Check | Result |
|---|---|
| MCP handshake | 200, valid `event: message` SSE framing, `jsonrpc: "2.0"` |
| Version negotiation | falls back to a supported version instead of erroring |
| `tools/list` schema | valid JSON Schema draft 2020-12 with `required` fields |
| Missing required argument | handled: `isError: true` with "Invalid arguments for tool calculate: b: Invalid input: expected number, received undefined" |
| Divide by zero | handled: returns "Error: Cannot divide by zero" as text (not a crash) |
| Unknown method | correct `-32601 Method not found` |
| Unknown tool | correct `-32602 Tool not found` |
| CORS | `Access-Control-Allow-Origin: *`, methods and headers exposed |

So the template itself is competently implemented. It is simply **not this
project**.

---

## One security note about that endpoint

It is unauthenticated by design ("authless"). Anyone who learns the URL can call
`add`/`calculate`. For a calculator that is harmless. **Do not** repoint that
hostname at WebLens without adding `WEBLENS_HTTP_TOKEN` — WebLens's server
refuses to bind a public interface without a token (exit code 2), and that
protection is deliberate.

---


---

## Note: the local venv was emptied while this check ran

At 08:59 today (during the gap before this request) `.venv` was recreated empty —
`site-packages` contains **0** packages, so `pydantic` and every other dependency
are gone and the suites cannot run until it is reinstalled.

This does **not** affect the conclusions above: the endpoint check was done over
the network against Cloudflare with plain HTTP requests, and the tool-count claim
was re-verified **statically** from `weblens/src/weblens/mcp_server.py` (14 tool
names), not by importing anything.

To restore the local environment (needs network):

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ./weblens -e . pytest pytest-asyncio pytest-cov respx
```

I did not reinstall automatically: it needs a network install, which you have not
authorised, and another writer is active in this tree.

## Why WebLens is not deployed, and what would put it there

I did not deploy anything, and I could not have: **no Cloudflare credentials are
configured here** (`wrangler` is not installed; `npx wrangler` would need a login
this environment does not have), and you have not authorised a deployment.

WebLens on Cloudflare is also **not a simple worker upload**. `wrangler.jsonc`
declares a `containers` block with a `WebLensContainer` Durable Object, and
`cloudflare/worker.ts` proxies requests to a Python process on port 8080. So:

1. Cloudflare **Containers require a paid plan** — the free tier cannot run this.
2. The image must build (`Dockerfile.cloudflare`), which I have **not** built here.
3. Secrets must be set: `npx wrangler secret put WEBLENS_HTTP_TOKEN` (and
   optionally `TAVILY_API_KEY`).
4. Then `npx wrangler deploy` from the repo root.

Until 1–4 happen, there is no WebLens deployment to test.

### The faster path, already prepared

`render.yaml` in the repo root is a working blueprint for the **tested** path. I
verified locally (real server, real HTTP) that it binds `$PORT`, serves
`/healthz` 200, and enforces 200/401/401/421/403 on `/mcp`. That path needs only
a git push plus a Render account and one secret.

---

## Honest summary

You asked me to check the deployment. The deployment is real and healthy — but it
is **the wrong application**. I would rather report that plainly than test the
calculator and present the results as if they described WebLens.
