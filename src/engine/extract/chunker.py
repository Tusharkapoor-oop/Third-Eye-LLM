"""
Token-Aware Text Chunker
Chunks documents into overlapping, paragraph-preserving spans while tracking exact character offsets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import tiktoken


@dataclass
class DocumentChunk:
    text: str
    char_start: int
    char_end: int
    token_count: int
    heading: str | None = None

class DocumentChunker:
    def __init__(self, target_tokens: int = 180, overlap_tokens: int = 30):
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        self.tokenizer = tiktoken.get_encoding("o200k_base")

    def chunk_document(self, text: str) -> list[DocumentChunk]:
        if not text or not text.strip():
            return []

        # Split by paragraph breaks (double newline or markdown headers)
        paragraph_splits = [m.start() for m in re.finditer(r"\n\s*\n|(?=^#{1,4}\s)", text, re.MULTILINE)]
        paragraph_splits = [0] + paragraph_splits + [len(text)]
        paragraph_splits = sorted(list(set(paragraph_splits)))

        paragraphs: list[tuple[str, int, int]] = []
        for i in range(len(paragraph_splits) - 1):
            start = paragraph_splits[i]
            end = paragraph_splits[i + 1]
            p_text = text[start:end].strip()
            if p_text:
                # Find exact start and end of stripped text
                actual_start = text.find(p_text, start)
                actual_end = actual_start + len(p_text)
                paragraphs.append((p_text, actual_start, actual_end))

        chunks: list[DocumentChunk] = []
        current_paragraphs: list[tuple[str, int, int]] = []
        current_token_count = 0

        for p_text, p_start, p_end in paragraphs:
            p_tokens = len(self.tokenizer.encode(p_text))

            # If a single paragraph is larger than target_tokens, sub-chunk by sentences
            if p_tokens > self.target_tokens:
                if current_paragraphs:
                    # Flush accumulated paragraphs
                    chunk_text = text[current_paragraphs[0][1]:current_paragraphs[-1][2]]
                    chunks.append(DocumentChunk(
                        text=chunk_text,
                        char_start=current_paragraphs[0][1],
                        char_end=current_paragraphs[-1][2],
                        token_count=current_token_count
                    ))
                    current_paragraphs = []
                    current_token_count = 0

                # Sentence-level chunking
                sentence_splits = [m.start() for m in re.finditer(r"(?<=[.!?])\s+", p_text)]
                sentence_splits = [0] + sentence_splits + [len(p_text)]
                sub_sentences: list[tuple[str, int, int]] = []
                for s_i in range(len(sentence_splits) - 1):
                    s_str = p_text[sentence_splits[s_i]:sentence_splits[s_i + 1]].strip()
                    if s_str:
                        s_start = p_start + p_text.find(s_str, sentence_splits[s_i])
                        s_end = s_start + len(s_str)
                        sub_sentences.append((s_str, s_start, s_end))

                sub_curr: list[tuple[str, int, int]] = []
                sub_tok = 0
                for s_str, s_start, s_end in sub_sentences:
                    st_count = len(self.tokenizer.encode(s_str))
                    if sub_curr and (sub_tok + st_count > self.target_tokens):
                        c_text = text[sub_curr[0][1]:sub_curr[-1][2]]
                        chunks.append(DocumentChunk(
                            text=c_text,
                            char_start=sub_curr[0][1],
                            char_end=sub_curr[-1][2],
                            token_count=sub_tok
                        ))
                        sub_curr = []
                        sub_tok = 0
                    sub_curr.append((s_str, s_start, s_end))
                    sub_tok += st_count

                if sub_curr:
                    c_text = text[sub_curr[0][1]:sub_curr[-1][2]]
                    chunks.append(DocumentChunk(
                        text=c_text,
                        char_start=sub_curr[0][1],
                        char_end=sub_curr[-1][2],
                        token_count=sub_tok
                    ))
                continue

            if current_paragraphs and (current_token_count + p_tokens > self.target_tokens):
                chunk_text = text[current_paragraphs[0][1]:current_paragraphs[-1][2]]
                chunks.append(DocumentChunk(
                    text=chunk_text,
                    char_start=current_paragraphs[0][1],
                    char_end=current_paragraphs[-1][2],
                    token_count=current_token_count
                ))
                # Keep last paragraph for overlap if within overlap limit
                if current_token_count <= self.overlap_tokens:
                    pass
                else:
                    current_paragraphs = []
                    current_token_count = 0

            current_paragraphs.append((p_text, p_start, p_end))
            current_token_count += p_tokens

        if current_paragraphs:
            chunk_text = text[current_paragraphs[0][1]:current_paragraphs[-1][2]]
            chunks.append(DocumentChunk(
                text=chunk_text,
                char_start=current_paragraphs[0][1],
                char_end=current_paragraphs[-1][2],
                token_count=current_token_count
            ))

        return chunks
