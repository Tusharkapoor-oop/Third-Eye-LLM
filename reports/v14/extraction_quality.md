# Extraction Quality

**Status: PARTIALLY_VERIFIED.** Root and `src/engine` extractors use HTTP
fetching, main-content extraction, protected code/table handling, WAF checks,
query-guided chunks, and optional browser fallback. Current live documentation
smokes and extraction tests demonstrate meaningful content and exact passages.

**Open gates:** unified metadata/JSON-LD/link contract, PDF/document coverage,
browser-rendered SPA release test, and extraction precision/recall on a frozen
held-out corpus.
