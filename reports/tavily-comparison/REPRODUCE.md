# Reproduce

**Campaign:** `stage7-20261028-a4a64151`  
**Working directory for benchmark commands:** `weblens/`  
**Report directory:** `../reports/tavily-comparison/`

These commands reproduce the campaign structure. A full paid rerun requires a Tavily key and enough credits. Do not print the key. The recorded run consumed 381 credits and left 449; a rerun is not free.

---

## 1. Prerequisites

- Windows 11 x64 (the recorded environment).
- Python 3.14.0 via `uv`.
- Playwright Chromium for the browser fixture.
- `WEBLENS_TAVILY_API_KEY` in the environment or `weblens/.env`.
- Network access to Tavily, DuckDuckGo, Mwmbl, and Wikipedia.

Verify the key without printing it:

```powershell
cd "C:\Users\ACER\Downloads\Broswer for ai agnets\weblens"
uv run python -c "from benchmarks.stage7_common import load_tavily_key; k=load_tavily_key(); import hashlib; print('present', bool(k), 'sha256_prefix', hashlib.sha256(k.encode()).hexdigest()[:12])"
```

Expected: `present True` and a short fingerprint. Never echo the key itself.

---

## 2. Verify the frozen dataset

```powershell
cd "C:\Users\ACER\Downloads\Broswer for ai agnets"
Get-FileHash reports\tavily-comparison\data\stage7_dataset.jsonl -Algorithm SHA256
```

Expected SHA-256:

```text
a4a64151fbdbda850a9de128bb7f83ec67f126b633aac42488c6f0b9296a9b21
```

The manifest and card are at:

- `reports/tavily-comparison/data/stage7_manifest.json`
- `reports/tavily-comparison/data/DATASET-CARD.md`

The 10,000-row synthetic corpus is excluded. Do not substitute it for the 108 hand-labelled rows.

---

## 3. Record the environment

```powershell
cd "C:\Users\ACER\Downloads\Broswer for ai agnets\weblens"
uv run python -c "import json, platform, sys, os, subprocess; print(json.dumps({'python':sys.version,'platform':platform.platform(),'cpu_count':os.cpu_count(),'commit':subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()},indent=2))"
```

Record the output in the run log. The current fingerprint is in `reports/redteam/00-environment-fingerprint.json`.

---

## 4. Campaign commands

Run in order. The harness is resumable; do not mix a partial old run with a new campaign ID.

### 4.1 Dataset rebuild (optional; changes the hash)

```powershell
cd "C:\Users\ACER\Downloads\Broswer for ai agnets\weblens"
uv run python benchmarks/stage7_dataset.py
```

Only run this if you intend to create a new frozen dataset. It will change the hash and invalidate the recorded evidence.

### 4.2 Smoke (small, paid)

```powershell
uv run python -m benchmarks.stage7_run --phase search --split dev --limit 1 --tag _smoke
uv run python -m benchmarks.stage7_run --phase research --split dev --limit 1 --tag _smoke
```

Smoke records are preserved but excluded from headline scoring.

### 4.3 Dev search and research

```powershell
uv run python -m benchmarks.stage7_run --phase search --split dev
uv run python -m benchmarks.stage7_run --phase research --split dev
```

Expected: 243 search records and 162 research records.

### 4.4 Provider-raw, extraction, crawl/map, load, browser

```powershell
uv run python -m benchmarks.stage7_run --phase provider_raw
uv run python -m benchmarks.stage7_run --phase extraction
uv run python -m benchmarks.stage7_run --phase crawl_map
uv run python -m benchmarks.stage7_run --phase load
uv run python -m benchmarks.stage7_run --phase browser_fixture
```

Expected: 60 provider-raw records, 10 extraction records, 4 crawl/map records, 6 load records, 6 browser records.

### 4.5 Sealed test (open once)

```powershell
uv run python -m benchmarks.stage7_run --phase search --split test
uv run python -m benchmarks.stage7_run --phase research --split test
```

Expected: 81 test search records and 54 test research records. Do not use the test split to change code, labels, thresholds, or provider settings.

### 4.6 Analysis

```powershell
uv run python -m benchmarks.stage7_analyze
```

Expected outputs:

- `reports/tavily-comparison/data/analysis.json`
- `reports/tavily-comparison/QUALITY-RESULTS.json`
- `reports/tavily-comparison/PERFORMANCE-RESULTS.json`
- `reports/tavily-comparison/COST-AND-TOKEN-RESULTS.json`

### 4.7 Controlled security/reliability harness

```powershell
uv run python -m benchmarks.stage7_security
```

Expected: 40 records in `reports/tavily-comparison/raw/security.jsonl`; 38 PASS, 2 FAIL (429/503 retry). The harness uses only owned loopback fixtures. It does not attack Tavily or third parties.

### 4.8 Usage check

```powershell
@'
import asyncio, json, httpx
from benchmarks.stage7_common import load_tavily_key, tavily_usage

async def main():
    key = load_tavily_key()
    async with httpx.AsyncClient(timeout=20) as client:
        print(json.dumps(await tavily_usage(client, key), indent=2))

asyncio.run(main())
'@ | uv run python -
```

Do not print the key. Record account usage and remaining credits. Stop paid work if remaining credits fall below 200.

---

## 5. Verification

### 5.1 Test suite

```powershell
cd "C:\Users\ACER\Downloads\Broswer for ai agnets\weblens"
uv run pytest -q
uv run ruff check .
```

The recorded campaign used the current `weblens` test suite plus the added `age_days` regression test. A full root-repository suite is separate; do not claim it passed unless it was actually run.

### 5.2 Artifact hashes

```powershell
cd "C:\Users\ACER\Downloads\Broswer for ai agnets"
Get-ChildItem reports\tavily-comparison -Recurse -File | Get-FileHash -Algorithm SHA256
```

Compare against `reports/tavily-comparison/data/artifact-integrity.json`.

### 5.3 Secret scan

```powershell
cd "C:\Users\ACER\Downloads\Broswer for ai agnets"
Get-ChildItem reports\tavily-comparison,reports\redteam,reports\extreme-benchmark -Recurse -File |
  Select-String -Pattern 'tvly-[A-Za-z0-9_-]{12,}','Bearer\s+[A-Za-z0-9._-]{20,}','sk-[A-Za-z0-9]{20,}'
```

Expected: no output. Key names and `present` booleans are fine. If the pattern matches a real value, stop and rotate the credential; do not paste the value into a report.

---

## 6. Known reproduction limits

- A full rerun is paid; the recorded campaign used 381 credits.
- The usage endpoint can return HTTP 429; use the final check and preserve the raw response.
- The 108-query dataset is small and has no human relevance judgments.
- The 10,000-row corpus is not valid ground truth.
- Full MCP conformance was not completed on this Windows host.
- No OS/container/browser sandbox was configured.
- Brave was not measured because `WEBLENS_BRAVE_API_KEY` was blank.
