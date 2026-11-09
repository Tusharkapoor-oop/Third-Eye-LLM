"""Crawl2RAG: Turn a website into a local searchable knowledge base.

Uses bounded polite crawling, SSRF checks on every link, clean semantic chunking
with exact source spans, and a local SQLite FTS5/BM25 index for zero-latency,
zero-cost retrieval with full source attribution.

When a local ONNX sentence-embedding model is available, retrieval can also add
dense candidates and fuse them with BM25 using reciprocal rank fusion.  The
lexical path remains the default and needs no model, network, or extra package.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
import sqlite3
import threading
import time
from array import array
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from ..errors import BlockedURLError
from ..extract.passages import build_chunks
from ..lexical import query_terms, tokenize
from ..service import WebLens
from .embeddings import Embedder, EmbeddingUnavailable, build_default_embedder

_RRF_K = 60
_MAX_FTS_TOKENS = 64
# FTS5 treats these as prefix operators; "NEAR" also has special meaning.
_FTS_OPERATORS = {"not", "and", "or", "near"}


def _quote_fts_token(token: str) -> str:
    """Wrap a token for FTS5 MATCH, escaping embedded double quotes."""
    escaped = token.replace('"', '""')
    return f'"{escaped}"'


def _build_fts_query(question: str) -> str:
    """Sanitize free-text question into a safe FTS5 OR query.

    Keeps letters, digits and apostrophes, drops bare FTS operators, and quotes
    every remaining token so punctuation and reserved words cannot break the
    MATCH expression.
    """
    cleaned = re.sub(r"[^\w\s']", " ", question)
    tokens = [t for t in cleaned.split() if len(t) > 2]
    tokens = [t for t in tokens if t.lower() not in _FTS_OPERATORS]
    if not tokens:
        return ""
    return " OR ".join(_quote_fts_token(t) for t in tokens[:_MAX_FTS_TOKENS])


# Conservative floor for dense-only matches. Lexically supported passages are
# always kept; this floor only decides whether an embedding-space neighbour is
# strong enough to answer a query whose terms do not appear in the passage.
_DENSE_MIN_SCORE = 0.30


class _DenseScanLimitExceeded(RuntimeError):
    """The exact dense scan would exceed the configured passage cap."""


def _normalise_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(float(value) * float(value) for value in vector))
    if not math.isfinite(norm) or norm <= 0:
        return [0.0 for _ in vector]
    return [float(value) / norm for value in vector]


def _pack_vector(vector: list[float]) -> bytes:
    return array("f", _normalise_vector(vector)).tobytes()


def _unpack_vector(blob: bytes) -> array:
    values = array("f")
    values.frombytes(blob)
    return values


def _try_numpy():
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - only needs the optional extra
        return None
    return np


class _EncodeQuery(Protocol):
    """A cached embedder query function exposing ``cache_clear``."""

    def __call__(self, model: str, question: str) -> list[float]: ...
    def cache_clear(self) -> None: ...


class Crawl2RAG:
    """Website-to-Knowledge-Base pipeline backed by local SQLite FTS5."""

    def __init__(
        self,
        service: WebLens,
        db_path: Path | str | None = None,
        *,
        embedder: Embedder | None = None,
        auto_embedder: bool = True,
    ):
        self.service = service
        if db_path is None:
            db_path = service.s.cache_dir / "crawl2rag.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._embedding_error: str | None = None
        self._dense_lock = threading.Lock()
        # (model, row count, ids, vectors, db mtime_ns, db size). Writes
        # through this instance invalidate explicitly; the file signature
        # also catches external changes without scanning the whole index.
        self._dense_cache: tuple[str, int, Any, Any, int, int] | None = None
        # (model, db mtime_ns, db size) for a KB above the exact-scan cap.
        self._dense_overflow: tuple[str, int, int] | None = None
        if embedder is not None:
            self.embedder: Embedder | None = embedder
        elif auto_embedder:
            self.embedder = build_default_embedder(service.s)
        else:
            self.embedder = None

        self._encode_query: _EncodeQuery = lru_cache(maxsize=128)(self._encode_query_uncached)

        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kb_docs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    title TEXT,
                    content_hash TEXT,
                    ingested_at TEXT,
                    page_tokens INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS kb_passages USING fts5(
                    url,
                    title,
                    passage_index,
                    span_start,
                    span_end,
                    text,
                    tokenize='porter unicode61'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kb_embeddings (
                    passage_rowid INTEGER PRIMARY KEY,
                    url TEXT NOT NULL,
                    model TEXT NOT NULL,
                    dim INTEGER NOT NULL,
                    vec BLOB NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_embeddings_url ON kb_embeddings(url)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_embeddings_model ON kb_embeddings(model)")
            conn.commit()

    def _invalidate_dense_cache(self) -> None:
        with self._dense_lock:
            self._dense_cache = None
            self._dense_overflow = None

    def _disable_embedder(self, exc: Exception) -> None:
        self._embedding_error = f"{type(exc).__name__}: {exc}"
        self.embedder = None
        self._encode_query.cache_clear()
        self._invalidate_dense_cache()

    def _encode_query_uncached(self, model: str, question: str) -> list[float]:
        if self.embedder is None:
            raise EmbeddingUnavailable("embedder is not available")
        if self.embedder.model_name != model:
            raise EmbeddingUnavailable(f"embedder model mismatch: {self.embedder.model_name} != {model}")
        return self.embedder.encode([question])[0]

    def _index_embeddings(self, conn: sqlite3.Connection, url: str) -> int:
        if self.embedder is None:
            return 0
        rows = conn.execute(
            "SELECT rowid, text FROM kb_passages WHERE url = ? ORDER BY passage_index",
            (url,),
        ).fetchall()
        if not rows:
            return 0

        vectors = self.embedder.encode([str(row[1]) for row in rows])
        model = self.embedder.model_name
        payload = []
        for (rowid, _text), vector in zip(rows, vectors, strict=False):
            if not vector:
                continue
            payload.append((rowid, url, model, len(vector), _pack_vector(vector)))
        if payload:
            conn.executemany(
                """
                INSERT OR REPLACE INTO kb_embeddings
                    (passage_rowid, url, model, dim, vec)
                VALUES (?, ?, ?, ?, ?)
                """,
                payload,
            )
        return len(payload)

    def _persist_ingest(self, pages) -> dict[str, Any]:
        """SQLite-heavy ingestion path intended to run in a worker thread.

        Keeps the event loop free while crawling has already returned.
        """
        now_iso = datetime.now(UTC).isoformat()
        indexed_pages = 0
        indexed_passages = 0
        indexed_embeddings = 0
        skipped_unchanged = 0

        with sqlite3.connect(self.db_path) as conn:
            for page in pages:
                text = (getattr(page, "text", "") or "").strip()
                if not text:
                    passages = getattr(page, "passages", None) or []
                    text = "\n\n".join(str(p.get("x", "")) for p in passages).strip()
                if not text:
                    text = (getattr(page, "excerpt", "") or "").strip()
                if not text:
                    continue

                page_tokens = getattr(page, "tokens", 0) or 0

                chash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                row = conn.execute("SELECT content_hash FROM kb_docs WHERE url = ?", (page.url,)).fetchone()

                if row and row[0] == chash:
                    skipped_unchanged += 1
                    continue

                # Remove existing passages and vectors for this URL if updating.
                conn.execute("DELETE FROM kb_embeddings WHERE url = ?", (page.url,))
                conn.execute("DELETE FROM kb_passages WHERE url = ?", (page.url,))
                conn.execute(
                    """
                    INSERT INTO kb_docs (url, title, content_hash, ingested_at, page_tokens)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        title = excluded.title,
                        content_hash = excluded.content_hash,
                        ingested_at = excluded.ingested_at,
                        page_tokens = excluded.page_tokens
                    """,
                    (page.url, page.title or "", chash, now_iso, page_tokens),
                )

                passages = build_chunks(text)
                for idx, p in enumerate(passages):
                    conn.execute(
                        """
                        INSERT INTO kb_passages (url, title, passage_index, span_start, span_end, text)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (page.url, page.title or "", idx, p.start, p.end, p.text),
                    )
                    indexed_passages += 1

                if self.embedder is not None:
                    try:
                        indexed_embeddings += self._index_embeddings(conn, page.url)
                    except EmbeddingUnavailable as exc:
                        self._disable_embedder(exc)
                    except Exception as exc:  # noqa: BLE001 - optional path
                        self._disable_embedder(exc)

                indexed_pages += 1
            conn.commit()

        return {
            "indexed_pages": indexed_pages,
            "indexed_passages": indexed_passages,
            "indexed_embeddings": indexed_embeddings,
            "skipped_unchanged": skipped_unchanged,
        }

    async def ingest(
        self,
        start_url: str,
        *,
        max_pages: int = 15,
        max_depth: int = 2,
    ) -> dict[str, Any]:
        """Crawl website and index clean passages with source spans into SQLite."""
        # Validate destination policy upfront to prevent SSRF
        if hasattr(self.service, "fetcher") and hasattr(self.service.fetcher, "policy"):
            try:
                self.service.fetcher.policy.check_url(start_url)
            except BlockedURLError as e:
                return {
                    "status": "error",
                    "err": "blocked_url",
                    "msg": f"Destination blocked by SSRF policy: {e}",
                    "url": start_url,
                    "pages_crawled": 0,
                    "pages_indexed": 0,
                }

        t0 = time.perf_counter()
        crawl_out = await self.service.crawler.crawl(
            start_url,
            max_pages=max_pages,
            max_depth=max_depth,
            max_tokens=25000,
        )

        if any(p.status == "error" and any("BlockedURL" in str(w) for w in p.warnings) for p in crawl_out.pages):
            return {
                "status": "error",
                "err": "blocked_url",
                "msg": "Destination blocked by SSRF policy",
                "url": start_url,
                "pages_crawled": len(crawl_out.pages),
                "pages_indexed": 0,
            }

        # SQLite and ONNX encode are blocking; keep them off the event loop.
        ingest_state = await asyncio.to_thread(self._persist_ingest, crawl_out.pages)

        indexed_pages = ingest_state["indexed_pages"]
        indexed_passages = ingest_state["indexed_passages"]
        indexed_embeddings = ingest_state["indexed_embeddings"]
        skipped_unchanged = ingest_state["skipped_unchanged"]

        if indexed_pages:
            self._invalidate_dense_cache()

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        page_failures = [
            {"url": p.url, "status": p.status, "warnings": list(p.warnings)}
            for p in crawl_out.pages
            if isinstance(getattr(p, "status", None), str) and p.status != "ok"
        ]
        raw_warnings = getattr(crawl_out, "warnings", None)
        crawl_warnings = list(raw_warnings) if isinstance(raw_warnings, list) else []
        if indexed_pages == 0 and skipped_unchanged == 0:
            status = "no_reliable_result"
        elif page_failures or crawl_warnings:
            status = "partial"
        else:
            status = "ok"
        return {
            "status": status,
            "url": start_url,
            "pages_crawled": len(crawl_out.pages),
            "pages_indexed": indexed_pages,
            "passages_indexed": indexed_passages,
            "embeddings_indexed": indexed_embeddings,
            "embedding_model": (self.embedder.model_name if self.embedder is not None else None),
            "embedding_error": self._embedding_error,
            "skipped_unchanged": skipped_unchanged,
            "failures": crawl_warnings,
            "page_failures": page_failures,
            "ms": elapsed_ms,
            "db_path": str(self.db_path),
        }

    def _bm25_rows(self, fts_query: str, limit: int) -> list[tuple[int, str, str, int, int, str, float]]:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(
                """
                SELECT rowid, url, title, span_start, span_end, text,
                       bm25(kb_passages) as score
                FROM kb_passages
                WHERE kb_passages MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()

    def _dense_scores(self, question: str, limit: int) -> list[tuple[int, float]]:
        if self.embedder is None:
            return []
        model = self.embedder.model_name
        max_scan = int(getattr(self.service.s, "embedding_max_scan", 50_000))
        query_vector = self._encode_query(model, question)
        if not query_vector:
            return []
        query = _normalise_vector(query_vector)
        np = _try_numpy()
        if np is None:
            return self._dense_scores_python(query, limit, model, max_scan)

        query_array = np.asarray(query, dtype=np.float32)
        with self._dense_lock:
            db_stat = self.db_path.stat()
            signature = (db_stat.st_mtime_ns, db_stat.st_size)
            if self._dense_overflow == (model, *signature):
                raise _DenseScanLimitExceeded(f"dense scan exceeds {max_scan} indexed passages")
            cache = self._dense_cache
            if cache is not None and cache[0] == model and cache[4:] == signature:
                ids, matrix = cache[2], cache[3]
            else:
                with sqlite3.connect(self.db_path) as conn:
                    count = int(
                        conn.execute(
                            "SELECT COUNT(*) FROM kb_embeddings WHERE model = ?",
                            (model,),
                        ).fetchone()[0]
                    )
                    if count > max_scan:
                        self._dense_overflow = (model, *signature)
                        raise _DenseScanLimitExceeded(f"dense scan exceeds {max_scan} indexed passages")
                    ids, matrix = self._build_dense_matrix(conn, model, count, int(query_array.size), np)
                self._dense_cache = (
                    model,
                    count,
                    ids,
                    matrix,
                    *signature,
                )
                self._dense_overflow = None
            if ids.size == 0:
                return []

        scores = matrix @ query_array
        order = np.argsort(-scores, kind="stable")[:limit]
        return [(int(ids[int(index)]), float(scores[int(index)])) for index in order]

    def _build_dense_matrix(
        self,
        conn: sqlite3.Connection,
        model: str,
        count: int,
        dim: int,
        np: Any,
    ) -> tuple[Any, Any]:
        matrix = np.empty((count, dim), dtype=np.float32)
        ids = np.empty(count, dtype=np.int64)
        valid = 0
        cursor = conn.execute(
            "SELECT passage_rowid, vec FROM kb_embeddings WHERE model = ? ORDER BY passage_rowid LIMIT ?",
            (model, count),
        )
        for rowid, blob in cursor:
            vector = np.frombuffer(blob, dtype=np.float32)
            if vector.size != dim:
                continue
            matrix[valid] = vector
            ids[valid] = int(rowid)
            valid += 1
        if valid == 0:
            return ids[:0], matrix[:0]
        if valid < count:
            return ids[:valid].copy(), matrix[:valid].copy()
        return ids[:valid], matrix[:valid]

    def _dense_scores_python(
        self, query: list[float], limit: int, model: str, max_scan: int
    ) -> list[tuple[int, float]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT passage_rowid, vec FROM kb_embeddings WHERE model = ? LIMIT ?",
                (model, max_scan + 1),
            ).fetchall()
        if len(rows) > max_scan:
            raise _DenseScanLimitExceeded(f"dense scan exceeds {max_scan} indexed passages")
        scored: list[tuple[int, float]] = []
        for rowid, blob in rows:
            vector = _unpack_vector(blob)
            if len(vector) != len(query):
                continue
            scored.append((int(rowid), sum(a * b for a, b in zip(query, vector, strict=True))))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:limit]

    def _ground_dense_candidates(
        self,
        dense_scores: list[tuple[int, float]],
        terms: list[str],
    ) -> list[tuple[int, float]]:
        """Keep dense neighbours with lexical support or a strong similarity.

        Dense retrieval always returns nearest neighbours, even for a query
        whose topic is absent. A lexical match is sufficient; a dense-only
        neighbour must clear a conservative similarity floor so an unrelated
        page cannot answer a false-premise query.
        """
        if not dense_scores or not terms:
            return []
        details = self._fetch_passages([rowid for rowid, _ in dense_scores])
        wanted = set(terms)
        supported: list[tuple[int, float]] = []
        for rowid, score in dense_scores:
            row = details.get(rowid)
            if row is None:
                continue
            passage_tokens = set(tokenize(f"{row[2]} {row[5]}"))
            if wanted.intersection(passage_tokens) or score >= _DENSE_MIN_SCORE:
                supported.append((rowid, score))
        return supported

    def _fetch_passages(self, rowids: list[int]) -> dict[int, tuple[int, str, str, int, int, str]]:
        if not rowids:
            return {}
        placeholders = ",".join("?" for _ in rowids)
        query = (
            "SELECT rowid, url, title, span_start, span_end, text "  # noqa: S608
            f"FROM kb_passages WHERE rowid IN ({placeholders})"  # nosec B608
        )
        with sqlite3.connect(self.db_path) as conn:
            # nosec B608: the only interpolated text is a run of "?" placeholders
            # generated from an internal integer rowid list; every value is bound
            # through sqlite parameters, so no caller-controlled data reaches SQL.
            rows = conn.execute(query, rowids).fetchall()  # noqa: S608
        return {int(row[0]): row for row in rows}

    def _fuse(
        self,
        bm25_rows: list[tuple[int, str, str, int, int, str, float]],
        dense_scores: list[tuple[int, float]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        bm25_by_id = {int(row[0]): row for row in bm25_rows}
        bm25_rank = {int(row[0]): rank for rank, row in enumerate(bm25_rows, 1)}
        dense_rank = {int(rowid): rank for rank, (rowid, _score) in enumerate(dense_scores, 1)}
        dense_by_id = {int(rowid): score for rowid, score in dense_scores}

        fused: dict[int, float] = {}
        for rowid in set(bm25_rank) | set(dense_rank):
            score = 0.0
            if rowid in bm25_rank:
                score += 1.0 / (_RRF_K + bm25_rank[rowid])
            if rowid in dense_rank:
                score += 1.0 / (_RRF_K + dense_rank[rowid])
            fused[rowid] = score

        ordered = sorted(
            fused,
            key=lambda rowid: (
                -fused[rowid],
                bm25_rank.get(rowid, 10**9),
                dense_rank.get(rowid, 10**9),
            ),
        )[:top_k]
        details = self._fetch_passages(ordered)
        passages: list[dict[str, Any]] = []
        for rowid in ordered:
            row = details.get(rowid)
            if row is None:
                continue
            bm25 = bm25_by_id.get(rowid)
            passages.append(
                {
                    "url": row[1],
                    "title": row[2],
                    "span": [row[3], row[4]],
                    "text": row[5],
                    "score": round(fused[rowid], 6),
                    "signals": {
                        "bm25_rank": bm25_rank.get(rowid),
                        "dense_rank": dense_rank.get(rowid),
                        "bm25": round(float(bm25[6]), 6) if bm25 else None,
                        "dense": (round(float(dense_by_id[rowid]), 6) if rowid in dense_by_id else None),
                    },
                }
            )
        return passages

    async def query(
        self,
        question: str,
        *,
        top_k: int = 5,
        hybrid: bool = True,
    ) -> dict[str, Any]:
        """Query the local knowledge base using BM25 or hybrid BM25 + dense RRF."""
        t0 = time.perf_counter()
        fts_query = _build_fts_query(question)
        if not fts_query:
            return {
                "status": "ok",
                "q": question,
                "n": 0,
                "passages": [],
                "mode": "bm25",
                "warnings": [],
                "ms": int((time.perf_counter() - t0) * 1000),
            }

        candidate_limit = max(top_k * 8, 40)
        bm25_rows = await asyncio.to_thread(self._bm25_rows, fts_query, candidate_limit)

        terms, _phrases = query_terms(question)
        dense_scores: list[tuple[int, float]] = []
        warnings: list[str] = []
        if hybrid and self.embedder is not None:
            try:
                dense_scores = await asyncio.to_thread(self._dense_scores, question, candidate_limit)
            except _DenseScanLimitExceeded as exc:
                # The embedder is healthy; only this knowledge base is too
                # large for exact scanning. Keep hybrid available for smaller
                # instances instead of disabling it for the process lifetime.
                warnings.append(f"dense_unavailable:{exc}")
            except EmbeddingUnavailable as exc:
                self._disable_embedder(exc)
                warnings.append(f"dense_unavailable:{exc}")
            except Exception as exc:  # noqa: BLE001 - optional path
                # Keep the embedder enabled: a transient failure should not
                # permanently degrade this instance to BM25-only.
                warnings.append(f"dense_unavailable:{type(exc).__name__}:{exc}")

        dense_scores = await asyncio.to_thread(self._ground_dense_candidates, dense_scores, terms)
        if dense_scores:
            passages = self._fuse(bm25_rows, dense_scores, top_k)
            mode = "hybrid"
        else:
            passages = [
                {
                    "url": row[1],
                    "title": row[2],
                    "span": [row[3], row[4]],
                    "text": row[5],
                    "score": round(float(row[6]), 3),
                }
                for row in bm25_rows[:top_k]
            ]
            mode = "bm25"

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "status": "ok" if passages else "not_found",
            "q": question,
            "n": len(passages),
            "passages": passages,
            "mode": mode,
            "warnings": warnings,
            "ms": elapsed_ms,
        }

    def stats(self) -> dict[str, Any]:
        """Return knowledge base size and summary metrics."""
        with sqlite3.connect(self.db_path) as conn:
            doc_count = conn.execute("SELECT COUNT(*) FROM kb_docs").fetchone()[0]
            passage_count = conn.execute("SELECT COUNT(*) FROM kb_passages").fetchone()[0]
            embedding_count = conn.execute("SELECT COUNT(*) FROM kb_embeddings").fetchone()[0]
            model_row = conn.execute(
                "SELECT model, dim FROM kb_embeddings GROUP BY model, dim ORDER BY COUNT(*) DESC LIMIT 1"
            ).fetchone()
        size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        return {
            "documents": doc_count,
            "passages": passage_count,
            "embeddings": embedding_count,
            "embedding_model": (
                self.embedder.model_name if self.embedder is not None else (model_row[0] if model_row else None)
            ),
            "embedding_dim": (
                self.embedder.dim if self.embedder is not None else (int(model_row[1]) if model_row else 0)
            ),
            "embedding_error": self._embedding_error,
            "db_bytes": size_bytes,
            "db_path": str(self.db_path),
        }

    def clear(self) -> None:
        """Wipe the local knowledge base."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM kb_docs")
            conn.execute("DELETE FROM kb_passages")
            conn.execute("DELETE FROM kb_embeddings")
            conn.commit()
        self._invalidate_dense_cache()
