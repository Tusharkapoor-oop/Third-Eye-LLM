"""Query-aware passage selection with exact character spans.

Ranking is lexical (BM25 plus phrase/heading/position priors). No score is
returned: ordering is a retrieval heuristic, not a calibrated relevance value.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from ..lexical import query_terms, tokenize
from ..security.injection import scan_injection
from .html import HEADING, heading_of

SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9#])")


@dataclass
class Chunk:
    idx: int
    start: int
    end: int
    text: str
    heading: str | None
    tokens: list[str]
    tf: dict[str, int]
    _score: float = 0.0
    _coverage: float = 0.0


@dataclass
class Passage:
    start: int
    end: int
    text: str
    heading: str | None = None
    score: float = 0.0
    injection: list[str] | None = None


def _split_blocks(text: str) -> list[tuple[int, int, str | None]]:
    """Split into (start, end, heading) blocks, keeping headings with bodies."""
    blocks: list[tuple[int, int, str | None]] = []
    pos = 0
    current_heading: str | None = None
    buf_start = 0
    buf: list[str] = []

    def flush(end: int) -> None:
        nonlocal buf_start, buf
        body = "".join(buf)
        if body.strip():
            blocks.append((buf_start, end, current_heading))
        buf = []

    in_fence = False
    for line in text.splitlines(keepends=True):
        start = pos
        pos += len(line)
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
        m = None if in_fence else HEADING.match(stripped)
        if m and len(m.group(2)) < 160:
            flush(start)
            current_heading = m.group(2)[:160]
            buf_start = start
            buf = [line]
            continue
        if not buf:
            buf_start = start
        buf.append(line)
        # Paragraph boundary: close blocks at blank lines to keep spans local.
        if not stripped and len("".join(buf)) > 900:
            flush(pos)
    flush(len(text))
    return blocks


def _split_segment(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    """Hard-split a long block at paragraph/sentence/space boundaries."""
    spans: list[tuple[int, int]] = []
    pos = start
    while end - pos > max_chars:
        window = text[pos : pos + max_chars]
        cut = max(
            window.rfind("\n\n"),
            window.rfind(". "),
            window.rfind("! "),
            window.rfind("? "),
            window.rfind("\n"),
            window.rfind(" "),
        )
        if cut < int(max_chars * 0.55):
            cut = max_chars
        spans.append((pos, pos + cut))
        pos += cut
        while pos < end and text[pos] in " \t\n":
            pos += 1
    if pos < end:
        spans.append((pos, end))
    return spans


def build_chunks(text: str, *, target_chars: int = 900, max_chars: int = 1600) -> list[Chunk]:
    chunks: list[Chunk] = []
    for start, end, heading in _split_blocks(text):
        for s, e in _split_segment(text, start, end, max_chars):
            piece = text[s:e]
            if piece.strip():
                chunks.append(_chunk(len(chunks), s, e, piece, heading))
    # Drop tiny nav leftovers but keep short code snippets when clearly code.
    return [c for c in chunks if len(c.text.strip()) >= 40 or c.text.strip().startswith("```")]


def _chunk(idx: int, start: int, end: int, text: str, heading: str | None) -> Chunk:
    toks = tokenize(text)
    tf: dict[str, int] = {}
    for t in toks:
        tf[t] = tf.get(t, 0) + 1
    return Chunk(idx=idx, start=start, end=end, text=text, heading=heading, tokens=toks, tf=tf)


def spread_chunks(chunks: list[Chunk], limit: int) -> list[Chunk]:
    """Evenly spaced chunks including the first and last.

    Used when no query is supplied so that facts near the tail of a long page
    remain reachable without query guidance.
    """
    if limit <= 0 or len(chunks) <= limit:
        return chunks
    if limit == 1:
        return [chunks[0]]
    indices = sorted({round(i * (len(chunks) - 1) / (limit - 1)) for i in range(limit)})
    return [chunks[i] for i in indices]


def score_chunks(chunks: list[Chunk], query: str, title: str = "") -> None:
    """Annotate chunk scores in place. Not exposed to callers."""
    terms, phrases = query_terms(query)
    if not terms or not chunks:
        for i, c in enumerate(chunks):
            c_score = 1.0 / (1.0 + 0.08 * i)
            c._score = c_score
        return
    n = len(chunks)
    df: dict[str, int] = {t: 0 for t in terms}
    for c in chunks:
        present = set(c.tokens)
        for t in terms:
            if t in present:
                df[t] += 1
    avgdl = sum(len(c.tokens) for c in chunks) / max(1, n)
    idf = {t: math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in terms}
    title_low = title.lower()
    phrase_low = [p.lower() for p in phrases]
    for _i, c in enumerate(chunks):
        low = c.text.lower()
        dl = max(1, len(c.tokens))
        s = 0.0
        for t in terms:
            f = c.tf.get(t, 0)
            if not f:
                continue
            s += idf[t] * (f * 2.2) / (f + 1.2 * (0.25 + 0.75 * dl / avgdl))
        coverage = sum(1 for t in terms if t in c.tf) / len(terms)
        s *= 0.35 + 0.65 * coverage
        for p in phrase_low:
            if p in low:
                s += 4.0 * (len(p.split()) ** 0.5)
        if c.heading:
            h = c.heading.lower()
            hit = sum(1 for t in terms if t in h)
            if hit:
                s += 1.0 * hit / len(terms)
        if title_low:
            hit = sum(1 for t in terms if t in title_low)
            s += 0.8 * hit / len(terms)
        # Prefer answer-shaped blocks slightly: sentences with numbers/units.
        if re.search(r"\b\d+(?:\.\d+)?\s?(?:ms|s|kb|mb|gb|%|version|v\d|python|node)\b", low):
            s += 0.15
        c._score = s
        c._coverage = coverage


def select_passages(
    text: str,
    query: str | None,
    *,
    title: str = "",
    max_passages: int = 4,
    max_chars: int = 6000,
) -> tuple[list[Passage], float]:
    """Return ranked passages and the best query-term coverage (0..1)."""
    if not text.strip():
        return [], 0.0
    chunks = build_chunks(text)
    if not chunks:
        return [], 0.0
    if query and query.strip():
        score_chunks(chunks, query, title)
        best_cov = max((getattr(c, "_coverage", 0.0) for c in chunks), default=0.0)
        if best_cov == 0:
            return [], 0.0
        full = [c for c in chunks if getattr(c, "_coverage", 0.0) >= 0.999]
        pool = full if full else [c for c in chunks if getattr(c, "_coverage", 0.0) > 0]
        ordered = sorted(pool, key=lambda c: (-getattr(c, "_score", 0.0), c.idx))
    else:
        ordered = spread_chunks(chunks, max_passages)
        best_cov = 0.0

    selected: list[Chunk] = []
    total = 0
    seen_texts: list[str] = []
    for c in ordered:
        clean = c.text.strip()
        if not clean:
            continue
        key = re.sub(r"\W+", "", clean.lower())[:200]
        if any(key[:80] == s[:80] for s in seen_texts):
            continue
        if total + len(clean) > max_chars and selected:
            continue
        selected.append(c)
        seen_texts.append(key)
        total += len(clean)
        if len(selected) >= max_passages or total >= max_chars:
            break
    selected.sort(key=lambda c: c.idx)

    passages: list[Passage] = []
    for c in selected:
        inj = scan_injection(c.text)
        passages.append(
            Passage(
                start=c.start,
                end=c.end,
                text=text[c.start : c.end],
                heading=c.heading or heading_of(text, c.start),
                score=float(getattr(c, "_score", 0.0)),
                injection=inj or None,
            )
        )
    return passages, best_cov
