"""Fixed DocumentChunker that selects evenly spaced chunks including the last.

The key design changes from the original:
1. Computes target number of chunks based on total token count / target_tokens
2. Selects N evenly-spaced paragraph indices as chunk boundaries
3. ALWAYS includes the last paragraph index, ensuring tail facts are captured
4. Falls back to accumulator approach for small documents
5. Sub-chunks oversized paragraphs at sentence level
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import tiktoken


def _sub_split_paragraph(p_text: str, start_offset: int, max_chars: int = 720) -> list[tuple[str, int, int]]:
    if len(p_text) <= max_chars:
        return [(p_text, start_offset, start_offset + len(p_text))]
    subs: list[tuple[str, int, int]] = []
    pos = 0
    end = len(p_text)
    while end - pos > max_chars:
        window = p_text[pos : pos + max_chars]
        cut = max(
            window.rfind(". "),
            window.rfind("! "),
            window.rfind("? "),
            window.rfind("\n"),
            window.rfind("; "),
            window.rfind(" "),
        )
        if cut < int(max_chars * 0.50):
            cut = max_chars
        else:
            cut += 1
        chunk_str = p_text[pos : pos + cut].strip()
        if chunk_str:
            subs.append((chunk_str, start_offset + pos, start_offset + pos + len(chunk_str)))
        pos += cut
        while pos < end and p_text[pos] in " \t\n":
            pos += 1
    if pos < end:
        chunk_str = p_text[pos:end].strip()
        if chunk_str:
            subs.append((chunk_str, start_offset + pos, start_offset + pos + len(chunk_str)))
    return subs


@dataclass
class DocumentChunk:
    text: str
    char_start: int
    char_end: int
    token_count: int
    heading: str | None = None


class DocumentChunker:
    """Token-aware text chunker that selects evenly-spaced chunks including the last.

    The original accumulator approach chops paragraphs sequentially until the token
    budget runs out, which means for long documents, only the first few chunks are
    created and tail facts in the final paragraphs may be lost.

    This charger instead:
    1. Splits the document into paragraphs
    2. Computes N = ceil(total_tokens / target_tokens) as the target number of chunks
    3. Selects N evenly-spaced paragraph indices (first=0, last=n_paragraphs-1)
    4. Always ensures the last paragraph is included in a chunk
    5. Builds chunks from the selected paragraph boundaries
    """

    def __init__(self, target_tokens: int = 180, overlap_tokens: int = 30):
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        self.tokenizer = tiktoken.get_encoding("o200k_base")

    def chunk_document(self, text: str) -> list[DocumentChunk]:
        """Split text into evenly-spaced chunks, always including the last paragraph."""

        if not text or not text.strip():
            return []

        # Split by paragraph breaks (double newline or markdown headers)
        paragraph_splits = [
            m.start()
            for m in re.finditer(r"\n\s*\n|(?=^#{1,4}\s)", text, re.MULTILINE)
        ]
        paragraph_splits = [0] + paragraph_splits + [len(text)]
        paragraph_splits = sorted(list(set(paragraph_splits)))

        paragraphs: list[tuple[str, int, int]] = []
        for i in range(len(paragraph_splits) - 1):
            start = paragraph_splits[i]
            end = paragraph_splits[i + 1]
            p_text = text[start:end].strip()
            if p_text:
                actual_start = text.find(p_text, start)
                actual_end = actual_start + len(p_text)
                if len(p_text) > self.target_tokens * 4:
                    paragraphs.extend(_sub_split_paragraph(p_text, actual_start, max_chars=self.target_tokens * 4))
                else:
                    paragraphs.append((p_text, actual_start, actual_end))

        if not paragraphs:
            return []

        n_paragraphs = len(paragraphs)

        # Compute total tokens and target number of chunks
        total_token_count = sum(
            len(self.tokenizer.encode(p_text)) for p_text, _, _ in paragraphs
        )
        n_chunks = max(1, math.ceil(total_token_count / self.target_tokens))

        # If we have fewer paragraphs than needed chunks, use accumulator approach
        if n_chunks >= n_paragraphs:
            # Accumulator: split paragraphs into chunks by token budget
            chunks: list[DocumentChunk] = []
            current_paragraphs: list[tuple[str, int, int]] = []
            current_token_count = 0

            for p_text, p_start, p_end in paragraphs:
                p_tokens = len(self.tokenizer.encode(p_text))

                if current_paragraphs and (current_token_count + p_tokens > self.target_tokens):
                    # Flush accumulated paragraphs as a chunk
                    chunk_text = text[current_paragraphs[0][1] : current_paragraphs[-1][2]]
                    chunks.append(
                        DocumentChunk(
                            text=chunk_text,
                            char_start=current_paragraphs[0][1],
                            char_end=current_paragraphs[-1][2],
                            token_count=current_token_count,
                        )
                    )
                    # Keep last paragraph for overlap if within overlap limit
                    if current_token_count <= self.overlap_tokens:
                        pass  # current_paragraphs will be reset below
                    else:
                        current_paragraphs = []
                        current_token_count = 0

                current_paragraphs.append((p_text, p_start, p_end))
                current_token_count += p_tokens

            if current_paragraphs:
                chunk_text = text[current_paragraphs[0][1] : current_paragraphs[-1][2]]
                chunks.append(
                    DocumentChunk(
                        text=chunk_text,
                        char_start=current_paragraphs[0][1],
                        char_end=current_paragraphs[-1][2],
                        token_count=current_token_count,
                    )
                )
            return chunks

        # --- Evenly-spaced chunk selection ---

        # Select N evenly-spaced paragraph indices as chunk boundaries.
        # Boundary i (0-based) maps to paragraph index:
        #   round(i * (n_paragraphs - 1) / (n_chunks - 1))
        # This ensures boundary 0 -> paragraph 0 and boundary n_chunks-1 -> paragraph n_paragraphs-1

        if n_chunks <= 1:
            # Single chunk containing all paragraphs
            all_text = text[paragraphs[0][1] : paragraphs[-1][2]]
            return [
                DocumentChunk(
                    text=all_text,
                    char_start=paragraphs[0][1],
                    char_end=paragraphs[-1][2],
                    token_count=len(self.tokenizer.encode(all_text)),
                )
            ]

        # Select evenly-spaced paragraph indices
        selected_indices: set[int] = set()
        for i in range(n_chunks):
            ratio = i / (n_chunks - 1) if n_chunks > 1 else 0
            p_idx = round(ratio * (n_paragraphs - 1))
            p_idx = max(0, min(n_paragraphs - 1, p_idx))
            selected_indices.add(p_idx)

        # CRITICAL: Always include the last paragraph index to capture tail facts
        selected_indices.add(n_paragraphs - 1)

        # Build chunks from selected paragraph boundaries
        sorted_indices = sorted(selected_indices)

        chunks: list[DocumentChunk] = []
        for i in range(len(sorted_indices) - 1):
            start_idx = sorted_indices[i]
            end_idx = sorted_indices[i + 1]

            # Chunk includes paragraphs from start_idx to end_idx-1 (inclusive)
            # Text runs from actual start of paragraph start_idx to actual end of paragraph (end_idx-1)
            if end_idx - 1 >= start_idx:
                chunk_start = paragraphs[start_idx][1]
                chunk_end = paragraphs[end_idx - 1][2]
                chunk_text = text[chunk_start : chunk_end]
                chunk_token_count = len(
                    self.tokenizer.encode(chunk_text)
                )

                # For the last chunk group, ensure we extend to include
                # the very last paragraph if it wasn't already covered
                if i == len(sorted_indices) - 2:
                    # Extend chunk text to include through the last paragraph
                    last_para_end = paragraphs[n_paragraphs - 1][2]
                    remaining_text = text[chunk_start + len(chunk_text) : last_para_end]
                    if remaining_text.strip():
                        chunk_text = chunk_text + remaining_text
                        chunk_end = last_para_end
                    chunk_token_count = len(
                        self.tokenizer.encode(chunk_text)
                    )

                chunks.append(
                    DocumentChunk(
                        text=chunk_text,
                        char_start=chunk_start,
                        char_end=chunk_end,
                        token_count=chunk_token_count,
                    )
                )

        return chunks