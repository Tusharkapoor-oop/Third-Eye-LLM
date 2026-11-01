# WebLens Python API Reference

## 1. Top-Level Facade: `weblens.service.WebLens`

### `WebLens(settings: Settings | None = None)`
Initializes the unified WebLens engine composing search, extraction, crawling, caching, and research subsystems.

#### Methods:
- `async search(query: str, *, max_results: int = 5, freshness: str | None = None, domains: list[str] | None = None, exclude_domains: list[str] | None = None, max_tokens: int | None = None) -> dict[str, Any]`
  Searches the web via configured providers. Trims snippets to caller token budget. Returns JSON dict with keys: `status`, `q`, `n`, `res` (list of `{t, u, s, d}`), `ms`, `tok`.
- `async extract(url: str, *, query: str | None = None, max_tokens: int | None = None, full: bool = False) -> dict[str, Any]`
  Fetches and extracts passages from a URL. Returns JSON dict with keys: `status`, `u`, `passages` (list of `{p, s, at, h}`), `tok`, `ms`.
- `async crawl_site(url: str, *, mode: str = "map", max_pages: int = 10, max_depth: int = 2, query: str | None = None, max_tokens: int | None = None) -> dict[str, Any]`
  Performs polite website mapping (`mode="map"`) or bounded crawling (`mode="crawl"`).
- `async deep_research(query: str, *, max_tokens: int | None = None, max_searches: int = 4, max_pages: int = 6) -> dict[str, Any]`
  Executes iterative research loop with claim-level citations and conflict detection.
- `async doctor(*, live: bool = False) -> dict[str, Any]`
  Returns diagnostic status, active providers, cache statistics, and tokenizer configurations.
- `async close() -> None`
  Gracefully releases HTTP connections and SQLite cache handles.

---

## 2. Application Modules: `weblens.apps`

### 2.1 `weblens.apps.crawl2rag.Crawl2RAG`
- `async ingest(start_url: str, *, max_pages: int = 15, max_depth: int = 2) -> CrawlResult`
  Crawls and indexes website text into a local SQLite FTS5 database.
- `async query(question: str, *, top_k: int = 5) -> RAGAnswer`
  Queries the local knowledge base using BM25 ranking and returns verbatim cited text passages.

### 2.2 `weblens.apps.company.CompanyResearcher`
- `async research_company(name_or_domain: str) -> CompanyProfile`
  Extracts verified corporate overview, leadership, products, news, competitors, and risks. Returns `not_found` for non-existent companies.

### 2.3 `weblens.apps.market.MarketResearcher`
- `async analyze_asset(ticker_or_company: str) -> MarketReport`
  Synthesizes market intelligence from regulatory filings and official disclosures. Returns `not_available` when real-time figures cannot be verified.

### 2.4 `weblens.apps.sheets.SheetsEnricher`
- `async enrich_table(input_path: str, column_specs: dict[str, str], output_path: str) -> EnrichmentSummary`
  Enriches tabular datasets row by row. Prepend `'` to dangerous formula characters (`=`, `+`, `-`, `@`) to block formula injection.

### 2.5 `weblens.apps.chat.ResearchChatSession`
- `async send_message(message: str) -> ChatTurnResponse`
  Maintains multi-turn context within a bounded token window and verifies all citations.

### 2.6 `weblens.apps.meeting.MeetingPrepAgent`
- `async prepare_meeting(attendees: list[str], context: str) -> MeetingBrief`
  Generates attendee background dossiers strictly from verified public professional sources. Refuses private personal information probes.

