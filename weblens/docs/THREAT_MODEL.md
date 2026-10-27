# Threat model

Scope: WebLens running locally on a user's Windows 11 machine, called by an MCP
client, fetching arbitrary public HTTP(S) URLs. This is a security design review
with implemented controls and residual risks, not a certification.

## Assets

1. **Host network access** — loopback services, LAN devices, cloud metadata
   endpoints, the user's router.
2. **Local files and cache** — `~/.weblens/cache.sqlite3`, logs, optional `.env`
   credentials.
3. **Provider credentials** — optional Brave/Tavily keys and HTTP bearer token.
4. **Query privacy** — search terms and fetched URLs sent to third-party
   providers.
5. **Model context integrity** — retrieved text becomes model input and can try
   to steer the calling agent.
6. **Host resources** — CPU, memory, disk, sockets, and provider quotas.
7. **MCP client trust** — the server is read-only, but a malicious client could
   induce expensive crawls or scans.

## Trust boundaries

```text
untrusted web pages / redirects / DNS
        |
        v
SafeFetcher + DestinationPolicy  <-- untrusted URLs from the model
        |
        v
parser (lxml/trafilatura/PyMuPDF) --> compact evidence --> MCP client/model
        |
        v
local cache and config (semi-trusted local state)
```

The model and the MCP client are semi-trusted: they choose URLs and queries, but
must not be able to reach private networks or execute retrieved instructions.

## Threats and controls

### 1. SSRF and DNS rebinding

**Threat:** a URL or redirect targets `127.0.0.1`, RFC1918 space, link-local
metadata (`169.254.169.254`), IPv6 loopback, or a hostname that resolves to a
private address. DNS may alternate public/private answers.

**Controls:**

- `DestinationPolicy.check_hostname` blocks `localhost`, metadata hostnames,
  `.local`, `.internal`, `.home.arpa`, `.lan`, and configured deny suffixes.
- Literal IPs are parsed and validated in `check_hostname` as well as at
  connection time, covering the optional browser route handler.
- `resolve()` resolves the hostname once, rejects the **entire** hostname if any
  answer is non-public, and prefers IPv4.
- `SafeNetworkBackend.connect_tcp` opens the socket to the validated IP, not the
  hostname. TLS SNI and the HTTP `Host` header remain the original hostname
  because httpcore derives them from the request origin.
- The optional browser is launched behind a loopback egress proxy. For every
  HTTP request and HTTPS `CONNECT`, it resolves once, applies the same
  destination policy, and opens the upstream socket to the validated IP. The
  browser does not resolve the page destination itself.
- Only ports 80 and 443 are allowed unless private networks are explicitly
  enabled.
- `trust_env=False` prevents `HTTP_PROXY`/`HTTPS_PROXY` environment variables
  from silently rerouting requests.
- Redirects are resolved with `normalize_url` and rechecked on every hop;
  redirect loops and overlong chains are refused. The connection backend
  validates the redirect destination's IP again.

**Tests:** `tests/test_ssrf.py` covers loopback, RFC1918, link-local, CGNAT,
multicast, IPv6, IPv4-mapped IPv6, metadata names, allow/deny lists, port
filtering, mixed public/private DNS answers, and IPv4 preference.
`tests/test_urls.py` covers protocol/userinfo/redirect normalization.

**Residual:** a public IP can still host a service that proxies to private
resources; WebLens cannot detect that. IP validation is not a substitute for
egress firewall rules. The cache may retain a page fetched before a DNS change.

### 2. Redirect and URL-parser confusion

**Threat:** open redirects, `//host`, encoded hosts, backslashes, credentials in
authority, mixed schemes, or redirect loops reach a different destination than
the validator saw.

**Controls:** a single `normalize_url` path, explicit `http`/`https` allowlist,
no `file:`/`ftp:`/`gopher:`, redirect target normalization, per-hop hostname
check, and a hop cap. The effective URL is returned as `u`/`final_url`.

**Residual:** parser differentials between Python's URL parser and a downstream
tool are possible. Content is only fetched by WebLens, not handed to a second
fetcher.

### 3. Response-size and resource exhaustion

**Threat:** a server sends an endless body, a huge PDF, a sitemap with millions
of URLs, a crawl with unbounded links, or many concurrent requests.

**Controls:**

- `Content-Length` is checked before reading; the stream is also truncated at
  `max_response_bytes` (default 4 MB), with `truncated=true`.
- HTTP connect/read/pool timeouts; one retry for timeouts/transport errors.
- Global semaphore (8) and per-host semaphore (2).
- Crawl caps: 30 pages, depth 3, 8 sitemap fetches, at most 400 map entries.
- Research: at most 4 searches, 6 pages by default, 8 s fetch deadline per page,
  at most 8 findings and 3 per domain.
- Output budgets cap serialized JSON; the envelope is included.
- PDFs are limited to 40 pages.

**Residual:** decompression/parser CPU is not separately sandboxed. A malicious
page can still consume CPU within the timeouts. Run WebLens as an unprivileged
user and keep dependency updates current.

### 4. Prompt injection and instruction smuggling

**Threat:** a page contains "ignore previous instructions", role hijacks,
exfiltration requests, tool-invocation text, concealment instructions, invisible
Unicode, or HTML-comment instructions aimed at the model.

**Controls:**

- Retrieved content is explicitly labeled as data in the MCP `instructions` and
  in the README.
- `scan_injection` flags six pattern families and invisible Unicode in `inj`;
  `has_instruction_smuggling` flags suspicious HTML comments.
- The server exposes only read-only tools; it has no shell, file-write, email, or
  payment tool for an injected page to invoke.
- Findings are verbatim spans; the caller can inspect the source.

**Residual:** heuristics are easy to bypass and can false-positive. Flags are
advisory and do not sanitize text. The calling model must maintain the
data/instruction boundary; WebLens cannot enforce it.

### 5. Credential and query leakage

**Threat:** optional Brave/Tavily keys leak through logs, errors, cache, or
process listings; queries are sent to third-party providers.

**Controls:** keys are read from settings/environment, not returned in payloads;
`doctor` does not print keys; cache stores fetched pages, not provider keys;
provider errors are summarized. The default keyless path sends queries only to
DuckDuckGo, Mwmbl, and Wikipedia.

**Residual:** the cache is plain SQLite and is not encrypted. Queries are
inherently visible to the search provider. Do not use WebLens for secrets or
private intranet content without an explicit privacy review.

### 6. Local HTTP exposure

**Threat:** the optional HTTP transport is bound to `0.0.0.0` and becomes an open
proxy; a browser page performs a drive-by request to the local server.

**Controls:** loopback bind by default; non-loopback bind refused without a
bearer token or `--allow-insecure`; constant-time bearer comparison; no CORS
headers; read-only tools; no session data in stateless mode.

**Residual:** no TLS termination. In the tested loopback configuration the SDK
transport rejects a non-loopback `Host`/`Origin` with HTTP 421 (the official
conformance check passed 2/2), but this is not a substitute for TLS or a reverse
proxy with ACLs when exposed beyond loopback. A local malicious process can
still call a loopback server.

### 7. Cache integrity and disk growth

**Threat:** cache poisoning, path traversal through cache keys, stale pages
presented as current, or unbounded disk use.

**Controls:** cache keys are hashes of method/URL/body; values are compressed
blobs in a SQLite table, not filesystem paths; TTLs and ETag/Last-Modified
revalidation; `fetched_at` is returned with every passage; cache failures are
contained and never fail the request; `WEBLENS_CACHE_MAX_BYTES` evicts the
oldest rows when the logical payload exceeds the cap; `weblens cache stats` and
`weblens cache purge [--all]` operate only on the WebLens SQLite database.

**Residual:** the byte cap is logical payload, not a hard disk quota: SQLite
pages and the WAL are extra (`file_bytes` in `cache stats`). There is no
encryption; a compromised local account can read or edit the database. Delete
`~/.weblens/cache.sqlite3` to reset.

### 8. Optional browser path

**Threat:** even with request interception, Chromium can resolve DNS
independently of `SafeNetworkBackend`, so a public hostname can resolve to a
private address after the hostname check. A page can also issue subresource
requests, downloads, or popups.

**Controls:** disabled by default (`allow_browser=false`); the Playwright extra is
optional and is not installed by a plain `uv sync`; Chromium is launched behind a
loopback-only egress proxy. For every HTTP request and HTTPS `CONNECT`, the proxy
resolves the destination once, applies `DestinationPolicy`, and opens the
upstream socket to that validated IP; Chromium does not perform the page
destination lookup. Requests are still aborted for non-HTTP(S), non-web ports,
blocked hostnames, literal private IPs, images/media/fonts/stylesheets. QUIC,
DNS prefetch, and non-proxied WebRTC UDP are disabled; JavaScript only, service
workers blocked, downloads disabled, HTTPS errors not ignored, navigation
timeout. `tests/test_browser_proxy.py` covers forwarding, `CONNECT` tunnels, and
private-destination refusal. The live smoke test runs three fresh local
JavaScript-shell extractions and a public HTTPS `CONNECT` check; the private-URL
check fails before navigation as expected.

**Residual:** the proxy is an in-process Python component, not a network
namespace or an independent sandbox, and it has not been independently audited.
A Chromium compromise or a proxy bug could bypass these controls. While the
browser is running, another local process that can reach the ephemeral loopback
proxy port could use it, subject to the same destination policy. A public IP can
still proxy to private resources. Treat the browser as experimental and leave it
off unless you accept this residual risk.

### 9. MCP/transport abuse

**Threat:** malformed JSON-RPC, oversized arguments, invalid enums, repeated
expensive calls, or error-payload spoofing.

**Controls:** Pydantic validation at the tool boundary; `Literal` enums; result
caps; budget floors; `ToolError` only for transport/input failures; evidence
states remain successful calls; no tool can write to the host.

**Residual:** no rate limiter on MCP calls and no per-client quota. A local
client can consume provider quotas or CPU. Use OS-level resource limits if
untrusted local clients share the machine.

## Adversarial test map

| Area | Tests |
| --- | --- |
| Loopback/RFC1918/link-local/metadata | `tests/test_ssrf.py` |
| Mixed public/private DNS answers | `tests/test_ssrf.py` |
| Redirect loops, URL normalization | `tests/test_urls.py` |
| Size and budget enforcement | `tests/test_service.py`, `tests/test_tokens.py` |
| HTML prompt-injection flags | `tests/test_extract.py` |
| robots.txt and crawl caps | `tests/test_crawl.py` |
| Research refusal guards | `tests/test_research.py` |
| MCP error mapping and protocol flows | `tests/test_mcp.py` |
| Bearer authentication and non-loopback refusal | `tests/test_http_auth.py` |
| Browser proxy forwarding, CONNECT, private refusal | `tests/test_browser_proxy.py` |
| Browser JavaScript rendering (optional) | `tests/test_browser_optional.py` |

These tests are not a penetration test. No independent security audit was
performed.

## Deployment checklist

- Keep the default loopback/stdin configuration.
- Leave `WEBLENS_ALLOW_PRIVATE_NETWORKS=false`.
- Leave `WEBLENS_ALLOW_BROWSER=false` unless you accept the browser residual risk.
- Never commit `.env`; rotate any provider key that appears in logs.
- Run as an unprivileged user with a disposable cache directory.
- If HTTP is required remotely, terminate TLS in a reverse proxy and add network
  ACLs and rate limiting.
- Review retrieved `inj` flags; do not let a model follow page instructions.
