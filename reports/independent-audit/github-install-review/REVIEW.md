# Independent Review — WebLens GitHub Install & Real-World Run

**Review ID:** `weblens-github-realworld-review-20261105`  
**Reviewer:** Subagent 2 — independent monitor/reviewer  
**Subject:** Subagent 1's fresh GitHub install and real-world WebLens runs  
**Repository:** `https://github.com/Tusharkapoor-oop/Third-Eye-LLM.git`  
**Reviewed commit:** `b3a0b62` (`b3a0b624c73191d86a6e681edef531bbdb83f37d`)  
**Install under review:** `C:\Users\ACER\AppData\Local\Temp\opencode\weblens-gh-run-20261105\clone`  
**Review date:** 2026-11-05  
**Write boundary:** only `reports/independent-audit/github-install-review/`; Subagent 1 evidence was not modified.

---

## 1. Executive verdict

| Question | Verdict |
|---|---|
| Is the GitHub install real and isolated? | **PASS** |
| Do the claimed 14 CLI invocations and 49 raw files exist? | **PASS** |
| Does Subagent 1's summary match the raw evidence? | **SUBSTANTIATED, with minor discrepancies** |
| Did independent reruns reproduce the key behaviors? | **YES — 6/6 reruns exited 0 and reproduced the reported statuses** |
| Overall real-world capability of `weblens 0.1.0` at `b3a0b62` | **PARTIAL** |

Subagent 1's install claim is substantiated. The clone is a clean, shallow checkout of `b3a0b62`; the package is an editable install into a dedicated Python 3.13.15 venv; `weblens --version` returns `weblens 0.1.0`; there is no global install and no workspace-venv contamination. The primary working tree is dirty, but none of the GitHub-install results should be attributed to those uncommitted changes.

Subagent 1's capability summary is also substantially accurate: search, `doctor --live`, and `research` on example.com are PARTIAL; query-mode extraction on example.com is FAIL; `--full` extraction works; Python 3.14 extraction is PASS; map and crawl are PASS; Python 3.14 research is FAIL. The main corrections are small but real: one `doctor` run was not cache-isolated, the research ground-truth JSON contains false `illustrative` flags, the claim that DDG timed out on *both* live attempts is only directly proven for `search`, and four of the claimed eight direct probes have no saved raw artifact.

The biggest real-world limitation is the keyless search layer. DuckDuckGo timed out, leaving only MWMbl + Wikipedia; that produced off-topic search results and prevented `research` from reaching `docs.python.org` for a Python 3.14 question. `research` is extractive-only by design, so it returns evidence fragments rather than an answer.

---

## 2. Install provenance and isolation

### 2.1 Provenance

| Check | Observed | Verdict |
|---|---|---|
| Repository URL | `https://github.com/Tusharkapoor-oop/Third-Eye-LLM.git` | OK |
| Requested commit | `b3a0b62` | — |
| Local clone HEAD | `b3a0b624c73191d86a6e681edef531bbdb83f37d` | **matches** |
| Clone depth | `git rev-list --count HEAD` = `1` | shallow, as claimed |
| Clone worktree | `git status --porcelain` = empty | **clean** |
| Remote `main` at review time | `4e0885d21842e5382716f3076b6c3a4f4737f469` | **does not match clone** |
| Package version | `weblens 0.1.0` | OK |
| Venv Python | `Python 3.13.15` | OK |
| Install mode | editable (`direct_url.json` → clone/weblens) | OK |
| Resolved / installed packages | 58 / 58 | OK |
| Global `weblens` on PATH | none (`Get-Command weblens -All` empty) | OK |
| Workspace venv used | no | OK |

**Important provenance nuance:** the install is a clean clone of the requested `b3a0b62`, but `b3a0b62` is **not the current remote `main` tip** at review time (`4e0885d`). The review therefore describes `b3a0b62` only; fixes or changes after that commit are not included. The task's expected commit was `b3a0b62`, so the install meets the requested pin.

### 2.2 Isolation and contamination

- Installed venv: `C:\Users\ACER\AppData\Local\Temp\opencode\weblens-gh-run-20261105\clone\.venv`
- Editable project location: `...\weblens-gh-run-20261105\clone\weblens`
- The workspace venv `C:\Users\ACER\Downloads\Broswer for ai agnets\.venv` is Python 3.14.0 and contains a **pre-existing** editable install pointing to `C:\Users\ACER\Downloads\Broswer for ai agnets\src`, dated 2026-10-20. This run did not use it or write to it. No contamination.
- The isolated venv is Python 3.13.15, so the running interpreter itself proves the workspace venv was not used.

### 2.3 Cache isolation

Subagent 1 redirected `WEBLENS_CACHE_DIR` to `...\weblens-gh-run-20261105\cache`. This is mostly true, but **`cmd01` was not isolated**:

- `raw/cmd01-doctor.stdout.txt` shows `"cache_dir": "C:\\Users\\ACER\\.weblens"` and `"entries": 661`.
- `raw/cmd02-doctor-live.stdout.txt` onward show the temp cache and `"entries": 0`.

`doctor` does not fetch web content, so this did not contaminate search/extract/research results. It does make the blanket statement “cache was cold at the start of the CLI runs” (`RESULTS.md` evidence-integrity section) imprecise: the first CLI run was not cold; the cold run starts at `cmd02`.

For the independent review, each rerun used its own fresh cache directory under `review-cache/<command-id>`; `rr01-doctor` reported `entries: 0`.

### 2.4 Install exit status

The manifest records exit code `0` for clone, venv, and `uv pip install`, and the install log shows `Resolved 58 packages`, `Prepared 58 packages`, `Installed 58 packages`, with `weblens==0.1.0` editable. There is no separate install `.meta.json` with a machine-readable exit code, so the install exit status is **recorded in the manifest and supported by the completed venv/log**, not independently re-executed (the review was instructed not to reinstall). The PowerShell `NativeCommandError` text in the install logs is stderr formatting from `uv`, not a build failure.

---

## 3. Evidence inventory

### 3.1 File count and command count

| Item | Claimed | Actual | Verdict |
|---|---:|---:|---|
| Raw files under `github-install-run/raw/` | 49 | **49** | match |
| CLI command sets (`stdout` + `stderr` + `meta.json`) | 14 | **14** | match |
| Command-set files | 42 | **42** | match |
| Supporting files (analysis, environment, ground truth, install logs) | 7 | **7** | match |
| Commands with exit code recorded | 14 | **14** | match |
| Commands with non-zero exit | 0 | **0** | match |
| Commands with non-empty stderr | 0 | **0** | match |

The 7 supporting files are: `analysis-checks.json`, `environment.json`, `groundtruth-example-com.html`, `groundtruth-research-sources.json`, `install-uv-pip-install.log`, `install-uv-venv.log`, `verify-python-env.log`.

### 3.2 The 14 commands

| ID | Command | Exit | Wall (s) | CLI status | Key result |
|---|---|---:|---:|---|---|
| `cmd00a-version` | `weblens --version` | 0 | 2.094 | ok | `weblens 0.1.0` |
| `cmd00b-help` | `weblens --help` | 0 | 1.760 | ok | command list |
| `cmd01-doctor` | `weblens doctor --pretty` | 0 | 2.386 | `ok:true` | default cache, 661 entries |
| `cmd02-doctor-live` | `weblens doctor --live --pretty` | 0 | 7.606 | `partial` | live providers mwmbl+wikipedia |
| `cmd03-search-python314` | `weblens search "Python 3.14 release notes" -k 5 --pretty` | 0 | 6.863 | `partial` | 5 results; DDG TimeoutError |
| `cmd04-extract-example` | `weblens extract https://example.com -q "What is this page?" --max-tokens 300 --pretty` | 0 | 5.577 | `no_reliable_result` | 0 passages |
| `cmd04b-extract-example-full` | `weblens extract https://example.com --full --pretty` | 0 | 3.339 | `ok` | 156-char page text |
| `cmd04c-extract-example-query-match` | `weblens extract https://example.com -q "documentation examples domain" --max-tokens 300 --pretty` | 0 | 5.584 | `ok` | 1 passage |
| `cmd05-extract-python314` | `weblens extract https://docs.python.org/3/whatsnew/3.14.html -q "What are the major new features in Python 3.14?" --max-tokens 500 --pretty` | 0 | 6.358 | `ok` | 2 passages; 4 feature terms |
| `cmd06-map-example` | `weblens crawl https://example.com --mode map --max-pages 5 --max-depth 1 --pretty` | 0 | 3.332 | `ok` | 1 URL; `no_links_found` |
| `cmd06b-map-python-docs` | `weblens crawl https://docs.python.org/3/library/asyncio.html --mode map --max-pages 5 --max-depth 1 --pretty` | 0 | 2.800 | `ok` | 5 unique URLs |
| `cmd07-crawl-asyncio` | `weblens crawl https://docs.python.org/3/library/asyncio.html --mode crawl --max-pages 3 --max-depth 1 -q "How does asyncio work?" --max-tokens 600 --pretty` | 0 | 7.455 | `ok` | 2 pages; both `ok` |
| `cmd08-research-example` | `weblens research "What is the purpose of example.com?" --max-tokens 500 --pretty` | 0 | 10.483 | `partial` | 4 findings; 3 sources |
| `cmd09-research-python314` | `weblens research "What are the major new features in Python 3.14?" --max-tokens 500 --pretty` | 0 | 12.677 | `partial` | 2 findings; 1 source |

`RESULTS.md` says “all 14 CLI invocations exited 0.” That is correct. Its tables list 10 primary CLI rows + 3 diagnostics = 13; `cmd00b-help` is present in the manifest/raw but omitted from the RESULTS tables. This is a documentation omission, not a false count.

### 3.3 Evidence hashes

Key SHA-256 values (full listing in `review.json`):

- `manifest.json` → `8736B05976294BB7CFB1226A5314FC6CF5F85CCECA833635430A64B09CDC5B59`
- `RESULTS.md` → `600143F2A11193035BE6D43B12092335A119EFFE5CA8B94934794290586FBACA`
- `cmd03-search-python314.stdout.txt` → `653E028833FFBF17C754859ACC1D4E1DF1FC1A7E0BF6EB30F668AF3B932D1E2E`
- `cmd04-extract-example.stdout.txt` → `2A43A7DF68FB2C1F5B939EE96249075E7B5FA42CD51AA6BE3662F50BD5C2B9C4`
- `cmd05-extract-python314.stdout.txt` → `7FE590E275EA93B6A5747D456438B0A7D646776CA800E52A5DD497956DE6841A`
- `cmd08-research-example.stdout.txt` → `8A1C3126DB358AD6C8367656F0B76DBC6B082DF0541A67160E6D4B2B852A5DBC`
- `cmd09-research-python314.stdout.txt` → `10FE126E5F24C21094ABD638946DFEEEC2B957D3EE9E557F5AC851B3993AA0CE`
- Combined hash of all 49 raw files → `fbfe8b370014366db18f6028599e0aacb0558c2e879f9bbb75eff9867f356c1b`

---

## 4. Independent rerun results

All reruns used the installed exe:

`C:\Users\ACER\AppData\Local\Temp\opencode\weblens-gh-run-20261105\clone\.venv\Scripts\weblens.exe`

Each had a fresh `WEBLENS_CACHE_DIR` at `reports/independent-audit/github-install-review/review-cache/<id>` (pre-run entries 0). Raw output is under `review-raw/`.

| ID | Command | Exit | Wall (s) | CLI `ms` | Status | Key metrics |
|---|---|---:|---:|---:|---|---|
| `rr01-doctor` | `doctor --pretty` | 0 | 5.272 | — | `ok:true` | Python 3.13.15; 3 providers; cache entries 0 |
| `rr02-search-python314` | `search "Python 3.14 release notes" -k 5 --pretty` | 0 | 7.883 | 3508 | `partial` | 5 results; 5 unique; DDG TimeoutError |
| `rr03-extract-example-q` | `extract https://example.com -q "What is this page?" --max-tokens 300 --pretty` | 0 | 5.297 | 1110 | `no_reliable_result` | 0 passages; tok 74 |
| `rr04-extract-example-full` | `extract https://example.com --full --max-tokens 300 --pretty` | 0 | 5.278 | 1517 | `ok` | 156 chars; tok 104 |
| `rr05-extract-example-altq` | `extract https://example.com -q "documentation examples domain" --max-tokens 300 --pretty` | 0 | 5.762 | 1306 | `ok` | 1 passage; tok 127 |
| `rr06-research-example` | `research "What is the purpose of example.com?" --max-tokens 500 --pretty` | 0 | 12.031 | 7409 | `partial` | 4 findings; 3 sources; tok 492 |

**Rerun conclusions:**

- `doctor` still reports `ok: true`, Python 3.13.15, providers `["ddg","mwmbl","wikipedia"]`, `browser: false`, tokenizer `cl100k_base`.
- Search reproduced the exact 5 URLs and titles, 5 unique URLs, and the DDG `TimeoutError`. `off_topic_filtered` was `5` in the rerun vs `4` in Subagent 1's run; that is ordinary run-to-run variability, not a contradiction.
- Example.com query-mode extraction reproduced `no_reliable_result` with 0 passages and the same title/content hash (`0a080719be9fbb82`).
- `--full` reproduced the exact 156-character page sentence. Token count was 104 vs Subagent 1's 103 because the CLI's token accounting includes the variable `ms` field; this is not an output mismatch.
- The alternate query reproduced 1 passage with the exact page sentence.
- Research reproduced 4 findings and 3 distinct sources with the same gap (`no_source_for:purpose`) and the same `fetch_failed:FetchError` warning. Fetch timestamps differ, as expected.

No rerun used Subagent 1's cache, and no Tavily or paid API was used.

---

## 5. Accuracy against ground truth

### 5.1 example.com — the live page and the stale expectation

Independent live fetch (`review-raw/gt-live-example.html`, HTTP 200, 577 bytes) and the saved Subagent 1 artifact (`raw/groundtruth-example-com.html`) agree:

| Fact | Result |
|---|---|
| Title contains “Example Domain” | **YES** |
| Text contains “illustrative examples” | **NO** |
| Text contains “documentation examples” | **YES** |
| Text contains or cites `iana.org` | **NO** |
| Anchor (`<a>`) elements | **0** |
| Extracted `--full` text length | **156 characters** |
| Extracted text matches live paragraph | **YES** |

Live page paragraph:

> This domain is for use in documentation examples without needing permission. This is not a service; avoid relying on it for testing and monitoring purposes.

**Conclusion:** Subagent 1's claim that the review plan's expected text is stale is **substantiated from the actual HTML**. The plan's three facts are not supportable against this live page: only the “Example Domain” fact is present, and there is no iana.org link. This is an environment/page-content change, not an extractor fabrication. The `--full` command is faithful to the live page.

**Query-mode extraction:** the requested command returned exactly 0 passages and `status: no_reliable_result`. That is accurate. The root cause is query-dependent: after stopword removal, the only content term in “What is this page?” is `page`, and that word does not occur in the 156-character page. `select_passages` returns no passages when best query coverage is zero. This is a real usability defect for terse pages; `--full` or a query with a term that occurs on the page works.

### 5.2 Search — exact counts and relevance

From `raw/cmd03-search-python314.stdout.txt`:

| Metric | Value |
|---|---:|
| Results | 5 |
| Unique URLs | 5 |
| Titles present | 5/5 |
| Snippets present | 5/5 |
| Distinct domains | 4 |
| Providers that answered | 2 (`mwmbl`, `wikipedia`) |
| Provider failures | `ddg: TimeoutError` |
| Off-topic results | 2 (`History of Python`, `CPython`) |
| First result URL HTTP status | 200 (`https://docs.python.org/3.14/whatsnew/3.14.html`) |

The claim of “5 results, DDG timeout” is **substantiated**. The relevance criticism is also fair: two of five results are general Python-history/CPython pages, not 3.14 release notes. The first result is the correct 3.14 whats-new page and was independently reachable.

### 5.3 Research on example.com — findings, sources, traceability

From `raw/cmd08-research-example.stdout.txt` and the independent rerun:

| Metric | Value |
|---|---:|
| Findings | 4 |
| Distinct source URLs | 3 |
| Findings with URL + verbatim text | 4/4 |
| Findings traceable to their cited page | 4/4 |
| Clearly off-topic findings | 1 (`en.wikipedia.org/wiki/.xxx`) |
| Duplicate/overlapping claims | 2 findings repeat the same “second-level domain” sentence across Wikipedia and HandWiki |
| LLM prose / synthesis | none |
| Gaps | `no_source_for:purpose` |
| Warnings | `fetch_failed:FetchError` |

Sources:

1. `https://en.wikipedia.org/wiki/.xxx` — finding about `example.xxx`; irrelevant to “purpose of example.com.”
2. `https://en.wikipedia.org/wiki/Example.com` — two findings: the domain-table/second-level-domain sentence and the Purpose-section sentence.
3. `https://handwiki.org/wiki/Example.com` — duplicate of the second-level-domain sentence.

**Traceability check:** all four claims were found in the fetched source text (independent fetches saved under `review-raw/gt-wiki-*.html`, `review-raw/gt-handwiki-example.html`). Each finding carries a URL, character span, heading, and fetch timestamp. The extractive-only claim is confirmed by `weblens/src/weblens/research/engine.py`: the module docstring says “No LLM is called,” and the research path imports only deterministic extraction/search/token utilities.

**Gap-accounting nuance:** the tool flags `no_source_for:purpose` even though the Purpose-section quote is returned. The code computes supported terms from `tokenize(finding.claim)` only (`engine.py`, gap section); it does not include the finding's heading (`"Purpose"`). So the gap is consistent with the code but semantically misleading. Subagent 1's “gap accounting appears inconsistent” wording is fair.

### 5.4 Research on Python 3.14 — failure is real

From `raw/cmd09-research-python314.stdout.txt`:

| Metric | Value |
|---|---:|
| Findings | 2 |
| Distinct source URLs | 1 (`en.wikipedia.org/wiki/Python_(programming_language)`) |
| Findings whose claim contains “3.14” | 0/2 |
| Template-string mentions | 0 |
| Deferred-annotation mentions | 0 |
| Subinterpreter mentions | 0 |
| `compression.zstd` mentions | 0 |
| Self-reported gap | `no_source_for:3.14` |
| Status | `partial` (capability verdict: **FAIL**) |

The two findings are generic Wikipedia prose about the PEP process and annual release cadence. The output contains “3.14” only in the query and the gap string, not in either finding. The claim that the run “lacks 3.14 content and self-reports `no_source_for:3.14`” is **substantiated**. The tool correctly refuses to synthesize an answer, but it also fails to reach the primary source that `search` had already returned. `status: partial` is the CLI's status; the capability answer is FAIL because the returned evidence does not answer the question.

### 5.5 Python 3.14 extraction, map, and crawl

| Capability | Ground-truth check | Verdict |
|---|---|---|
| Python 3.14 extract | 2 passages; page about 3.14; contains template strings, deferred annotations, subinterpreters, `compression.zstd`; tok 488; `cut:true` | **PASS** |
| Map example.com | 1 URL (`https://example.com/`); 0 duplicates; `status ok`; `no_links_found` matches 0 anchors | **PASS** |
| Map Python docs | 5 unique URLs; 0 duplicates; all `docs.python.org`; heading labels sometimes leak (`auditing event`, `Availability`) | **PASS** (label-quality caveat) |
| Crawl asyncio | 2 pages, both `ok`, 2 passages, tok 562; `max-pages 3` respected | **PASS** |

The crawl output has **no `page_failures` field**. Subagent 1 says “absent ⇒ none”; the review plan's wording says “page_failures reported.” Functionally the crawl succeeded, but the exact plan criterion is not met because the field is absent. Treat this as a PASS-with-caveat, not a failure.

---

## 6. Discrepancies and overclaims

| # | Discrepancy | Raw evidence | Impact |
|---|---|---|---|
| D1 | `cmd01` was **not** cache-isolated, despite the blanket cache-isolation claim. | `raw/cmd01-doctor.stdout.txt` shows `cache_dir: C:\Users\ACER\.weblens`, `entries: 661`; `raw/cmd02-doctor-live.stdout.txt` shows the temp cache, `entries: 0`. | Low. Doctor does not fetch web content. It does falsify “cache was cold at the start of the CLI runs.” |
| D2 | `groundtruth-research-sources.json` marks `illustrative: true` for Wikipedia Example.com and HandWiki, but the live pages contain zero occurrences of `illustrat*`. | `raw/groundtruth-research-sources.json` vs independent `review-raw/gt-wiki-example.html`, `gt-handwiki-example.html` (0 matches). | Medium as an artifact-accuracy issue. The main conclusion (all 3 sources reachable; Purpose and .xxx quotes exist) is still true. |
| D3 | “DDG timed out on both live attempts” is only directly proven for `search`. | `raw/cmd03-search-python314.stdout.txt` has `"fail":{"ddg":"TimeoutError"}`. `raw/cmd02-doctor-live.stdout.txt` only omits `ddg` from `live.providers` and reports `"error": null`; it does not name a timeout. | Low. The search rerun independently reproduces the DDG timeout; the doctor attribution is an inference. |
| D4 | “8 direct probes” is not backed by 8 saved artifacts. | Raw ground-truth artifacts are `groundtruth-example-com.html` (1 fetch) and `groundtruth-research-sources.json` (3 URLs). The 2 docs-availability checks and 2 search-result URL checks have no raw files. | Low-medium evidence gap. The search-result URL was independently verified 200 in this review; the claim is plausible but not fully preserved. |
| D5 | Crawl PASS claim relies on `page_failures` being absent. | `raw/cmd07-crawl-asyncio.stdout.txt` has no `page_failures` key. | Low. Functional pass; strict plan wording (“page_failures reported”) is not met. |
| D6 | RESULTS tables list 13 CLI rows, but the claimed count is 14. | `raw/cmd00b-help.*` exists in the manifest/raw; it is not in the RESULTS tables. | Documentation-only. The count 14 is correct. |
| D7 | `--full` token count differs: 103 (Subagent 1) vs 104 (rerun). | `raw/cmd04b-extract-example-full.stdout.txt` vs `review-raw/rr04-extract-example-full.stdout.txt`. | None. `service.py` includes the variable `ms` field in token accounting; one extra digit changes the count. |
| D8 | The clone is `b3a0b62`, but remote `main` is now `4e0885d`. | `git rev-parse HEAD` vs `git ls-remote ... refs/heads/main`. | Provenance caveat. Results describe `b3a0b62`, not current main. |
| D9 | “No source file or reports/domination modified” cannot be fully verified. | Primary tree `git status --porcelain` is dirty (e.g., `config.py`, `src/engine/search/aggregator.py`, `reports/domination/...`). | Scope caveat. The review did not attribute those changes to Subagent 1; they are uncommitted primary-tree state. |
| D10 | Ground-truth HTML is 577 bytes over HTTP but 580 bytes on disk. | `raw/groundtruth-example-com.html` starts with UTF-8 BOM `EF BB BF`; HTTP `Content-Length`/download was 577. | None. BOM only. |
| D11 | Search warning count differs: `off_topic_filtered:4` vs rerun `5`. | `raw/cmd03...` vs `review-raw/rr02...`. | None. Run-to-run provider variation; the off-topic result set is the same. |

No evidence was found that Subagent 1 fabricated outputs, skipped a command, or used a paid/keyed provider. The install and the major capability verdicts hold.

---

## 7. Security and secret scan

- Scanned all 49 Subagent 1 raw files and all reviewer raw files for: `sk-ant-`, `sk-proj-`, `sk-[A-Za-z0-9]{20,}`, `tvly-[A-Za-z0-9]{10,}`, `ghp_...`, `xox[baprs]-`, `AIza...`, `Bearer <token>`, private-key headers, and `password=...`.
- **Matches: 0.** No secret values were printed.
- Environment variables checked for presence only: `TAVILY_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `BRAVE_API_KEY`, `SERPER_API_KEY`, `GOOGLE_API_KEY`, `WEBLENS_TAVILY_API_KEY`, `WEBLENS_SEARCH_PROVIDER` — all **absent**.
- Search providers used: `ddg`, `mwmbl`, `wikipedia`; Tavily was never invoked. No paid API spend.
- No global `weblens` install; no workspace venv contamination.
- Requests were benign, single requests: example.com, Wikipedia Example.com, Wikipedia .xxx, HandWiki Example.com, one HEAD for the docs.python.org search result. No load, no localhost, no third-party attack.

---

## 8. Capability verdicts

| Capability | Verdict | Basis |
|---|---|---|
| Install / version | **PASS** | clean clone at `b3a0b62`; 58 packages; editable venv; `weblens 0.1.0` |
| `doctor` (static) | **PASS** | `ok: true`, Python 3.13.15, 3 providers, tokenizer `cl100k_base` |
| `doctor --live` | **PARTIAL** | live status `partial`; only mwmbl + wikipedia; DDG absent (timeout inferred) |
| Search | **PARTIAL** | 5 real results / 5 unique; DDG timeout; 2 off-topic results |
| Extract example.com — requested query | **FAIL** | `no_reliable_result`, 0 passages |
| Extract example.com — `--full` | **PASS** | exact 156-char live page text; plan facts stale |
| Extract example.com — alternate query | **PASS** | 1 correct passage |
| Extract Python 3.14 docs | **PASS** | 2 passages; 4 concrete 3.14 feature terms |
| Map | **PASS** | 1 URL, 0 duplicates; `no_links_found` correct |
| Crawl | **PASS*** | 2 pages, both `ok`, 2 passages; `page_failures` field absent |
| Research example.com | **PARTIAL** | 4 findings / 3 sources, all traceable; 1 off-topic; no synthesis; gap inconsistency |
| Research Python 3.14 | **FAIL** | 2 findings / 1 source; neither mentions 3.14; gap self-reported |
| Extractive-only research design | **PASS** | code path has no LLM; findings are verbatim sentences with URLs/spans |
| Keyed / paid providers | **BLOCKED** | no keys present; not exercised (and not required) |
| Browser / JS rendering | **BLOCKED / DISABLED** | `browser: false` in `doctor` |
| Current remote `main` (`4e0885d`) | **NOT RUN** | install is pinned to `b3a0b62` |

`*` Crawl is functionally PASS; strict plan criterion “page_failures reported” is not met because the field is absent.

**Overall real-world capability: PARTIAL.** The install and deterministic extraction stack work. The keyless retrieval stack is the limiting layer: search breadth, relevance, and research coverage are unreliable for current/version-specific questions.

---

## 9. Biggest real-world limitation

**The keyless search layer is the bottleneck, and every downstream capability inherits its blind spots.** DuckDuckGo — the primary general-web provider — timed out. The fallback set (MWMbl + Wikipedia) returned only 5 results, two of which were off-topic, and `research` could not reach `docs.python.org` for a Python 3.14 question even though `extract` had just retrieved that exact page successfully. The result was a Python 3.14 research run with 1 source, 2 generic findings, no 3.14 feature content, and a self-reported `no_source_for:3.14`.

Secondary limitation: strict lexical passage selection returns `no_reliable_result` with **zero passages** for a short page when the query's surviving content term does not occur in the page. A bare `extract <url> -q ...` is therefore not a reliable “give me the page content” operation; `--full` is the reliable path for terse pages. The research engine is extractive-only by design, so even a successful run returns evidence fragments, not a synthesized answer.

---

## 10. Evidence paths

### Subagent 1 (read-only)

- `reports/independent-audit/github-install-run/manifest.json`
- `reports/independent-audit/github-install-run/RESULTS.md`
- `reports/independent-audit/github-install-run/errors.md`
- `reports/independent-audit/github-install-run/raw/` (49 files)
- Isolated install: `C:\Users\ACER\AppData\Local\Temp\opencode\weblens-gh-run-20261105\clone`

### Independent review

- `reports/independent-audit/github-install-review/REVIEW.md`
- `reports/independent-audit/github-install-review/review.json`
- `reports/independent-audit/github-install-review/review-raw/` (rerun stdout/stderr/meta, ground-truth HTML, `groundtruth-checks.json`, runner)
- `reports/independent-audit/github-install-review/review-cache/` (per-command fresh caches)

### Scope / method limitations

- Six reruns only; no independent crawl rerun (the crawl claim was verified from raw output).
- One search invocation and one research invocation, as instructed; no load or stress testing.
- No Tavily or paid API; no keyed provider.
- Timings vary with network conditions; token counts include timing metadata and can differ by ±1.
- The install is `b3a0b62`; current remote `main` (`4e0885d`) was not tested.
- The primary working tree is dirty; its uncommitted changes were not attributed to the GitHub install.

---

## 11. Bottom line

Subagent 1's install is **real, isolated, and reproducible**, and its major capability verdicts are **substantiated by the raw evidence and by independent reruns**. The summary is not perfect: `cmd01` was not cache-isolated, the research ground-truth `illustrative` flags are false, the DDG “both live attempts” wording is partly inferred, and four of the claimed eight direct probes lack saved artifacts. None of these changes the central result.

The real-world verdict is **PARTIAL**: deterministic install/extract/map/crawl work; keyless search is thin and unreliable; query-mode extraction fails on terse pages; and research cannot reliably answer current/version-specific questions without a broader search provider or an LLM synthesis layer.
