# ADR-005: Socket Connect-Time SSRF & DNS Rebinding Mitigation

## Status
Accepted

## Context
AI agents equipped with crawling or URL extraction capabilities can be manipulated by malicious prompts or poisoned web links to access internal local network infrastructure (e.g., `http://127.0.0.1:11434`, `http://192.168.1.1`, or `http://169.254.169.254`). Simple regex or string checks on the hostname are susceptible to DNS rebinding, TOCTOU race conditions, IP obfuscation (decimal, hex, octal, or IPv6-mapped IPv4), and HTTP 302 redirects.

## Decision
1. Resolve hostnames to canonical IP addresses using `socket.getaddrinfo()` before establishing connections.
2. Evaluate resolved IPs against blacklisted CIDR ranges (RFC 1918, loopback, link-local / cloud IMDS, multicast, reserved).
3. Enforce validation at socket connection time via custom HTTP transport hooks, preventing DNS rebinding between pre-flight check and TCP handshake.
4. Disable automatic client-side redirect following; each redirect hop is intercepted and re-validated.
5. Enforce a 10 MB streaming byte cap to mitigate gzip and content bombs.

## Consequences
- **Positive**: Complete defense against SSRF, internal port scanning, cloud credential theft, and DNS rebinding attacks.
- **Negative**: Legitimate scraping of private intranet URLs is blocked unless explicitly overridden by configuration (`WEBINTEL_ALLOW_PRIVATE_NET=1`).
