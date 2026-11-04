# V14 Forensic Test Addendum

## Current executable result

Command:

```powershell
$files=(Get-ChildItem tests -Filter 'test_v14_*.py' | ForEach-Object { $_.FullName })
.venv\Scripts\python.exe -m pytest -q $files --tb=short
```

Result: **28 passed** in 34.37 seconds.

## What this proves

- Browser session creation/closure, permission checks, and SSRF rejection are
  exercised with the local Playwright runtime.
- Geographic coordinate validation, Haversine routes, and mocked Nominatim
  caching are exercised.
- DOCX/PDF/PPTX/XLSX/CSV/Markdown/TXT generation and structural validation are
  exercised locally.
- Crawl/research lifecycle state transitions, cancellation, robots parsing,
  graph fields, and document export are exercised with mocked providers.
- EventStore aggregation and zero-count truth checks are exercised.

## What this does not prove

- Live Nominatim availability or rate-limit behavior.
- Live multi-page crawl against an authorized public site.
- Live Gemini/Tavily synthesis in research.
- Deployed browser isolation or external-agent MCP interaction.
- A dashboard frontend or REST resource surface.
- That every root MCP call is wired to EventStore outside the tested wrapper.

Disposition: the affected capabilities are **PARTIALLY_VERIFIED**, not
automatically VERIFIED solely from the 28-test result.
