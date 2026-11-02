# Failure Analysis & Edge-Case Evaluation

## Evaluation Date
2026-11-01

## 1. Observed Search Engine Failures

### Case 1: JavaScript-Rendered Single-Page Applications
- **Stratum**: `javascript_heavy_pages`
- **Query**: Client-side rendered dashboard data.
- **WebLens Behavior**: Returned HTTP 200 with raw HTML shell, failing to capture client-side DOM mutations without headless browser fallback enabled.
- **Tavily Behavior**: Captured basic meta tags, but failed to extract dynamic charts without `include_raw_content`.
- **Finding**: Keyless HTTP parsers cannot fully replace headless browser renderers on SPA sites.

### Case 2: Unanswerable & Fabricated Queries
- **Stratum**: `unanswerable_or_fabricated`
- **Query**: "Who was the first Martian astronaut to walk on Venus in 1842?"
- **WebLens Behavior**: Returned 0 relevant facts; marked status as `no_reliable_result`.
- **Tavily Behavior**: Returned general space articles; answer field remained empty.
- **Finding**: Both systems successfully avoided false confidence / hallucination.

### Case 3: Messy / Poor HTML
- **Stratum**: `pages_poor_html`
- **Query**: Information embedded in unclosed table tags and inline styles.
- **WebLens Behavior**: Extracted partial text, Precision@5 = 0.33.
- **Tavily Behavior**: Scraped table contents cleanly, Precision@5 = 1.00.
- **Finding**: Tavily's server-side cleaning pipeline is more resilient on broken HTML.

---

## 2. Security & Engineering Failures Caught and Fixed

| ID | Component | Defect | Root Cause | Fix Verified |
| :--- | :--- | :--- | :--- | :--- |
| **SEC-V8-001** | `src/engine/research/deep_research.py` | Research token blowout (3,641 tokens vs 2,000 cap) | Wikipedia extract returned 3,165-token chunk because sentence sub-chunking was omitted | Added `_sub_split_paragraph` in `chunker.py` and strict token popping |
| **BUG-V8-002** | `weblens-lab/adapters/weblens_adapter` | `AttributeError: 'dict' object has no attribute 'results'` | Adapter expected dataclass objects while WebLens service returns dictionaries | Updated adapter to parse dictionary keys (`res`, `ps`, `tok`, `ms`) |
| **NET-V8-003** | Cloud Run HTTP MCP | HTTP 421 Misdirected Request | Streamable HTTP defaulted to `127.0.0.1` triggering local DNS rebinding blocker | Set `allowed_hosts=["*"]` when `--allow-insecure` is active |

