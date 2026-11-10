"""
Lexical & BM25 Passage Scorer
Ranks document chunks against user queries to select top evidence passages without returning full documents.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from src.engine.extract.chunker import DocumentChunk


@dataclass
class ScoredPassage:
    text: str
    char_start: int
    char_end: int
    token_count: int
    rank: int

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "char_start": self.char_start,
            "char_end": self.char_end
        }

WORD_PATTERN = re.compile(r"\b\w{2,}\b")
BM25_STOPWORDS = frozenset({
    "what", "which", "who", "whom", "whose", "where", "when", "why", "how",
    "does", "did", "is", "are", "was", "were", "the", "and", "for", "with",
    "from", "about", "approximate", "primary", "order", "in", "of", "to", "on"
})

def tokenize_words(text: str) -> list[str]:
    return [w.lower() for w in WORD_PATTERN.findall(text)]

class BM25PassageScorer:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b

    def score_and_rank_passages(
        self,
        chunks: list[DocumentChunk],
        query: str | None,
        max_tokens: int = 1200,
        max_passages: int = 5
    ) -> list[ScoredPassage]:
        if not chunks:
            return []

        # If no query is provided, return introductory chunks in document order
        if not query or not query.strip():
            selected: list[ScoredPassage] = []
            tokens_accum = 0
            for idx, c in enumerate(chunks[:max_passages]):
                if tokens_accum + c.token_count > max_tokens and selected:
                    break
                selected.append(ScoredPassage(
                    text=c.text,
                    char_start=c.char_start,
                    char_end=c.char_end,
                    token_count=c.token_count,
                    rank=idx + 1
                ))
                tokens_accum += c.token_count
            return selected

        # Query-guided BM25 scoring with stop-word filtering
        raw_terms = tokenize_words(query)
        query_terms = [t for t in raw_terms if t not in BM25_STOPWORDS] or raw_terms
        if not query_terms:
            return self.score_and_rank_passages(chunks, None, max_tokens, max_passages)

        doc_count = len(chunks)
        chunk_tokenized = [tokenize_words(c.text) for c in chunks]
        chunk_lengths = [len(words) for words in chunk_tokenized]
        avg_length = sum(chunk_lengths) / max(doc_count, 1)

        # Document frequencies for query terms
        df: dict[str, int] = {}
        for term in set(query_terms):
            df[term] = sum(1 for words in chunk_tokenized if term in words)

        # Calculate BM25 scores
        scored_indices: list[tuple[int, float]] = []
        for idx, words in enumerate(chunk_tokenized):
            doc_len = chunk_lengths[idx]
            term_counts = Counter(words)
            score = 0.0

            for term in query_terms:
                freq = term_counts.get(term, 0)
                if freq == 0:
                    continue
                doc_freq = df.get(term, 0)
                # Standard Robertson-Spärck Jones IDF
                idf = math.log(1.0 + (doc_count - doc_freq + 0.5) / (doc_freq + 0.5))
                # BM25 term saturation
                numerator = freq * (self.k1 + 1.0)
                denominator = freq + self.k1 * (1.0 - self.b + self.b * (doc_len / (avg_length or 1.0)))
                score += idf * (numerator / denominator)

            # Bonus for exact query phrase match
            if query.lower() in chunks[idx].text.lower():
                score += 5.0

            # Lead section bonus: first chunk in document typically contains definitions and summaries
            if idx == 0 and score > 0:
                score += 2.0

            scored_indices.append((idx, score))

        # Sort descending by score
        scored_indices.sort(key=lambda x: x[1], reverse=True)

        # Select top chunks fitting within token budget
        results: list[ScoredPassage] = []
        used_tokens = 0
        rank = 1

        for idx, score in scored_indices:
            # If even the best chunk has 0 score, we fall back to intro chunks
            if rank == 1 and score <= 0:
                return self.score_and_rank_passages(chunks, None, max_tokens, max_passages)

            chunk = chunks[idx]
            if used_tokens + chunk.token_count > max_tokens and results:
                break
            results.append(ScoredPassage(
                text=chunk.text,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                token_count=chunk.token_count,
                rank=rank
            ))
            used_tokens += chunk.token_count
            rank += 1
            if len(results) >= max_passages:
                break

        # Sort back into document reading order (char_start) for natural coherence
        results.sort(key=lambda p: p.char_start)
        return results
