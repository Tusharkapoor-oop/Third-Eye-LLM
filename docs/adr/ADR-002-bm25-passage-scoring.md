# ADR-002: BM25 Passage Scoring with Verifiable Exact Spans

## Status
Accepted

## Context
Standard web extraction tools either return entire web pages (3,000–15,000 tokens of markdown) or rely on LLMs to generate prose summaries. Whole-page extraction inflates LLM context consumption, causes attention degradation, and drastically increases prompt latency. Conversely, black-box summaries detach claims from the source text and introduce hallucination risks without verifiable grounding.

## Decision
Implement a two-stage passage retrieval pipeline:
1. Extract clean document text via Trafilatura.
2. Segment the document into overlapping token-aware chunks (150 words per chunk with a 50-word stride).
3. Score each chunk using Okapi BM25 (`k1=1.5`, `b=0.75`) against the user's specific query terms.
4. Return only the top $k$ passages (default 3 passages, hard cap 1,500 tokens).
5. Attach exact character offsets (`char_start`, `char_end`) to every returned passage, guaranteeing that the passage is an unadulterated verbatim substring of the source page.
6. Prohibit uncalibrated confidence/similarity floating-point scores.

## Consequences
- **Positive**: Reduces context token usage by 80–90%; enables instantaneous fact verification; eliminates fake accuracy; zero GPU/VRAM requirement.
- **Negative**: Queries that rely purely on high-level conceptual synonyms without lexical overlap may score lower than dense vector embeddings.
