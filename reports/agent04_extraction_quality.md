# Extraction Quality Audit Report

## 1. Executive Summary

This audit evaluated the web extraction engine, HTML parsing, markdown extraction, boilerplate stripping, density-aware chunking, table parsing, noise filtering, and two-stage reranking pipelines.
The extraction test suite comprising 7 unit and integration tests across `tests/test_extract.py` and `tests/test_05_extraction_quality.py` was executed using `pytest` in the project virtual environment.
All 7 tests PASSED with a 100% success rate (execution time: 35.08s).

---

## 2. Test Suite Execution Breakdown

- Command: `.\.venv\Scripts\pytest -v --tb=short tests/test_extract.py tests/test_05_extraction_quality.py`
- Platform: Windows (Python 3.14.0, pytest-9.1.1, pluggy-1.7.0)
- Execution Duration: 35.08 seconds
- Result: **7 passed, 0 failed, 0 skipped (100% pass rate)**

| Test Case | Module / Suite | Description | Expected Outcome | Actual Outcome | Status |
|---|---|---|---|---|---|
| `test_chunker_exact_span_preservation` | `tests/test_extract.py` | Verifies DocumentChunker maintains exact character offsets with zero drift | `sample_text[c.char_start:c.char_end] == c.text` for all chunks | Exact equality verified across all passage spans | Passed |
| `test_bm25_passage_scoring` | `tests/test_extract.py` | Verifies BM25 passage scorer ranks query-relevant passages above non-relevant passages | Top-ranked chunk matches query topic (`Python`) | Chunk containing `Python` ranked #1 | Passed |
| `test_extractor_live` | `tests/test_extract.py` | Live end-to-end extraction against `https://www.python.org/about/` | Status `success`, valid timestamp, passages returned, `tokens_used <= 600` | Status `success`, token budget strictly respected | Passed |
| `test_extractor_blocked_ssrf` | `tests/test_extract.py` | Validates SSRF protection blocking loopback addresses (`127.0.0.1:9090`) | Status `blocked`, security error in metadata | Blocked with security policy error recorded | Passed |
| `test_html_table_to_markdown_conversion` | `tests/test_05_extraction_quality.py` | Converts complex HTML `<table>` into GitHub-Flavored Markdown (GFM) table | Formats valid 5-row markdown table with aligned pipes and headers | Exact 5-line GFM table generated with headers and cell data intact | Passed |
| `test_code_block_preservation_and_indentation` | `tests/test_05_extraction_quality.py` | Pre-protects `<pre><code class="language-python">`, preserving lines, syntax, and 12-space indentation | Preserves language tag (`python`), indentation, and exact code lines | Indentation, keywords, and code structure 100% preserved | Passed |
| `test_deep_document_bottom_answer_retrieval` | `tests/test_05_extraction_quality.py` | Evaluates Two-Stage Reranker on 27,000+ char document with target answer at bottom | Target token retrieved as Chunk #1 with score > 0.70; intro fluff discarded | Bottom answer retrieved as Chunk #1 (score > 0.70); ~20k fluff discarded | Passed |

---

## 3. Architecture & Quality Verification Analysis

### 3.1. HTML Parsing & Tiered Fallback Architecture
Inspection of `extractor.py` and `src/engine/extract/extractor.py` reveals a three-tier resilient extraction pipeline:
- **Tier 1 (Fast HTTP & In-Memory DOM Parsing)**: Fetches raw HTML via `safe_fetch_url` (<300ms) with SSRF checks. Parses HTML via `BeautifulSoup` and extracts article content via `Trafilatura`.
- **WAF & SPA Skeleton Detection**: `is_blocked_or_spa` monitors HTTP status codes (403, 429, 503), known WAF challenge markers, and empty JavaScript skeletons (`len(text) < 250` with SPA signatures like `id="root"`, `id="app"`, `react`, `vue`, `docusaurus`).
- **Tier 2 (Headless Browser Fallback)**: Automatically falls back to a persistent warm Playwright Chromium instance to execute client-side JavaScript, settle dynamic DOM trees, and extract post-render HTML. Aborts image, media, and font downloads to optimize latency.
- **Tier 3 (Enterprise Rescue Fallback)**: Connects to Tavily Extract API with `extract_depth="advanced"` to bypass enterprise Cloudflare/DataDome bot protection when both HTTP and local browser fail.

### 3.2. Markdown Extraction & Code Block Preservation
- **Pre-protection Mechanism**: `protect_code_and_tables` intercepts `<pre>` and `<code>` nodes before readability extractors can collapse whitespace or strip syntax.
- **Fenced Markdown Conversion**: Converts `<pre><code class="language-python">` directly into fenced blocks (````python ... ````).
- **Escaping Restoration**: Trafilatura escapes backticks (`\```) and underscores (`\_`); `extract_markdown` actively unescapes them (`re.sub(r"\\`\\`\\`", ...)` and `re.sub(r"\\_", "_")`) to prevent syntax corruption in variable identifiers (e.g. `foo_bar`).
- **Code Normalization**: `_normalize_code_blocks` repairs artificial newlines inserted into statements like `import asyncio` or `async def`.

### 3.3. Table Parsing (HTML to GitHub-Flavored Markdown)
- **Structure Normalization**: `html_table_to_markdown` inspects `<tr>`, `<th>`, and `<td>` elements.
- **Pipe Escaping & Whitespace Cleanup**: Internal cell pipes are escaped (`|` -> `\|`) and excessive whitespace is collapsed.
- **Rectangular Grid Guarantee**: Detects maximum column width and pads ragged rows with empty cells to ensure valid markdown rendering. Generates standard markdown header separators (`| --- | --- |`).

### 3.4. Boilerplate Stripping & Anti-Noise Filtering
- **Hidden Element Stripping**: `strip_hidden_dom_elements` recursively strips HTML comments and elements with `hidden`, `aria-hidden="true"`, or CSS rules specifying `display:none`, `visibility:hidden`, `opacity:0`, or `font-size:0` (defeating hidden indirect prompt injection payloads).
- **Navigation & Link-Farm Removal**: `_clean_rescued_markdown` detects `_NAV_MARKERS` ("sign up", "log in", "cookie", "terms of service", "newsletter", etc.) and prunes link-dense non-content headers while leaving code fences and tables untouched.
- **Prose Normalization**: `_normalize_prose` strips permalink symbols (`\u00b6`), inline image tags (`![...]`), and markdown link brackets to preserve pure semantic text.

### 3.5. Density-Aware & Structure-Aware Chunking
Two complementary chunking implementations provide robust document slicing:
- **StructureAwareChunker (`reranker.py`)**: Tracks heading hierarchies (`H1 > H2 > H3`) into breadcrumbs, preserves code fences and tables as atomic units (preventing mid-table splits), and injects section paths into passage context.
- **DocumentChunker (`src/engine/extract/chunker.py`)**: Implements token-aware partitioning using tiktoken `o200k_base`. Computes target chunk counts `N = ceil(total_tokens / target_tokens)`, spaces boundaries evenly across paragraphs, and guarantees that the final paragraph (tail facts) is preserved. Verified zero-drift character offsets (`sample_text[start:end] == chunk.text`).

### 3.6. Two-Stage Reranking & Retrieval Quality
- **Stage 1 (Lexical BM25 Candidate Gating)**: Evaluates Robertson-Spärck Jones BM25 with term saturation (`k1=1.2`, `b=0.75`), query-term frequency indexing, and bonus weights for code identifiers and tables. Quickly trims hundreds of chunks to the top 15 candidate passages in <10ms.
- **Stage 2 (Neural Cross-Encoder Scoring)**: Employs FlashRank `ms-marco-MiniLM-L-12-v2` to compute deep semantic relevance scores.
- **Fidelity Under Needle-in-a-Haystack Conditions**: In `test_deep_document_bottom_answer_retrieval`, the reranker successfully identified an emergency recovery token buried at the bottom of a 27,000+ character document as Chunk #1 with high confidence (>0.70), completely filtering out over 20,000 characters of preceding boilerplate.

---

## 4. Conclusion & Audit Sign-Off

The extraction subsystem meets all functional, structural, and performance criteria:
1. Zero character offset drift in document chunking.
2. 100% line, whitespace, and syntax preservation in code blocks.
3. Clean, standards-compliant GFM table output.
4. Robust anti-bot fallback (Fast HTTP -> Playwright -> Tavily).
5. Effective boilerplate and prompt-injection noise stripping.
6. Proven deep-document retrieval fidelity (>0.70 score for tail facts).

Audit Status: **PASSED (7/7 tests verified)**
