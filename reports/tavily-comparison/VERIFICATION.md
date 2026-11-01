# Verification Record

**Campaign:** `stage7-20261028-a4a64151`  
**Verified:** 2026-11-01 (local)  
**Environment:** Windows 11, Python 3.14.0, commit `902415d49f8da502b9de0e1c78da7f5777a1d2f8`

This record separates passing checks from checks that are not clean. It does not convert a type-check failure into a pass.

---

## 1. Test suite

```powershell
cd "C:\Users\ACER\Downloads\Broswer for ai agnets\weblens"
uv run pytest -q --junitxml=..\reports\tavily-comparison\data\pytest.xml
```

Result from `data/pytest.xml`:

| Field | Value |
|---|---:|
| tests | 163 |
| failures | 0 |
| errors | 0 |
| skipped | 0 |
| duration | 7.865 s |
| timestamp | 2026-11-01T18:40:27+05:30 |

The added regression test is `tests/test_extract.py::test_age_days_accepts_iso_and_rejects_invalid`.

---

## 2. Lint and lock

```powershell
uv run ruff check .
uv lock --check
```

Result:

- `ruff check .`: **All checks passed**.
- `uv lock --check`: **Resolved 75 packages**; lock is current.

`ruff format --check` was not run as a release gate; formatting is not claimed as verified.

---

## 3. Type check

```powershell
uv run pyright src/weblens/extract/html.py tests/test_extract.py
```

Result: **7 errors, 0 warnings, 0 informations — FAIL**.

The errors are outside the changed `age_days()` lines:

- `src/weblens/extract/html.py:328` — `_clean_text` argument union (pre-existing).
- `tests/test_extract.py:104` — seven `ExtractOutcome` fixture argument errors (pre-existing).

No claim of a clean repository type check is made. Full-repository `pyright` was not re-run as a release gate; earlier campaign notes report additional pre-existing errors in `crawl/crawler.py` and `extract/passages.py`.

---

## 4. Security harness

```powershell
uv run python -m benchmarks.stage7_security
```

Result:

- run `stage7-security-f432267e3e`
- 40 records
- 38 PASS
- 2 FAIL (`REL-RETRY-001`, `REL-RETRY-002`)
- 0 critical, 0 high, 1 medium finding covering 2 failed cases, 1 low residual finding

The two failures are real and preserved. The harness was not altered to make them pass.

A prior run `stage7-security-25d2ce55f7` was recorded under Python 3.13.15. It produced the same 38 PASS / 2 FAIL and is preserved at `raw/security_py313.jsonl` and `raw/security_summary_py313.json`; the current run is under Python 3.14.0.

---

## 5. Secret scan

Scanned `reports/tavily-comparison/`, `reports/redteam/`, `reports/extreme-benchmark/`, and the archive README for:

- `tvly-...` live-key format,
- `Bearer ...` tokens,
- `sk-...` model-key format.

Result: **0 matches** for all three patterns.

`OPENAI_API_KEY` appears in retrieved web content in `raw/search_dev.jsonl` as code examples (`setx OPENAI_API_KEY "<yourkey>"`, `process.env.OPENAI_API_KEY`), not as a credential value. The actual Tavily key is in ignored `.env` files and is not present in the reports.

No key value was printed during verification.

---

## 6. Usage check

Final Tavily check at `2026-10-28T10:25:24Z`:

- plan: `Researcher`
- account usage: `551/1000`
- remaining: `449`
- campaign delta: `381` credits
- cap: `420`; hard stop: `200` remaining
- result: within budget, above stop

`raw/usage_final.json` is authoritative. The mid-campaign 429 is preserved in the methodology as a limitation.

---

## 7. Artifact integrity

`data/artifact-integrity.json` lists SHA-256 hashes for **60** current report artifacts and raw record counts:

| File | Records |
|---|---:|
| `search_dev.jsonl` | 243 |
| `search_test.jsonl` | 81 |
| `research_dev.jsonl` | 162 |
| `research_test.jsonl` | 54 |
| `provider_raw.jsonl` | 60 |
| `extraction.jsonl` | 10 |
| `extraction_pre_fix.jsonl` | 10 |
| `browser_fixture.jsonl` | 6 |
| `load.jsonl` | 6 |
| `crawl_map.jsonl` | 4 |
| `security.jsonl` | 40 |
| `security_py313.jsonl` | 40 |
| `search_dev_smoke.jsonl` | 3 |
| `research_dev_smoke.jsonl` | 2 |

The integrity file does not include its own hash. Regenerate it after any report edit.

---

## 8. Not verified

- Full MCP conformance (official runner not completed on this Windows host).
- OS/container/browser sandbox isolation.
- Independent penetration test or code audit.
- Production capacity or sustained load.
- Human relevance judgments or true recall.
- 500-query or 10,000-query campaign.
- USD cost (no invoice or per-credit price).
