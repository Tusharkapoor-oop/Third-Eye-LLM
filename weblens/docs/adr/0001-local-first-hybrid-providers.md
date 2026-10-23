# ADR 0001: Local-first service with keyless-default, pluggable providers

- Status: Accepted
- Date: 2026-10-21

## Context

The target machine is a Windows 11 laptop with 16 GB RAM and a 6 GB RTX 3050.
The user wants fast web intelligence for local and cloud models, prefers free
and open-source components, and wants to avoid sending every query to a hosted
agent-search vendor. Hosted search APIs are more reliable but require keys,
accounts, quotas, and trust.

## Decision

Build a local Python service with a provider router. The default chain is
`ddg,mwmbl,wikipedia`, all keyless. Optional `brave`, `tavily`, and `searxng`
adapters can be enabled with configuration. The default mode is `fuse`: run
providers in parallel, merge and deduplicate, and record provider failures in
`fail` rather than hiding them.

Provider-specific deadlines are allowed because the keyless providers have very
different latency profiles. The fallback `provider_timeout_s` applies only to
providers without a measured deadline.

## Alternatives considered

- **Hosted-only (Tavily/Brave):** better reliability, but a key is mandatory and
  the free-tier claim could not be measured here.
- **Wikipedia-only:** reliable and keyless, but cannot answer most programming
  or current-fact queries.
- **Sequential fallback:** simpler, but one slow provider blocks all later
  providers; measured p95 was much worse.
- **SearXNG-only:** requires a trusted instance with JSON enabled; public
  instances are unreliable.

## Consequences

- The tool works offline-from-accounts but not offline-from-network.
- Result quality and latency vary with unofficial endpoints. This is documented
  rather than smoothed over.
- A user who needs reliability can add a key without changing the tool surface.
- The router must distinguish "provider failed" from "no evidence"; it does, via
  `partial`, `fail`, `warn`, and `gaps`.
- Re-evaluate the default when a keyed provider is measured on the same dataset.
