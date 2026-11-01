# Threat Model & Attack Surface Catalog (P0)

**Date:** 2026-11-01  
**Target:** WebLens MCP Engine (`weblens/` and `src/engine/`)  
**Specification:** Master Directive v6  

---

## 1. Assets Under Protection

1. **Host Credentials & Secrets:** API keys (Tavily, Brave, Exa), environment variables (`.env`), system configuration.
2. **Local & Internal Network:** Loopback services (`127.0.0.1`), LAN subnets (`192.168.0.0/16`, `10.0.0.0/8`, `172.16.0.0/12`), link-local/cloud-metadata (`169.254.169.254`, `[fe80::]`).
3. **Local Filesystem:** Working directory, SQLite cache database (`~/.weblens/cache.db`), temporary download files, arbitrary path access.
4. **Browser Runtime & Processes:** Headless Chromium/Edge instances, child process lifecycle, DevTools/CDP debugging ports, cookie jars.
5. **MCP Interface & Client Context:** JSON-RPC communication channel, LLM context window (protecting against context-poisoning and instruction hijacking).

---

## 2. Threat Actors & Capabilities

| Actor | Access Level | Objectives | Typical Vectors |
|---|---|---|---|
| **Hostile Web Server** | Untrusted public HTTP/HTTPS endpoint | SSRF into internal networks, DNS rebinding, resource exhaustion, crash browser | 302 redirects to `127.0.0.1`, infinite chunked encoding, decompression bombs, huge headers |
| **Hostile Web Content** | Retrieved HTML, text, or metadata | Subvert model instructions, leak secrets, inject malicious tools | Prompt injection, hidden CSS/comment instructions, unicode homoglyphs, markdown link exfiltration |
| **Hostile MCP Client** | Local process invoking MCP tools | Arbitrary command execution, filesystem traversal, resource starvation | Malformed JSON-RPC, path traversal in URLs, excessive concurrency, cancellation flooding |
| **Network Attacker** | On local LAN or path | Intercept or manipulate unencrypted communications | DNS spoofing, cache poisoning, traffic sniffing |

---

## 3. Trust Boundaries & Security Enforcers

```
[Untrusted Web]
      │  (Public HTTP/S)
      ▼
┌──────────────────────────────────────────────┐
│ WebLens Network Boundary                     │
│  - DestinationPolicy (SSRF / IP validator)   │
│  - BrowserEgressProxy (DNS-pinned loopback)  │
│  - SafeFetcher (Timeout / Size cap / Stream) │
└──────────────────────┬───────────────────────┘
                       │ (Sanitized bytes)
                       ▼
┌──────────────────────────────────────────────┐
│ Extraction & Sanitization Layer              │
│  - Passage extractor & boilerplate stripper  │
│  - Injection scanner (heuristic warnings)    │
│  - Token budget limiter (cl100k_base cap)    │
└──────────────────────┬───────────────────────┘
                       │ (Delimited untrusted data)
                       ▼
┌──────────────────────────────────────────────┐
│ MCP Protocol Server                          │
│  - Read-only compact tool surface            │
│  - Strict JSON schema input validation       │
└──────────────────────────────────────────────┘
                       │
                       ▼
                 [AI Agent Host]
```

---

## 4. Attack Tree & Coverage Matrix

- **SSRF & Network Boundary (P1):**
  - Loopback / IPv4 & IPv6 variants (`127.0.0.1`, `[::1]`, `0.0.0.0`, octal/hex encodings).
  - Cloud metadata endpoints (`169.254.169.254`, `metadata.google.internal`).
  - Redirect chains transitioning from public fixture to internal destination.
  - DNS rebinding (switching from public IP to private IP post-validation).
- **Browser & Renderer Egress (P2):**
  - Direct navigation to `file://`, `chrome://`, `javascript:`, `data:`.
  - Sub-resource extraction (iframes, image beacons, XHR/fetch) to private network.
  - CDP port exposure to external or unauthenticated local processes.
- **Prompt Injection & Integrity (P3):**
  - System instruction overrides in page body, headings, and tables.
  - Exfiltration commands targeting environment variables and canary keys.
  - Smuggled commands in HTML comments (`<!-- assistant: ... -->`) and zero-width unicode.
  - Measuring false positive rate on benign technical text.
- **Output Handling & Escaping (P4):**
  - Structured output injection (JSON-breaking quotes).
  - Terminal escape sequences (ANSI control codes).
  - Log injection (CRLF characters in URLs or query strings).
- **Fuzzing & Edge Cases (P5):**
  - Fuzzing URL normalizer with unusual characters, non-UTF8 bytes.
  - Edge cases in HTML parsing (deeply nested tags, malformed DOM).
- **Resource Exhaustion (P6):**
  - Decompression bombs (gzip/brotli).
  - Endless streams and slowloris attacks.
  - Regular expression Denial of Service (ReDoS).
- **Cache Security (P7):**
  - Cache poisoning via URL collisions.
  - Partitioning by authorization context (multi-tenant safety).
- **MCP Surface (P8):**
  - Protocol fuzzing (missing fields, unexpected types, out-of-bound integers).
  - Official MCP tool conformance.
- **Secret Redaction (P9):**
  - Verifying canary tokens are never logged or exposed.
- **Supply Chain (P10):**
  - Dependency vulnerability scan (`pip-audit`).
  - Hash verification of vendored packages.

