# WebLens loop — STATUS

**Updated:** 2026-11-10 06:45 IST
**HEAD:** `4c99e93` — **all work below is uncommitted working-tree state.**

---

## One-line answer

**Five model families audited this work and found 6 real defects — including one in
my own security code and one that invalidated my own headline measurement. All 6
are fixed with regression tests proven to fail on the broken build. The product is
green again, but it is still not committed and still loses on latency.**

---

## What the five models actually found

Each ran on a distinct area. I verified every claim at source before acting on it;
two of the findings contradicted things I had previously reported.

| Model | Area | What it found |
|---|---|---|
| **GLM 5.3** | security | 3 findings (below) — plus 4 areas proven to hold under live attack |
| **Kimi K2.7 Code** | search correctness | **2 × P0** in the early-stop guard, plus 8 more |
| **Kimi K2.6** | re-derivation | headline **CONFIRMED** using its own independent code |
| **Qwen 3.8 27B** | test quality | ~2% of tests proven to be theatre by breaking the implementation |
| **Gemma 4 31B** | documentation honesty | numbers cited no source → this file was rewritten |

Full record: `evidence/raw/cycle5_multi_model_findings.json`.

---

## Defects found and fixed

### 1. P0 — the diversity floor was dead code *(found by Kimi K2.7 Code)*

`_early_pool_is_enough` passed a **full URL** to `registrable_domain()`, which
expects a **host**. Every path segment became its own "domain", so six pages on
**one host** — or six URL spellings of **one document** — satisfied a 3-domain
floor. The guard then certified a single-source pool as deep and diverse,
cancelled healthy slow providers, and `diversify(strict=True)` shrank the window
below `k`.

Fixed: `registrable_domain(host_of(h.url))`. Regression test
`test_fuse_does_not_early_stop_on_a_single_domain_pool`, **Gate-1 proven** (it
fails on the mutant with `early_stopped=True`).

This matters because it is the guard that was supposed to make the early stop
*quality-safe* — my cycle-2 report leaned on it.

### 2. P0 — the recall pass bypassed the cache guard *(Kimi K2.7 Code)*

The `query_expanded` recall pass runs a second `_fuse` into a throwaway outcome;
its `early_stopped` flag was discarded. A timing-dependent partial result from
the recall pass was therefore cached for the full TTL. Fixed by propagating the
flag.

### 3. Security — cloud-metadata IPs reachable via the private-network opt-in *(I found this while strengthening a test Qwen flagged)*

`check_ip` returned early when `allow_private_networks=True`, **before** the
`BLOCKED_IPS` metadata check. So `169.254.169.254`, `168.63.129.16` and
`100.100.100.200` — the addresses whose entire purpose is to hand out instance
credentials — were reachable with that opt-in on. Fixed by moving the metadata
blocklist above the early return.

### 4–6. Test theatre, proven then repaired

Qwen proved these pass against deliberately broken implementations:
zero-assertion tests, a security-header test that never inspected headers, and a
**10-tool forwarding test that checked no argument at all**. Each now asserts real
behaviour; the forwarding test is **Gate-1 proven** to fail when a stub ignores
its input.

Also fixed a suite-isolation bug: `test_browser_renders_javascript_shell` skips
alone but **failed** in the full suite, because its environment guard only handled
raised launch exceptions, not an `error`-status payload.

---

## A correction to my own headline measurement

Kimi noticed `auto_include_tavily=True` silently prepends Tavily whenever a key is
present. I checked my own harness — and it was guilty: `cycle1_final_latency.py`
called bare `WebLens()`, which read `TAVILY_API_KEY` from `.env`. **A measurement
labelled "keyless" was actually using Tavily.**

| | p50 | p95 |
|---|---|---|
| Previously reported ("keyless") | **739 ms** | 2062 ms |
| Actually keyless (corrected) | **1497.5 ms** | 3010 ms |

Evidence: `cycle5-keyless-latency-corrected`. The harness now pins
`tavily_api_key=None` + `auto_include_tavily=False` and **refuses to run** if
`tavily` appears in the chain.

**The honest consequence: p50 1497.5 ms sits barely under the 1500 ms gate.** I
previously reported a comfortable pass; the real margin is ~2.5 ms.

---

## Verified state (all measured after the fixes)

| Gate | Result |
|---|---|
| weblens suite | **796 tests, 0 fail, 0 err, 1 skip** |
| root suite | **366 tests, 0 fail, 5 skip** |
| coverage | **90.94%** (gate 90) |
| mypy | **0 issues, 55 files** |
| bandit `-ll` | **exit 0** |
| ruff check + format | **clean, 127 files** |
| canonical ↔ mirror | **byte-identical**, 55 modules |
| Gate 1 (mutations) | **3/3 caught** on the shipped protections; new tests individually proven |

---

## Still open — not fixed, and not claimed fixed

| # | Severity | Issue |
|---|---|---|
| F1 | MEDIUM | `SafeFetcher` forwards caller headers (`Authorization`, `X-Subscription-Token`) across a **cross-host redirect**. Real callers are Tavily and Brave. Confirmed by code reading at `net/client.py:236` + `:278-287`; my own end-to-end repro was blocked by DNS first, so I report it as a **code-read finding, not a reproduced one**. |
| F2 | MEDIUM | The Stack Exchange key is a URL query parameter, so the full URL — key included — lands in cache meta and `FetchError` text. |
| F3 | LOW | Default `allowed_hosts` has no port wildcard, so a real MCP client gets **421**; the documented workaround `*` disables DNS-rebinding protection. |

Also still true: **nothing is committed**, `evidence/` is untracked (68 files),
the held-out split is spent, the Tavily head-to-head is stale, and the keyless
chain remains ~7× slower than Tavily.

---

## What the models confirmed as genuinely correct

Worth stating plainly, because these were attacked and held:
SSRF connect-time pinning on both httpx pools; the browser egress proxy rejecting
12/12 hostile raw-socket cases; inbound MCP auth (401/421/403, timing-safe
compare, no scheme/NUL/duplicate-header bypass); fully parameterized SQL under
hostile FTS input; no live API key in any of 1067 shipped files; dual trees
byte-identical.

---

## Decisions still needed from you

1. **Rotate the Tavily key** exposed in `.env` and git history (`1c11ac3`,
   `a93e61b`).
2. **Commit the work** — until then none of it survives a clean checkout.
3. **Build a fresh held-out slice** before the next scored decision.
4. **Authorise** SearXNG / Docker pen-testing / a funded Tavily comparison.
