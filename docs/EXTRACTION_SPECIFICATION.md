# WebLens Content Extraction Specification

## 1. Overview

The WebLens Content Extraction subsystem transforms raw, untrusted HTML, XML, JSON, and PDF documents into structured, clean, and evidence-dense textual representations for downstream AI agents.

Raw HTML is predominantly clutter: navigation bars, footer links, cookie consents, advertisements, tracking pixels, and CSS/JS scripts represent 70% to 90% of page bytes. WebLens strips this noise while strictly preserving semantic content, code snippets, and tabular data.

---

## 2. Processing Pipeline

```
               [ Raw HTTP Response Stream (<= 2MB) ]
                                |
                                v
               [ Content-Type & Encoding Detection ]
                                |
            +-------------------+-------------------+
            |                                       |
    [ HTML / XML Document ]                 [ PDF Document ]
            |                                       |
            v                                       v
    [ DOM De-cluttering ]                   [ PyMuPDF / PDF Parser ]
  - Strip <script>, <style>               - Text block extraction
  - Strip <nav>, <header>, <footer>       - Page boundary tracking
  - Strip ads, modals, trackers                     |
            |                                       |
            +-------------------+-------------------+
                                |
                                v
               [ Table & Code Fence Preservation ]
             - Convert <table> -> Markdown Table
             - Convert <pre>/<code> -> Fenced Code
                                |
                                v
               [ Main Body Readability Engine ]
                   (Trafilatura & LXML)
                                |
                                v
               [ Passage Chunking & Token Windowing ]
             - 512 token chunks, 128 token overlap
             - Character-span offsets calculated
                                |
                                v
               [ Cryptographic Hash & Provenance ]
                 (SHA-256 computed on raw input)
```

---

## 3. Extraction Standards & Invariants

### 3.1 DOM De-cluttering Rules
- **Prohibited Elements:** The following tags and their descendants are discarded prior to text parsing:
  `<script>`, `<style>`, `<noscript>`, `<iframe>`, `<svg>`, `<canvas>`, `<nav>`, `<header>`, `<footer>`, `<aside>`, `<form>`.
- **Boilerplate Suppression:** Common cookie banners (`id="cookie-banner"`, `class="gdpr-consent"`), newsletter popups, and related-article widgets are identified and pruned via CSS selector heuristics.

### 3.2 Table Preservation Specification
Tables convey dense factual comparisons that are ruined when flattened to plain text. WebLens parses HTML `<table>` elements and renders standard GitHub-flavored Markdown tables:
- Header row (`<th>`) formatted with dividing delimiter (`|---|---|`).
- Cell contents (`<td>`) trimmed of extraneous whitespace and stripped of nested formatting.
- Merged cells (`colspan`, `rowspan`) expanded to preserve column alignment.

### 3.3 Code & Preformatted Blocks
Blocks wrapped in `<pre>` or `<code>` are preserved with indentation and language hints:
```markdown
```language
<verbatim code content>
```
```

### 3.4 PDF Extraction Specification
When `Content-Type: application/pdf` is encountered:
- WebLens extracts text page-by-page, annotating each text section with its 1-based page number (`[Page X]`).
- Visual column layouts are reconstructed into linear reading order.
- Embedded vector tables are parsed into structured markdown blocks.

---

## 4. Passage Chunking & Verbatim Anchors

Downstream AI agents operate under finite context budgets. WebLens breaks extracted text into discrete passages:
- **Chunk Size:** Configurable, default 512 tokens.
- **Overlap:** 128 tokens to prevent losing context across sentence boundaries.
- **Verbatim Anchors:** Every chunk retains absolute character offsets (`char_start`, `char_end`) relative to the raw extracted document text.
- **Passage Scoring:** Passages are scored against query keywords using BM25 and exact lexical overlap, ensuring only the top-$K$ highest-density evidence spans are forwarded to the agent.

