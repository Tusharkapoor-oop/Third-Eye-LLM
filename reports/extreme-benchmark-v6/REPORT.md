# WebLens evaluation — evidence report

Generated deterministically from the hash-chained ledger at `2026-11-01T13:47:21Z`.
Subject: the `weblens/` package at commit `902415d49f8d`, tree hash `8f6ac2df4f55d5797270952e1f80b56980f0d3f0ab3f2a571d93e1374839b765`,
ledger head `271bc8c3cc6b5b4ff81d80f86511f6106a3ee5f61818bc36a5716c5825125a53`.

Built by `tools/v6_build_report.py`; checked by `tools/v6_lint_report.py`. No number is typed by hand.

## Verdict: hard problems first

- **No Tavily comparison exists in this pass.** Tavily direct, Tavily via WebLens and the Tavily MCP
  server are NOT RUN. No quality, latency, token or cost winner is claimed. Neither "Tavily is better"
  nor the reverse can be concluded, because Tavily was not measured.
- **No live-web search was run.** Ranking quality, freshness and multilingual behaviour are NOT RUN;
  the pre-registered search gates are not evaluated.
- **No browser run.** Playwright is `absent` in the pinned environment. Browser egress,
  subresource blocking and the proxy are NOT RUN.
- **Fixture results are SIMULATED.** The SSRF matrix, injection corpus and extraction pages are local
  fixtures; they show how these code paths handle these fixtures, not live-web performance.
- **Samples are small.** Every proportion carries its n and a Wilson interval; anything below the
  pre-registered threshold says "too small to support a claim".
- **No independent audit and no human review.** The reporter is deterministic and the owner can verify
  it, but it was written by the executor whose work it describes.
- **Secret-store action needed.** `.env.example` has a non-empty Tavily key value that is not `tvly-`
  shaped and is not a placeholder (`no` / `no`).
  It is untracked and absent from history. Rotate it if it is live. Its value is never printed.

Established in this pass: the package suite result, the loopback SSRF matrix against the real fetcher,
injection-scanner calibration on a synthetic corpus, cache correctness, extraction fact recall on
fixtures, the MCP schema token count, tamper/mutation detection, and a secret-pattern scan.

## Systems under test

| System | Status | Reason |
|---|---|---|
| WebLens keyless | NOT RUN | No live search pass |
| WebLens + SearXNG | NOT RUN | Service unreachable; format change not authorized |
| WebLens + Tavily | NOT RUN | No credit-spend authorization |
| Tavily direct API | NOT RUN | No credit-spend authorization |
| Tavily MCP server | NOT RUN | No credit-spend authorization |
| root stack keyless | NOT RUN | Separate stack, out of scope |
| root stack + Tavily | NOT RUN | Out of scope; no spend authorization |
| later competitors | NOT RUN | Not installed or not authorized |

WebLens `0.1.0` from `C:\Users\ACER\Downloads\Broswer for ai agnets\weblens\src\weblens\__init__.py`, Python `3.14.0`, pytest `9.1.1`.

A second copy of the package exists at `src/weblens` and shadows the subject on the default import
path. Every experiment pins `weblens/src` and asserts the loaded module path.

## Environment and fairness

The ledger pins the full tree hash (`8f6ac2df4f55d5797270952e1f80b56980f0d3f0ab3f2a571d93e1374839b765`) for every run; the tree contains
pre-existing changes and this pass's tools. Fixture runs disable the cache or use a temporary
directory, so no cache state is shared between experiments.

## Datasets

| Dataset | Items | Hash | Status |
|---|---|---|---|
| `benchmarks/eval_dataset.json` | 50 | `846b4de9b38de945821ad56e5bd4fa2375af9640164b9e9c2de6bf8245e32df1` | Frozen, English-only lookup set |
| `benchmarks/eval_dataset_expanded.json` | 200 | `6130548dacb595da44a0973e66c4e3a44836846baf16a97ef1ca87664f2d065f` | Frozen, English-only |
| `benchmarks/tavily_paired_subset.json` | 40 | `ecb14a073716808d993f709ce4e78769bdc31c4009863b67fd68e3b504f767b8` | Frozen, paired run NOT RUN |

These sets do not meet the directive's scale requirements. No claim is made that they do.

## Package test suite

One pytest process ran `weblens/tests`: collected `163`, passed `162`,
failed `0`, skipped `1`; executed `162`; exit `0`.
A skipped test is not a pass. The root `tests/` suite and the root stack were not run.

Superseded attempts: EXP-001, EXP-004 and EXP-007 are superseded by their corrected b runs and are excluded from every aggregate; they remain in the ledger.

## SSRF and URL handling

The real `SafeFetcher` attempted `32` private, loopback, metadata, scheme and encoding
variants against a loopback fixture. `32` were blocked; the fixture received
`0` requests attributable to blocked variants. Block rate: `32/32 (100.0% [89.3%, 100.0%])`.

Guard is load-bearing: reached the fixture only with the guard disabled. This is the broken-build control.

NOT RUN: redirect-to-private and public-host DNS rebinding (no controllable public redirector was
exposed), browser subresources, and proxy CONNECT abuse. No claim is made for those classes.

## Prompt-injection scanner calibration

On `64` synthetic attack strings the scanner flagged `48`
(`48/64 (75.0% [63.2%, 84.0%])`). On `64` benign technical strings it flagged
`1` (`1/64 (1.6% [0.3%, 8.3%])`).

This is a flag, not a block and not an agent outcome. No agent loop was driven, so no attack-success
rate is claimed. The corpus is hand-written, not BIPIA, InjecAgent or AgentDojo.

## Cache correctness

`11` of `11` cases passed (`11/11 (100.0% [74.1%, 100.0%]) — n<30: too small to support a claim`): TTL expiry, key-field
separation, hostile-key SQL handling, logical-size eviction, restart persistence, corrupt-value
containment, disabled-cache behaviour, cross-key isolation.

Recorded limitation: eviction uses the documented logical payload cap; the SQLite file can exceed it.

## Extraction on local fixtures

Across `9` page types, `13` of `17`
planted facts were recovered (`13/17 (76.5% [52.7%, 90.4%]) — n<30: too small to support a claim`). `6` pages recovered every
fact; `3` recovered none.

| Page | Status | Planted facts recovered |
|---|---|---|
| static article | `ok` | `5/5 (100.0% [56.6%, 100.0%]) — n<30: too small to support a claim` |
| table | `ok` | `3/3 (100.0% [43.9%, 100.0%]) — n<30: too small to support a claim` |
| malformed HTML | `ok` | `1/1 (100.0% [20.7%, 100.0%]) — n<30: too small to support a claim` |
| non-UTF8 | `ok` | `0/2 (0.0% [0.0%, 65.8%]) — n<30: too small to support a claim` |
| large page | `ok` | `0/1 (0.0% [0.0%, 79.3%]) — n<30: too small to support a claim` |
| JavaScript shell | `error` | `0/1 (0.0% [0.0%, 79.3%]) — n<30: too small to support a claim` |
| injection page | `ok` | `1/1 (100.0% [20.7%, 100.0%]) — n<30: too small to support a claim` |
| PDF with text layer | `ok` | `2/2 (100.0% [34.2%, 100.0%]) — n<30: too small to support a claim` |
| blank PDF | `error` | not applicable |
| redirect | `ok` | `1/1 (100.0% [20.7%, 100.0%]) — n<30: too small to support a claim` |
| not found | `exception:FetchError` | not applicable |

Latency over fixture calls: `mean 118.14 ms [23.10, 293.65], median 26.98, p95 539.03 — n<30: too small to support a claim`.

Budget adherence: `3` of `3` calls stayed within the requested budget.

The JavaScript-shell result is the static-extraction loss: with the browser disabled the content is
not recovered. This is a no-browser limitation, not a browser measurement.

## Token surface

MCP schema: `732` tokens over `4` tools, tokenizer
`cl100k_base`, source `server.list_tools()`, status `measured`.

The pre-registration named `o200k_base`; the packaged tokenizer reports the value above. That
pre-registration statement was an assumption and was wrong; the measured value is reported and the
discrepancy is recorded, not silently corrected.

No competitor schema was measured. No token-efficiency ratio is claimed.

## Mutation and tamper checks

`4` of `4` mutations were detected (`4/4 (100.0% [51.0%, 100.0%]) — n<30: too small to support a claim`):
a ledger-record edit, a raw-artifact edit, and disabling the SSRF guard before running the package's
own SSRF tests. The clean copy verified first, so a broken verifier would not pass.

NOT RUN: token-cap removal, scanner removal, random-result and empty-result search mutations.

## Secrets

Scanned `454` text files (excluding `.env`). Tree pattern hits `3`;
git-history hits `0`. Redaction self-test: `passed`.

Pattern hits with paths only: `env_assignment at .env.example; tavily at tests/test_p9_canary_secrets.py; bearer at weblens/examples/clients/http-token.json`. These are an environment assignment in the
example file, a canary fixture in the test tree, and an example client token; none matched the live key.

This is a pattern scan, not a substitute for gitleaks or trufflehog, which are not installed.

## Latency, throughput and soak

NOT RUN. No live search, browser, concurrency ladder or sustained soak was executed. The only latency
figure above is fixture extraction.

## Tavily and competitor comparison

NOT RUN. Credit spend and service configuration were not authorized. Therefore there is no accuracy,
latency, token, cost or quality comparison, no winner, and no claim that WebLens is better or worse.

## Penetration coverage

| Class | Attempted | Result |
|---|---:|---|
| SSRF / URL handling (loopback fixture) | 32 | `32/32 (100.0% [89.3%, 100.0%])` blocked, `0` fixture requests |
| Prompt injection (scanner input) | 64 | `48/64 (75.0% [63.2%, 84.0%])` flagged |
| Cache poisoning / SQL / TTL | 11 | `11/11 (100.0% [74.1%, 100.0%]) — n<30: too small to support a claim` cases passed |
| Tamper and broken build | 4 | `4/4 (100.0% [51.0%, 100.0%]) — n<30: too small to support a claim` detected |
| Browser egress | NOT RUN | Playwright absent |
| Fuzzing at scale | NOT RUN | Tooling absent |
| MCP conformance | NOT RUN | Suite not present |
| Supply chain | NOT RUN | Scanners absent |
| Resource exhaustion / soak | NOT RUN | Not executed |

Strongest allowed statement: no failure was observed in the executed classes. That is not a claim of security.

## Failures and losses

- Static extraction recovers nothing from the JavaScript-only shell with the browser disabled.
- The non-UTF8 fixture recovered `0/2 (0.0% [0.0%, 65.8%]) — n<30: too small to support a claim` of its planted facts; cause not established.
- The large page recovered `0/1 (0.0% [0.0%, 79.3%]) — n<30: too small to support a claim` of its planted facts: the final marker sits at
  the end of a long page and was not in the returned passages.
- The injection corpus is synthetic; detection and false-positive rates are corpus-specific.
- Cache physical file size can exceed the logical cap.
- `.env.example` holds a non-placeholder key value that could not be classified safely.
- The root stack was not run; no cross-stack numbers are merged.

## Honesty section

**Could any number be changed without the linter noticing?** No numeric token is accepted unless it is
in the reporter manifest, and the report is rebuilt and byte-compared during lint. `41` ledger
runs back the report; `15` categories are explicitly NOT RUN.

**Is anything left out without saying so?** The systems table and the NOT RUN list name every unrun
system and class, including the root stack, browser, live search, Tavily, SearXNG, conformance, fuzzing,
soak, independent audit and human review.

**Did any test pass a broken build?** The SSRF tests failed with the guard disabled (`4/4 (100.0% [51.0%, 100.0%]) — n<30: too small to support a claim`
of mutation checks detected). Token-cap and scanner mutations were not run.

**Did every Tavily comparison use identical queries, caps and timing?** No Tavily comparison was run,
so the fairness question is not applicable in this pass.

**Where does WebLens lose, and is it stated first?** It loses on JavaScript-only extraction without a
browser, stated above the positive results. Against Tavily nothing is measured in either direction.

**Independent audit and human review:** NOT RUN. No separate read-only agent and no human reviewer
participated. The reporter is deterministic and owner-verifiable, but it was written by the same
executor whose work it describes. No result is labelled human-verified or model-judged.

## Reproduction

```bash
python tools/v6_verify_evidence.py
python tools/v6_build_report.py
python tools/v6_lint_report.py
```

Experiments must run through `tools/v6_evidence_run.py` with a new id; ids are immutable.

## Evidence provenance

- git commit: `902415d49f8d` (branch `master`)
- working-tree hash: `8f6ac2df4f55d5797270952e1f80b56980f0d3f0ab3f2a571d93e1374839b765`
- ledger head: `271bc8c3cc6b5b4ff81d80f86511f6106a3ee5f61818bc36a5716c5825125a53`
- ledger runs: `41`
- timeline: 6 inherited run(s) overlap another run; they came from a prior interrupted parallel session. This pass's runs are strictly sequential, and that is what the linter enforces.
