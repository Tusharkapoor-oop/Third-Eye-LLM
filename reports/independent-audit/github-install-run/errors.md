# Errors and Warnings — `weblens-gh-run-20261105`

**Install outcome:** SUCCESS. There were **no install failures**, no build errors, no missing dependencies, and no non-zero exit codes. The `python -m venv` + `pip` fallback was never needed.

This file records every runtime error/warning actually emitted, so the non-`ok` statuses in `RESULTS.md` are traceable. All of these were non-fatal: the CLI still exited `0` and printed a JSON payload.

---

## 1. DuckDuckGo provider timeout (recurring, affects search + research)

**Where:** `doctor --live` and `search "Python 3.14 release notes" -k 5`

`doctor --live`:
```json
"live": {"status": "partial", "ms": 4695, "providers": ["mwmbl", "wikipedia"], "error": null}
```
Note: `ddg` is absent from the live provider list but `error` is `null` — the per-provider failure is not surfaced by `doctor`.

`search`:
```json
"prov": ["mwmbl", "wikipedia"],
"fail": {"ddg": "TimeoutError"}
```

**Impact:** general-web provider unavailable; only MWMbl + Wikipedia answered. This is the direct cause of the off-topic search results and the failed Python 3.14 research run. It reproduced on both attempts, so it is not a one-off transient in this environment.

---

## 2. `fetch_failed:FetchError` during research (recurring)

**Where:** `research "What is the purpose of example.com?"` and `research "What are the major new features in Python 3.14?"`

```json
"warn": ["fetch_failed:FetchError"]
```

**Impact:** at least one candidate source could not be fetched and was silently dropped; the payload contains no URL identifying which source failed. Both runs still returned findings from other sources.

---

## 3. `no_reliable_result` on `extract https://example.com -q "What is this page?"`

```json
{"status": "no_reliable_result", "ps": [], "tok": 74,
 "warn": ["low_content", "no_query_match"]}
```

**Not a crash.** Zero passages were selected because the query shares no lexical terms with the 156-character page. Same URL with `--full` returned `status: ok`, and with `-q "documentation examples domain"` returned the correct passage. Diagnosed as query-selection strictness, not fetch/extract failure.

---

## 4. `no_links_found` on `crawl https://example.com --mode map`

```json
"warn": ["no_links_found"]
```

**Not a bug.** Ground-truth fetch of `https://example.com` (577 bytes) confirmed the live page has no `<a>` elements and no iana.org link. The warning is accurate and the single-URL result is correct.

---

## 5. Research coverage gaps (self-reported)

| Command | `gaps` |
|---|---|
| `research "What is the purpose of example.com?"` | `["no_source_for:purpose"]` |
| `research "What are the major new features in Python 3.14?"` | `["no_source_for:3.14"]` |

The second gap is correct and matches the evidence (no source about 3.14 features was retrieved). The first gap is questionable: a `Purpose`-section quote from the Wikipedia example.com article *was* returned, yet the tool still reports no source for `purpose`. Possible gap-accounting inconsistency; not verified against source code behaviour beyond this observation.

---

## 6. Search relevance warning

```json
"warn": ["duplicate_text_removed", "off_topic_filtered:4"]
```

`off_topic_filtered:4` was emitted, yet the 5 returned results still include two clearly off-topic Wikipedia pages (`History of Python`, `CPython`) for a "Python 3.14 release notes" query. Recorded as a relevance-quality observation, not an error.

---

## Environment note (not an error)

Raw stdout files are UTF-8. Windows console code page is 437, so naive `Get-Content` renders non-breaking spaces and curly quotes as `�`. Decoding the same bytes as UTF-8 yields clean text (e.g. `Website\u00A0type`, `PEP 8`). No data corruption in the CLI output.

---

## What did *not* happen

- No dependency resolution failure, no hatchling build failure, no DLL/native import error (`lxml`, `pymupdf`, `tiktoken` all imported fine).
- No authentication prompt, no paid API call, no credit spend.
- No command exceeded its timeout, and no command was skipped or replaced with a simulated result.
