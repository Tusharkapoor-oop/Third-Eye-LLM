"""Structure-aware passage chunking and deterministic two-stage ranking."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from src.engine.schemas import ChunkResult

WORD = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:/+-]*")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE = re.compile(r"^\s*(```+|~~~+)\s*([A-Za-z0-9_-]*)\s*$")
STOPWORDS = frozenset(
    "a an the and or but for with from into about this that what which who where when why how is are was were be to of in on at by as do does did can could should would".split()
)


@dataclass(frozen=True)
class RankedChunk:
    text: str
    score: float
    char_start: int
    char_end: int
    section: str = ""

    def to_schema(self) -> ChunkResult:
        return ChunkResult(
            content=self.text,
            score=self.score,
            char_count=len(self.text),
            section=self.section,
            char_start=self.char_start,
            char_end=self.char_end,
        )


@dataclass(frozen=True)
class _Unit:
    text: str
    start: int
    end: int
    section: str
    atomic: bool


def _tokens(text: str) -> list[str]:
    return [word.casefold() for word in WORD.findall(text) if word.casefold() not in STOPWORDS]


def _section_path(stack: list[str]) -> str:
    return " > ".join(stack)


def _flush(units: list[_Unit], lines: list[tuple[str, int, int]], section: str, atomic: bool) -> None:
    if not lines:
        return
    start = lines[0][1]
    end = lines[-1][2]
    text = "\n".join(line[0] for line in lines).strip()
    if text:
        left = len("\n".join(line[0] for line in lines)) - len("\n".join(line[0] for line in lines).lstrip())
        units.append(_Unit(text=text, start=start + left, end=end, section=section, atomic=atomic))


def _parse_units(markdown: str) -> list[_Unit]:
    """Parse headings, paragraphs, fenced blocks and tables with source offsets."""
    if not markdown or not markdown.strip():
        return []
    lines: list[tuple[str, int, int]] = []
    offset = 0
    for raw in markdown.splitlines(keepends=True):
        content = raw.rstrip("\r\n")
        lines.append((content, offset, offset + len(content)))
        offset += len(raw)
    units: list[_Unit] = []
    stack: list[str] = []
    paragraph: list[tuple[str, int, int]] = []
    fenced: list[tuple[str, int, int]] = []
    fence_marker = ""
    table: list[tuple[str, int, int]] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        _flush(units, paragraph, _section_path(stack), False)
        paragraph = []

    def flush_table() -> None:
        nonlocal table
        _flush(units, table, _section_path(stack), True)
        table = []

    for line, start, end in lines:
        fence = FENCE.match(line)
        if fence_marker:
            fenced.append((line, start, end))
            if line.lstrip().startswith(fence_marker):
                flush_paragraph()
                _flush(units, fenced, _section_path(stack), True)
                fenced = []
                fence_marker = ""
            continue
        if fence:
            flush_paragraph()
            flush_table()
            fence_marker = fence.group(1)[:3]
            fenced = [(line, start, end)]
            continue
        heading = HEADING.match(line)
        if heading:
            flush_paragraph()
            flush_table()
            level = len(heading.group(1))
            while len(stack) >= level:
                stack.pop()
            stack.append(heading.group(2).strip())
            units.append(_Unit(text=line.strip(), start=start, end=end, section=_section_path(stack), atomic=True))
            continue
        stripped = line.strip()
        is_table_line = "|" in stripped and stripped.startswith("|") and stripped.endswith("|")
        if is_table_line:
            flush_paragraph()
            table.append((line, start, end))
            continue
        if table:
            flush_table()
        if not stripped:
            flush_paragraph()
            continue
        paragraph.append((line, start, end))
    flush_paragraph()
    flush_table()
    if fenced:
        _flush(units, fenced, _section_path(stack), True)
    return units


def _merge_units(units: list[_Unit], target_chars: int = 560) -> list[_Unit]:
    merged: list[_Unit] = []
    pending: list[_Unit] = []
    pending_chars = 0

    def flush() -> None:
        nonlocal pending, pending_chars
        if pending:
            merged.append(_Unit(
                text="\n\n".join(unit.text for unit in pending),
                start=pending[0].start,
                end=pending[-1].end,
                section=pending[-1].section,
                atomic=False,
            ))
        pending = []
        pending_chars = 0

    for unit in units:
        if unit.atomic or pending_chars and pending[-1].section != unit.section:
            flush()
            merged.append(unit)
            continue
        if pending and pending_chars + len(unit.text) + 2 > target_chars:
            flush()
        pending.append(unit)
        pending_chars += len(unit.text) + 2
    flush()
    return merged


def chunk_markdown(markdown: str, target_chars: int = 560) -> list[RankedChunk]:
    """Create source-aligned chunks while keeping code and tables atomic."""
    result: list[RankedChunk] = []
    for unit in _merge_units(_parse_units(markdown), target_chars):
        display = unit.text
        if unit.section and not display.startswith("#"):
            display = f"[Section: {unit.section}]\n{display}"
        result.append(RankedChunk(text=display, score=0.0, char_start=unit.start, char_end=unit.end, section=unit.section))
    return result


def _bm25_scores(chunks: list[RankedChunk], query: str) -> list[float]:
    q_terms = _tokens(query)
    if not q_terms:
        return [0.0 for _ in chunks]
    docs = [_tokens(chunk.text) for chunk in chunks]
    avg_len = sum(len(doc) for doc in docs) / max(len(docs), 1)
    scores: list[float] = []
    for index, doc in enumerate(docs):
        counts = Counter(doc)
        score = 0.0
        for term in q_terms:
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            doc_frequency = sum(term in other for other in docs)
            idf = math.log(1.0 + (len(docs) - doc_frequency + 0.5) / (doc_frequency + 0.5))
            denominator = frequency + 1.5 * (1.0 - 0.75 + 0.75 * len(doc) / max(avg_len, 1.0))
            score += idf * frequency * 2.5 / denominator
        if query.casefold() in chunks[index].text.casefold():
            score += 1.5
        if any(lock.casefold() in chunks[index].text.casefold() for lock in re.findall(r"[\"'`]([^\"'`]+)[\"'`]", query)):
            score += 1.0
        scores.append(score)
    maximum = max(scores, default=0.0)
    return [value / maximum if maximum else 0.0 for value in scores]


_RANKER = None


def _get_ranker():
    """Load the cross-encoder once per process instead of once per request."""
    global _RANKER
    if _RANKER is None:
        from flashrank import Ranker

        _RANKER = Ranker(model_name="ms-marco-MiniLM-L-12-v2")
    return _RANKER


def _is_structured(text: str) -> bool:
    return "```" in text or ("\n|" in text and "---" in text)


def rank_chunks(markdown: str, query: str, chunks_per_source: int = 3, max_candidates: int = 15) -> list[RankedChunk]:
    """Rank lexical candidates, optionally apply FlashRank, and return reading order."""
    limit = max(1, min(int(chunks_per_source), 5))
    chunks = chunk_markdown(markdown)
    if not chunks:
        return []
    scores = _bm25_scores(chunks, query)
    candidates = sorted(range(len(chunks)), key=lambda index: (-scores[index], chunks[index].char_start))[:max_candidates]
    # Guarantee that code and table evidence survives the lexical gate. A
    # prose-only candidate set can never surface the runnable example, even
    # when the query explicitly asks for one.
    if candidates and not any(_is_structured(chunks[index].text) for index in candidates):
        structured = [index for index, chunk in enumerate(chunks) if _is_structured(chunk.text)]
        if structured:
            candidates[-1] = max(structured, key=lambda index: scores[index])
            candidates = list(dict.fromkeys(candidates))
    neural_scores: dict[int, float] = {}
    try:
        from flashrank import RerankRequest

        ranker = _get_ranker()
        passages = [{"id": index, "text": chunks[index].text} for index in candidates]
        ranked = ranker.rerank(RerankRequest(query=query, passages=passages))
        raw_scores = [float(item.get("score", 0.0)) for item in ranked]
        max_raw = max(raw_scores, default=0.0)
        for item in ranked:
            value = float(item.get("score", 0.0))
            neural_scores[int(item["id"])] = value / max_raw if max_raw > 0 else 0.0
    except (ImportError, OSError, RuntimeError, TypeError, ValueError, AttributeError):
        neural_scores = {}

    scored: list[RankedChunk] = []
    for index in candidates:
        lexical = scores[index]
        neural = neural_scores.get(index, lexical)
        combined = max(0.0, min(1.0, 0.55 * lexical + 0.45 * neural))
        chunk = chunks[index]
        scored.append(RankedChunk(chunk.text, combined, chunk.char_start, chunk.char_end, chunk.section))
    scored.sort(key=lambda item: (-item.score, item.char_start))
    top = scored[:limit]
    if limit > 1 and not any(_is_structured(item.text) for item in top):
        extra = next((item for item in scored if _is_structured(item.text)), None)
        if extra is not None:
            top[-1] = extra
    return sorted(top, key=lambda item: item.char_start)
