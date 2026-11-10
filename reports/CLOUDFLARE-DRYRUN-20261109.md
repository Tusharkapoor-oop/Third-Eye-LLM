# Cloudflare dry run — 2026-11-09

Local validation only. **No deployment was performed.**

## Commands

```powershell
npm run check          # tsc --noEmit
npm run deploy:dry-run # wrangler deploy --dry-run --outdir dist
```

## Result

- `npm run check`: exit 0.
- `npm run deploy:dry-run`: exit 0. Wrangler built the container image, bundled
  the Worker, validated the bindings, and exited without uploading.

Relevant tail of the dry-run log:

```text
env.WEBLENS_MCP_PROFILE ("full")                                              Environment Variable
env.WEBLENS_SEARCH_PROVIDERS ("tavily,mwmbl,wikipedia,bing,yahoo")            Environment Variable
env.WEBLENS_SUPPLEMENT_PROVIDERS ("stackexchange")                            Environment Variable
env.WEBLENS_FUSE_SOFT_TIMEOUT_S ("2.0")                                       Environment Variable
env.WEBLENS_FUSE_GRACE_S ("0.25")                                             Environment Variable
env.WEBLENS_FUSE_EARLY_MIN_EXTRA ("0")                                        Environment Variable
env.WEBLENS_FUSE_EARLY_MIN_DOMAINS ("3")                                      Environment Variable
env.WEBLENS_LOG_LEVEL ("INFO")                                                Environment Variable

The following containers are available:
- WebLensContainer (durable_object)

--dry-run: exiting now.
```

## Not proven by this dry run

- Workers Paid plan status and account access.
- Real secrets, a live Tavily key at scale, or a production acceptance run.
- Worker latency, container cold starts, or tenant isolation under real traffic.
- `wrangler dev` on Windows (unsupported locally; use WSL).
