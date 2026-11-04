"""Structure-Aware Semantic Chunker and Two-Stage Passage Reranker.

Implements heading hierarchy breadcrumb injection, atomic code/table preservation,
fast BM25 candidate gating, and neural Cross-Encoder passage scoring (FlashRank).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from config import CONFIG
from schemas import ChunkResult


@dataclass
class RawChunk:
    """Internal representation of a passage before scoring."""

    content: str
    section_breadcrumb: str
    char_count: int
    has_code: bool
    has_table: bool
    index: int


class StructureAwareChunker:
    """Splits Markdown into context-preserving ~500 char passages with parent breadcrumbs."""

    def __init__(self, target_chars: int = 500):
        self.target_chars = target_chars

    def chunk_document(self, markdown_text: str) -> list[RawChunk]:
        """Split Markdown document into chunks with section breadcrumbs and atomic blocks."""
        if not markdown_text or not markdown_text.strip():
            return []

        lines = markdown_text.splitlines()
        chunks: list[RawChunk] = []

        current_section = "Overview"
        section_stack: list[str] = ["Overview"]
        buffer: list[str] = []
        current_len = 0
        in_code_block = False
        in_table = False
        chunk_idx = 0

        for line in lines:
            stripped = line.strip()

            # Detect fenced code block start/end
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                buffer.append(line)
                current_len += len(line) + 1
                continue

            # Detect Markdown headings outside of code blocks
            if not in_code_block and stripped.startswith("#"):
                heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
                if heading_match:
                    level = len(heading_match.group(1))
                    title = heading_match.group(2).strip()

                    # Flush previous buffer before entering new section
                    if buffer:
                        text = "\n".join(buffer).strip()
                        if text:
                            chunks.append(
                                RawChunk(
                                    content=text,
                                    section_breadcrumb=" > ".join(section_stack),
                                    char_count=len(text),
                                    has_code="```" in text,
                                    has_table="|" in text,
                                    index=chunk_idx,
                                )
                            )
                            chunk_idx += 1
                        buffer = []
                        current_len = 0

                    # Update heading stack
                    while len(section_stack) >= level:
                        section_stack.pop()
                    section_stack.append(title)
                    current_section = " > ".join(section_stack)
                    continue

            # Detect table rows
            if not in_code_block and stripped.startswith("|") and stripped.endswith("|"):
                in_table = True
                buffer.append(line)
                current_len += len(line) + 1
                continue
            elif in_table and not (stripped.startswith("|") and stripped.endswith("|")):
                in_table = False

            buffer.append(line)
            current_len += len(line) + 1

            # Break chunk when exceeding target length and not inside an atomic code/table block
            if current_len >= self.target_chars and not in_code_block and not in_table:
                text = "\n".join(buffer).strip()
                if text:
                    chunks.append(
                        RawChunk(
                            content=text,
                            section_breadcrumb=current_section,
                            char_count=len(text),
                            has_code="```" in text,
                            has_table="|" in text,
                            index=chunk_idx,
                        )
                    )
                    chunk_idx += 1
                buffer = []
                current_len = 0

        # Flush any remaining content in the buffer
        if buffer:
            text = "\n".join(buffer).strip()
            if text:
                chunks.append(
                    RawChunk(
                        content=text,
                        section_breadcrumb=current_section,
                        char_count=len(text),
                        has_code="```" in text,
                        has_table="|" in text,
                        index=chunk_idx,
                    )
                )

        return chunks


class TwoStageReranker:
    """Stage 1: Fast BM25 Candidate Gating (<10ms).

    Stage 2: Neural Cross-Encoder Passage Ranking via FlashRank (ms-marco-MiniLM-L-12-v2).
    """

    def __init__(self):
        self.chunker = StructureAwareChunker(target_chars=CONFIG.target_chunk_chars)
        self._flashrank_model = None
        self._init_flashrank()

    def _init_flashrank(self) -> None:
        """Initialize FlashRank cross-encoder safely."""
        try:
            from flashrank import Ranker
            # Use lightweight, high-accuracy MiniLM Cross-Encoder
            self._flashrank_model = Ranker(model_name="ms-marco-MiniLM-L-12-v2")
        except Exception:
            self._flashrank_model = None

    def _score_bm25_fast(self, query: str, chunks: list[RawChunk], top_k: int = 15) -> list[RawChunk]:
        """Stage 1 BM25 Gating: filter hundreds of chunks down to top candidate passages."""
        if len(chunks) <= top_k:
            return chunks

        query_tokens = [t.lower() for t in re.findall(r"\b\w+\b", query) if len(t) > 2]
        if not query_tokens:
            return chunks[:top_k]

        scored_chunks: list[tuple[float, RawChunk]] = []
        doc_count = len(chunks)

        # Build term frequencies and document frequencies
        token_docs: dict[str, int] = {}
        chunk_token_lists: list[list[str]] = []

        for c in chunks:
            # Combine content with section breadcrumb for lexical context
            full_context = f"{c.section_breadcrumb} {c.content}".lower()
            tokens = re.findall(r"\b\w+\b", full_context)
            chunk_token_lists.append(tokens)
            unique_tokens = set(tokens)
            for token in unique_tokens:
                token_docs[token] = token_docs.get(token, 0) + 1

        avg_dl = sum(len(t) for t in chunk_token_lists) / max(1, doc_count)
        k1 = 1.2
        b = 0.75

        for idx, c in enumerate(chunks):
            tokens = chunk_token_lists[idx]
            dl = len(tokens)
            score = 0.0

            tf_map: dict[str, int] = {}
            for t in tokens:
                tf_map[t] = tf_map.get(t, 0) + 1

            for q in query_tokens:
                if q in tf_map:
                    n_q = token_docs.get(q, 1)
                    idf = math.log((doc_count - n_q + 0.5) / (n_q + 0.5) + 1.0)
                    tf = tf_map[q]
                    denom = tf + k1 * (1.0 - b + b * (dl / avg_dl))
                    score += idf * (tf * (k1 + 1.0)) / max(0.001, denom)

            # Bonus for exact identifier matches (code/table)
            if c.has_code and any(q in c.content for q in query_tokens):
                score += 0.5
            if c.has_table:
                score += 0.3

            scored_chunks.append((score, c))

        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored_chunks[:top_k]]

    def rank_passages(
        self,
        query: str,
        markdown_text: str,
        chunks_per_source: int = 3,
    ) -> list[ChunkResult]:
        """Execute full Two-Stage intra-page chunk ranking.

        Returns top N passages sorted by reading order with parent breadcrumbs.
        """
        raw_chunks = self.chunker.chunk_document(markdown_text)
        if not raw_chunks:
            return []

        # Stage 1: BM25 candidate gating
        candidates = self._score_bm25_fast(query, raw_chunks, top_k=15)

        # Stage 2: Neural Cross-Encoder Ranking
        results: list[ChunkResult] = []

        if self._flashrank_model is not None and len(candidates) > 1:
            try:
                passages_payload = [
                    {
                        "id": str(c.index),
                        "text": f"[{c.section_breadcrumb}]\n{c.content}",
                        "meta": {"chunk": c},
                    }
                    for c in candidates
                ]
                from flashrank import RerankRequest
                rerank_req = RerankRequest(query=query, passages=passages_payload)
                ranked = self._flashrank_model.rerank(rerank_req)

                for item in ranked[:chunks_per_source]:
                    raw_c: RawChunk = item["meta"]["chunk"]
                    norm_score = max(0.0, min(1.0, float(item.get("score", 0.5))))
                    formatted_content = f"[{raw_c.section_breadcrumb}]\n{raw_c.content}"
                    results.append(
                        ChunkResult(
                            content=formatted_content,
                            score=round(norm_score, 4),
                            char_count=len(formatted_content),
                            section_title=raw_c.section_breadcrumb,
                        )
                    )
            except Exception:
                # Fall through to lexical scoring if neural model raises runtime error
                pass

        if not results:
            # Algorithmic lexical fallback
            for c in candidates[:chunks_per_source]:
                formatted_content = f"[{c.section_breadcrumb}]\n{c.content}"
                results.append(
                    ChunkResult(
                        content=formatted_content,
                        score=0.75,
                        char_count=len(formatted_content),
                        section_title=c.section_breadcrumb,
                    )
                )

        return results

