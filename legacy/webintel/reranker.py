"""Structure-aware passage chunking and two-stage reranking.

Why this exists
---------------
The previous pipeline sliced ``page[:16000]``. That returns navigation
boilerplate from the top of the page and cuts off the answer at the bottom.
Here the page is split by heading hierarchy into ~500-character passages, every
passage carries its section breadcrumb, and fenced code blocks plus Markdown
tables are never split from the explanation that introduces them.

Stage 1  BM25 over the page's own passages plus exact-identifier bonuses.
Stage 2  Cross-encoder (FlashRank / ms-marco-MiniLM-L-12-v2) over the top 15.

If FlashRank cannot load (offline first run, missing wheel), the pipeline
degrades to stage 1 and labels the selector ``bm25`` instead of silently
pretending a neural score exists.
"""
from __future__ import annotations

import asyncio
import math
import os
import re
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .schemas import Passage, PassageKind, QueryPlan
from .utils import normalize_text, sha256

TARGET_CHARS = 550
HARD_MAX_CHARS = 1200
MAX_ATTACH_CHARS = 2000
BM25_CANDIDATES = 15

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*([A-Za-z0-9_+#.-]*)\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?\s*$")
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_+#.:/-]*")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    """Internal chunk before scoring."""

    text: str
    section: str
    kind: PassageKind
    order: int
    meta: dict = field(default_factory=dict)


def _section_label(stack: Sequence[str]) -> str:
    parts = [p for p in stack if p]
    return " > ".join(parts[-3:])


def _split_long_paragraph(text: str, limit: int) -> list[str]:
    """Split an over-long paragraph on sentence boundaries, then words."""
    if len(text) <= limit:
        return [text]
    sentences = _SENTENCE.split(text)
    out: list[str] = []
    buf = ""
    for sentence in sentences:
        if not sentence:
            continue
        if buf and len(buf) + len(sentence) + 1 > limit:
            out.append(buf.strip())
            buf = ""
        if len(sentence) > limit:
            words = sentence.split()
            piece = ""
            for word in words:
                if piece and len(piece) + len(word) + 1 > limit:
                    out.append(piece.strip())
                    piece = ""
                piece = (piece + " " + word).strip()
            if piece:
                buf = piece
            continue
        buf = (buf + " " + sentence).strip()
    if buf:
        out.append(buf.strip())
    return [p for p in out if p]


class MarkdownChunker:
    """Heading-aware chunker with atomic code/table handling."""

    def __init__(self, target_chars: int = TARGET_CHARS, hard_max: int = HARD_MAX_CHARS):
        self.target = target_chars
        self.hard_max = hard_max

    def chunk(self, markdown: str) -> list[Chunk]:
        if not markdown or not markdown.strip():
            return []
        lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        chunks: list[Chunk] = []
        stack: list[str] = []
        buffer: list[str] = []
        buffer_len = 0
        order = 0

        def flush(kind: PassageKind = "text", force_attach: Optional[str] = None) -> None:
            nonlocal buffer, buffer_len, order
            body = "\n".join(buffer).strip()
            if force_attach:
                body = (body + "\n\n" + force_attach).strip() if body else force_attach
            buffer, buffer_len = [], 0
            if not body:
                return
            for piece in _split_long_paragraph(body, self.hard_max):
                section = _section_label(stack)
                chunks.append(Chunk(text=piece, section=section, kind=kind, order=order))
                order += 1

        i = 0
        while i < len(lines):
            line = lines[i]

            fence = _FENCE.match(line)
            if fence:
                marker = fence.group(1)
                lang = fence.group(2) or ""
                body_lines = [line]
                i += 1
                while i < len(lines):
                    body_lines.append(lines[i])
                    if lines[i].strip().startswith(marker[:3]) and lines[i].strip().strip(marker[0]) == "":
                        break
                    i += 1
                i += 1
                block = "\n".join(body_lines).strip()
                if not block.endswith(marker[:3]):
                    block = block + f"\n{marker[:3]}"
                flush("code", force_attach=block)
                continue

            heading = _HEADING.match(line)
            if heading:
                flush()
                level = len(heading.group(1))
                title = heading.group(2).strip().strip("#").strip()
                if title:
                    if level <= len(stack):
                        stack = stack[: level - 1]
                    while len(stack) < level - 1:
                        stack.append("")
                    stack.append(title)
                i += 1
                continue

            # Markdown table: header row followed by a separator row.
            if ("|" in line and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1])):
                table_lines = [line, lines[i + 1]]
                i += 2
                while i < len(lines) and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i])
                    i += 1
                block = "\n".join(table_lines).strip()
                flush("table", force_attach=block)
                continue

            if not line.strip():
                if buffer_len and buffer_len >= self.target:
                    flush()
                else:
                    buffer.append("")
                i += 1
                continue

            buffer.append(line)
            buffer_len += len(line) + 1
            if buffer_len >= self.target:
                flush()
            i += 1

        flush()
        return self._dedupe(chunks)

    @staticmethod
    def _dedupe(chunks: list[Chunk]) -> list[Chunk]:
        out: list[Chunk] = []
        seen: set[str] = set()
        for chunk in chunks:
            key = sha256(normalize_text(chunk.text)[:600])
            if key in seen:
                continue
            seen.add(key)
            out.append(chunk)
        return out


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def _bm25_scores(docs: list[list[str]], query: list[str]) -> list[float]:
    """BM25 with a pure-Python fallback.

    ``rank_bm25.BM25Okapi`` divides by average document length and by IDF sums;
    degenerate corpora (one chunk, empty vocabulary) raise or return NaN. Those
    cases fall back to overlap counting, which is coarse but correct.
    """
    if not docs or not query:
        return [0.0] * len(docs)
    if len(docs) >= 2:
        try:
            from rank_bm25 import BM25Okapi

            bm25 = BM25Okapi(docs)
            scores = [float(s) for s in bm25.get_scores(query)]
            if all(math.isfinite(s) for s in scores) and any(s > 0 for s in scores):
                return scores
        except Exception:
            pass
    q = set(query)
    return [float(len(q & set(doc))) for doc in docs]


class BM25Gate:
    """Stage 1: cheap lexical gate over candidates from every URL."""

    def __init__(self, top_k: int = BM25_CANDIDATES):
        self.top_k = top_k

    def rank(self, chunks: list[Chunk], plan: QueryPlan, query: str) -> list[tuple[Chunk, float]]:
        if not chunks:
            return []
        tokens = list(plan.bm25_tokens) or _tokenize(query)
        docs = [_tokenize(c.text + " " + c.section) for c in chunks]
        base = _bm25_scores(docs, _tokenize(" ".join(tokens)))
        locks = [lock.lower() for lock in plan.lexical_locks]
        q_tokens = set(_tokenize(query))

        scored: list[tuple[Chunk, float]] = []
        for chunk, bm25 in zip(chunks, base):
            low = chunk.text.lower()
            bonus = 0.0
            for lock in locks:
                if lock and lock in low:
                    bonus += 3.0
            heading_tokens = set(_tokenize(chunk.section))
            bonus += 0.4 * len(q_tokens & heading_tokens)
            if chunk.kind in ("code", "table"):
                bonus += 0.15
            scored.append((chunk, float(bm25) + bonus))

        scored.sort(key=lambda item: -item[1])
        return scored[: self.top_k]


class CrossEncoderRanker:
    """Stage 2: FlashRank cross-encoder, lazily loaded and thread-offloaded."""

    _lock = threading.Lock()

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir or os.path.join(
            os.environ.get("WEBINTEL_CACHE_DIR", ".webintel"), "flashrank"
        )
        self._ranker = None
        self._state = "unloaded"  # unloaded | ready | unavailable
        self._error = ""

    @property
    def available(self) -> bool:
        self._ensure()
        return self._state == "ready"

    @property
    def error(self) -> str:
        self._ensure()
        return self._error

    def _ensure(self) -> None:
        if self._state != "unloaded":
            return
        with self._lock:
            if self._state != "unloaded":
                return
            try:
                from flashrank import Ranker

                os.makedirs(self.cache_dir, exist_ok=True)
                self._ranker = Ranker(
                    model_name=os.environ.get(
                        "WEBINTEL_RERANK_MODEL", "ms-marco-MiniLM-L-12-v2"
                    ),
                    cache_dir=self.cache_dir,
                    max_length=512,
                )
                self._state = "ready"
            except Exception as exc:  # offline, HF outage, missing onnxruntime
                self._state = "unavailable"
                self._error = f"{type(exc).__name__}: {exc}"[:200]

    def _rank_sync(self, query: str, texts: list[str]) -> list[float]:
        from flashrank import RerankRequest

        request = RerankRequest(
            query=query,
            passages=[{"id": i, "text": text} for i, text in enumerate(texts)],
        )
        results = self._ranker.rerank(request)
        scores = [0.0] * len(texts)
        for item in results:
            idx = int(item.get("id", item.get("corpus_id", 0)))
            if 0 <= idx < len(scores):
                scores[idx] = float(item.get("score", 0.0))
        return scores

    async def score(self, query: str, texts: list[str]) -> Optional[list[float]]:
        if not texts:
            return []
        self._ensure()
        if self._state != "ready":
            return None
        try:
            return await asyncio.to_thread(self._rank_sync, query, texts)
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"[:200]
            return None


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


class PassageSelector:
    """Public entry point used by the extractor and research engine."""

    def __init__(self, chunker: Optional[MarkdownChunker] = None,
                 gate: Optional[BM25Gate] = None,
                 cross_encoder: Optional[CrossEncoderRanker] = None):
        self.chunker = chunker or MarkdownChunker()
        self.gate = gate or BM25Gate()
        self.cross_encoder = cross_encoder or CrossEncoderRanker()

    async def select(self, markdown: str, query: str, plan: QueryPlan,
                     top_k: int = 3) -> list[Passage]:
        chunks = self.chunker.chunk(markdown)
        if not chunks:
            return []
        top_k = max(1, min(int(top_k or 3), 8))
        gated = self.gate.rank(chunks, plan, query)
        if not gated:
            return []

        gate_scores = _minmax([score for _, score in gated])
        texts = [chunk.text for chunk, _ in gated]
        neural = await self.cross_encoder.score(query, texts)

        selector: str = "bm25"
        if neural is not None and any(abs(s) > 1e-9 for s in neural):
            neural_norm = [_sigmoid(s) for s in neural]
            final = [0.75 * n + 0.25 * g for n, g in zip(neural_norm, gate_scores)]
            selector = "cross-encoder"
        else:
            final = gate_scores

        ranked = sorted(range(len(gated)), key=lambda idx: -final[idx])[:top_k]
        # Reading order, not score order: a code block must follow its explanation.
        ranked.sort(key=lambda idx: gated[idx][0].order)

        out: list[Passage] = []
        for idx in ranked:
            chunk, bm25 = gated[idx]
            out.append(
                Passage(
                    url="",
                    title="",
                    section=chunk.section,
                    span=chunk.text,
                    kind=chunk.kind,
                    order=chunk.order,
                    score=round(float(max(0.0, min(1.0, final[idx]))), 4),
                    bm25=round(float(bm25), 4),
                    selector=selector if selector == "cross-encoder" else "bm25",
                )
            )
        return out

    async def select_many(self, pages: list[tuple[str, str]], query: str,
                          plan: QueryPlan, per_page: int = 3,
                          total: int = 12) -> list[Passage]:
        """Select from several (url, markdown) pairs and return a global top-N.

        This is what fixes multi-hop questions: a fact that ranks third on one
        page can beat the top chunk of a weaker page when compared globally.
        """
        pool: list[Passage] = []
        seen: set[str] = set()
        for url, markdown in pages:
            passages = await self.select(markdown, query, plan, top_k=per_page)
            for passage in passages:
                passage.url = url
                key = sha256(normalize_text(passage.span)[:400])
                if key in seen:
                    continue
                seen.add(key)
                pool.append(passage)
        if not pool:
            return []
        # Cross-URL comparison on the calibrated [0,1] score, then de-cluster so
        # one page cannot occupy every slot.
        pool.sort(key=lambda p: -p.score)
        out: list[Passage] = []
        per_url: dict[str, int] = {}
        for passage in pool:
            if per_url.get(passage.url, 0) >= max(2, per_page):
                continue
            per_url[passage.url] = per_url.get(passage.url, 0) + 1
            out.append(passage)
            if len(out) >= total:
                break
        return out
