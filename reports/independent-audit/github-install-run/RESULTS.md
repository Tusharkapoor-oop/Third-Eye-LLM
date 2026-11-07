# WebLens — Independent GitHub Install & Real-World Run

**Run ID:** `weblens-gh-run-20261105`
**Auditor:** Subagent 1 (independent installer/runner)
**Date:** 2026-11-05
**Repository:** `https://github.com/Tusharkapoor-oop/Third-Eye-LLM.git` (branch `main`)
**Commit verified:** `b3a0b624c73191d86a6e681edef531bbdb83f37d` (`b3a0b62`, matches requested)
**Package:** `<clone>/weblens` — `weblens 0.1.0`, CLI entry `weblens.cli:main`
**Isolation:** fresh `uv` venv (Python 3.13.15) + cold cache via `WEBLENS_CACHE_DIR` pointing inside the temp run dir. Workspace venv was **not** used.
**Spend:** $0. No Tavily / paid / keyed provider. No API keys were present in the environment (presence checked only, values never read).

---

## Verdict table

| # | Capability / command | Verdict | Exit | Wall | CLI `status` | Evidence |
|---|---|---|---|---|---|---|
| 0 | Install (`uv venv` + `uv pip install -e`) | **PASS** | 0 | 28.17 s (install) | — | `raw/install-uv-*.log` |
| 1 | `weblens --version` | **PASS** | 0 | 2.09 s | — | `raw/cmd00a-version.stdout.txt` |
| 2 | `weblens doctor` | **PASS** | 0 | 2.39 s | `ok: true` | `raw/cmd01-doctor.stdout.txt` |
| 3 | `weblens doctor --live` | **PARTIAL** | 0 | 7.61 s | `partial` | `raw/cmd02-doctor-live.stdout.txt` |
| 4 | `search "Python 3.14 release notes" -k 5` | **PARTIAL** | 0 | 6.86 s | `partial` | `raw/cmd03-search-python314.stdout.txt` |
| 5 | `extract https://example.com -q "What is this page?"` | **FAIL** | 0 | 5.58 s | `no_reliable_result` | `raw/cmd04-extract-example.stdout.txt` |
| 6 | `extract https://docs.python.org/3/whatsnew/3.14.html` | **PASS** | 0 | 6.36 s | `ok` | `raw/cmd05-extract-python314.stdout.txt` |
| 7 | `crawl https://example.com --mode map` | **PASS** | 0 | 3.33 s | `ok` | `raw/cmd06-map-example.stdout.txt` |
| 8 | `crawl …asyncio.html --mode crawl --max-pages 3` | **PASS** | 0 | 7.46 s | `ok` | `raw/cmd07-crawl-asyncio.stdout.txt` |
| 9 | `research "purpose of example.com"` | **PARTIAL** | 0 | 10.48 s | `partial` | `raw/cmd08-research-example.stdout.txt` |
| 10 | `research "major new features in Python 3.14"` | **FAIL** | 0 | 12.68 s | `partial` | `raw/cmd09-research-python314.stdout.txt` |

Extra diagnostic runs (not requested, used to separate cause from symptom):

| # | Diagnostic | Verdict | Wall | Evidence |
|---|---|---|---|---|
| D1 | `extract https://example.com --full` | **PASS** | 3.34 s | `raw/cmd04b-extract-example-full.stdout.txt` |
| D2 | `extract https://example.com -q "documentation examples domain"` | **PASS** | 5.58 s | `raw/cmd04c-extract-example-query-match.stdout.txt` |
| D3 | `crawl …asyncio.html --mode map --max-pages 5` | **PASS** | 2.80 s | `raw/cmd06b-map-python-docs.stdout.txt` |

All 14 CLI invocations exited `0`. **No command crashed and no command failed to run.**

---

## Install

```text
git clone --depth 1 --branch main https://github.com/Tusharkapoor-oop/Third-Eye-LLM.git <clone>   # exit 0
uv venv --python 3.13 <clone>\.venv                                                              # exit 0, CPython 3.13.15
uv pip install --python <clone>\.venv\Scripts\python.exe -e <clone>\weblens                      # exit 0, 58 pkgs, 28.17 s
<clone>\.venv\Scripts\weblens.exe --version                                                      # "weblens 0.1.0"
```

- Resolved 58, installed 58 packages; `weblens==0.1.0` installed editable from the clone.
- `pip` fallback was **not needed**. No install errors, no `errors.md`-class failure.
- `doctor` reports `providers: [ddg, mwmbl, wikipedia]`, `unavailable: {}`, `browser: false`, tokenizer `cl100k_base`.
- Default cache at `C:\Users\ACER\.weblens` already held **661 entries / 5.25 MB** from prior activity. To avoid passing off cached content as live evidence I redirected the cache to an isolated temp dir (`WEBLENS_CACHE_DIR`). The CLI arguments themselves were unchanged. Cold cache confirmed in `cmd02` (`entries: 0`).

---

## Accuracy checks (explicit, with ground truth)

### example.com extraction — requested command **FAIL**, extraction engine itself OK

Requested command `extract https://example.com -q "What is this page?" --max-tokens 300` returned:

```json
{"status":"no_reliable_result","t":"Example Domain","ps":[],"tok":74,
 "warn":["low_content","no_query_match"],"ms":2097}
```

- Title **"Example Domain" present**: YES.
- Sentence about "illustrative examples": **NO — the live page no longer contains that sentence.**
- Link to iana.org: **NO — the live page contains no links at all.**

Ground-truth probe (`raw/groundtruth-example-com.html`, HTTP 200, 577 bytes) shows the page in Nov 2026 is a 156-char stub:

> `<p>This domain is for use in documentation examples without needing permission. This is not a service; avoid relying on it for testing and monitoring purposes.</p>`

So the check's expected "illustrative examples" / iana.org text is stale relative to the live web. The extractor is **not** fabricating; it returned zero passages because its lexical query matcher found no overlap with the 5-word query.

Cause isolated by diagnostics:

- `--full` → `status: ok`, exact 156 chars, `tok: 103`, only `low_content` warning. Extraction pipeline works.
- Query `"documentation examples domain"` → `status: ok`, 1 passage, exact page sentence, `tok: 127`.

**Finding:** default query-mode passage selection can return *zero* passages (and `no_reliable_result`) on short pages whenever the user's question has no lexical overlap with the page text. A bare `extract <url>` on a terse page is therefore not usable as "give me the page content"; `--full` is required. This is a real usability defect, not an install problem.

### search — real results, degraded provider set

`status: partial`, `n: 5`, `tok: 454`, `ms: 3511`, `prov: [mwmbl, wikipedia]`, `fail: {"ddg": "TimeoutError"}`.

| # | Title | URL | Snippet |
|---|---|---|---|
| 1 | What's New In Python 3.14 — Python 3.14.0a0 documentation | `https://docs.python.org/3.14/whatsnew/3.14.html` | yes |
| 2 | History of Python | `https://en.wikipedia.org/wiki/History_of_Python` | yes |
| 3 | Python Release Python 3.14.0b3 \| Python.org | `https://www.python.org/downloads/release/python-3140b3/` | yes |
| 4 | CPython | `https://en.wikipedia.org/wiki/CPython` | yes |
| 5 | Python 3.14 Alpha 1 Released With Early Changes — Phoronix | `http://www.phoronix.com/news/Python-3.14-Alpha-1` | yes |

- 5/5 have title + URL + snippet, 5 unique URLs, 4 domains. **Not empty, not an error.**
- Result 1 URL independently verified HTTP 200.
- Warning `off_topic_filtered:4` yet results 2 and 4 are clearly off-topic (History of Python, CPython) — relevance filtering is weak.
- **DuckDuckGo (the primary general web provider) timed out**; only MWMbl + Wikipedia answered. That is the root cause of the thin/off-topic result set.

### map (example.com) — 1 URL, zero duplicates, iana.org absent

`status: ok`, `n: 1`, `tok: 47`, `ms: 871`, `warn: ["no_links_found"]`.

- URLs: exactly `https://example.com/` — 1 URL, **0 duplicates**.
- Contains `example.com`: **YES**. Contains `iana.org`: **NO**.
- The absence is correct: the live page has no `<a>` elements (ground truth confirmed). The map tool honestly reported `no_links_found` rather than inventing links.
- Supplementary map on `docs.python.org/3/library/asyncio.html` (D3) returned **5 unique URLs, 0 duplicates**, all on `docs.python.org`, proving link discovery works. Label quality issue: `sys.html` was labeled `"auditing event"` and `intro.html` `"Availability"` — heading/anchor text leaked in place of page titles.

### crawl (asyncio) — 2 pages, 0 page failures

`status: ok`, `n: 2`, `tok: 562`, `ms: 4188`, no `page_failures` key (absent ⇒ none).

| Page | Page status | Passages |
|---|---|---|
| `https://docs.python.org/3/library/asyncio.html` | `ok` | 1 (event loop, transports, protocols, REPL) |
| `https://docs.python.org/3/library/ipc.html` | `ok` | 1 (Networking and Interprocess Communication intro) |

- Requested domain present in all passages: **YES** (100% `docs.python.org`).
- Content is genuinely about asyncio (mentions event loops, async/await, `python -m asyncio`).
- `max-pages 3` / `max-depth 1` respected (2 pages fetched).
- Weakness: second page is a sibling nav page (`ipc.html`), not strongly relevant to "How does asyncio work?"; no `cut` flag reported for the crawl, so budget truncation is opaque.

### research (example.com) — 4 verbatim findings, 3 sources, 1 irrelevant

`status: partial`, `n: 4`, `tok: 492`, `ms: 7817`, `gaps: ["no_source_for:purpose"]`, `warn: ["fetch_failed:FetchError"]`.

- Findings: **4**, distinct sources: **3** (`en.wikipedia.org/wiki/Example.com` ×2, `en.wikipedia.org/wiki/.xxx`, `handwiki.org/wiki/Example.com`).
- All 4 have a URL and verbatim quote text. No model prose/synthesis key exists in the payload (`engine.py:3`: "No LLM is called. Every finding is a verbatim sentence from a fetched page").
- Claim support verified: all 3 source URLs returned HTTP 200; the `Purpose` quote and the `.xxx` quote both exist on their pages (`raw/groundtruth-research-sources.json`).
- **Relevance defect:** one of four "findings" is from the `.xxx` TLD article and does not answer the question. The tool itself flags `no_source_for:purpose` even though a Purpose section quote was returned — gap accounting appears inconsistent.
- Because there is no synthesis, the output is evidence to be read by the caller, not an answer.

### research (Python 3.14) — **FAIL**

`status: partial`, `n: 2`, `tok: 411`, `ms: 10188`, `gaps: ["no_source_for:3.14"]`, `warn: ["fetch_failed:FetchError"]`.

- Only **1 distinct source**: `https://en.wikipedia.org/wiki/Python_(programming_language)`.
- Both findings are generic Wikipedia prose about the PEP process and release cadence. **Neither mentions any Python 3.14 feature.**
- Zero mentions of template strings, deferred annotations, subinterpreters, or `compression.zstd` — the actual 3.14 highlights that the `extract` command retrieved successfully from docs.python.org minutes earlier.
- The only correct signal is the self-declared gap `no_source_for:3.14`. **Verdict: FAIL** — claims are technically supported by the returned URL, but the returned URLs do not support an answer to the question. It did not surface the primary source even though search had already found it.

---

## Timings and token accounting

| Command | Wall | CLI `ms` | `tok` | `cut` |
|---|---|---|---|---|
| doctor | 2.39 s | — | — | — |
| doctor --live | 7.61 s | 4695 | — | — |
| search | 6.86 s | 3511 | 454 | — |
| extract example (query) | 5.58 s | 2097 | 74 | — |
| extract example (--full) | 3.34 s | 719 | 103 | — |
| extract python 3.14 | 6.36 s | 2854 | 488 | true |
| map example.com | 3.33 s | 871 | 47 | — |
| map python docs | 2.80 s | 774 | 148 | — |
| crawl asyncio | 7.46 s | 4188 | 562 | — |
| research example.com | 10.48 s | 7817 | 492 | true |
| research python 3.14 | 12.68 s | 10188 | 411 | true |

Total CLI wall time: **78.31 s** across 14 invocations. All token counts are the CLI's own reported `tok` values, not estimates. Budget `cut: true` on all three 500-token runs; the 300-token extract was not marked cut despite `tok: 74` with 0 passages (budget accounting counts pre-selection text).

---

## Biggest real-world limitation observed

**The keyless search layer is the bottleneck, and every downstream capability inherits its blind spots.** DuckDuckGo timed out on both live attempts (`doctor --live` and `search`), leaving only MWMbl + Wikipedia. As a result `research` could not reach `docs.python.org` for a Python 3.14 question — even though the same tool had just extracted that exact page successfully — and instead returned irrelevant Wikipedia prose while honestly flagging `no_source_for:3.14`. Install, extraction, mapping, and bounded crawling are solid; retrieval breadth and relevance are not.

Secondary limitation: strict lexical passage selection returns `no_reliable_result` with **zero passages** for a short page when the question shares no words with it, so `extract` on minimal pages needs `--full` to be useful.

---

## Evidence integrity notes

- Raw stdout/stderr are **UTF-8**. The Windows console code page is 437, so `Get-Content` mangles non-ASCII characters such as U+00A0; the bytes on disk are correct (verified by decoding raw files as UTF-8). No CLI encoding bug was found.
- Every command was captured with exit code, wall time, and byte counts via `Start-Process`/`cmd` redirection into `raw/<id>.{stdout,stderr}.txt` + `.meta.json`.
- Cache was cold at the start of the CLI runs (`entries: 0`), so results reflect real network fetches.
- No source file or `reports/domination` in the workspace repo was modified. All writes are under `reports/independent-audit/github-install-run/`.
- Benign single requests only: 8 direct probes (2 docs availability checks, 1 example.com ground-truth fetch, 2 search-result URL verifications, 3 research-source verifications). No load, no localhost, no third-party stress.
