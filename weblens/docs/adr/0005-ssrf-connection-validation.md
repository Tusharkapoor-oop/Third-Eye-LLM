# ADR 0005: Connection-time IP validation for every fetch

- Status: Accepted
- Date: 2026-10-21

## Context

Validating a URL's hostname before the request is not enough: DNS can return a
private address, redirects can change the destination, and a resolver can return
a mix of public and private answers. The optional browser makes the problem
harder because Chromium resolves DNS independently.

## Decision

Use a custom `httpcore` network backend (`SafeNetworkBackend`) for all HTTP
fetches:

1. `DestinationPolicy.check_hostname` enforces hostname blocklists/suffixes,
   allow/deny lists, and literal-IP validation.
2. `check_port` allows only 80/443 unless private networks are enabled.
3. `resolve()` resolves once, rejects the entire hostname if **any** answer is
   non-public, and prefers IPv4.
4. `connect_tcp` opens the socket to the validated IP. TLS SNI and the HTTP Host
   header remain the original hostname.
5. Redirects are normalized and rechecked on every hop; the next connection is
   validated again.
6. `trust_env=False` prevents environment proxies from bypassing the backend.
7. Response sizes are capped before and during streaming.

The optional browser checks hostnames, literal IPs, and ports in its request
route handler, but it does not pin DNS to a validated IP. It is disabled by
default and documented as having a larger residual SSRF risk.

## Alternatives considered

- **Pre-flight DNS check only:** vulnerable to rebinding between check and
  connect.
- **URL allowlist only:** unusable for open-web search.
- **OS firewall only:** necessary defense in depth, but not portable or
  testable in the unit suite.
- **Disable redirects entirely:** breaks too many real pages; revalidation is a
  better trade-off.

## Consequences

- The implementation depends on `httpcore` internals
  (`_transport._pool._network_backend`). The lockfile pins compatible versions;
  upgrades require re-running the SSRF tests.
- All fetches pay a DNS resolution; the HTTP cache avoids most repeats.
- IPv6-only public hosts work, but IPv4 is preferred for stability.
- Browser DNS rebinding remains a residual risk; see `THREAT_MODEL.md`.
