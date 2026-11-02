"""Crawl2RAG: Turn a website into a local searchable knowledge base.

Uses bounded polite crawling, SSRF checks on every link, clean semantic chunking
with exact source spans, and a local SQLite FTS5/BM25 index for zero-latency,
zero-cost retrieval with full source attribution.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..errors import BlockedURLError
from ..extract.passages import build_chunks
from ..service import WebLens


class Crawl2RAG:
    """Website-to-Knowledge-Base pipeline backed by local SQLite FTS5."""

    def __init__(self, service: WebLens, db_path: Path | str | None = None):
        self.service = service
        if db_path is None:
            db_path = service.s.cache_dir / "crawl2rag.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
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
            conn.commit()

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

        now_iso = datetime.now(UTC).isoformat()
        indexed_pages = 0
        indexed_passages = 0
        skipped_unchanged = 0

        with sqlite3.connect(self.db_path) as conn:
            for page in crawl_out.pages:
                text = (getattr(page, "text", "") or "").strip()
                if not text:
                    # Backwards-compatible fallback for crawlers that only
                    # expose budgeted passages/excerpts.
                    passages = getattr(page, "passages", None) or []
                    text = "\n\n".join(str(p.get("x", "")) for p in passages).strip()
                if not text:
                    text = (getattr(page, "excerpt", "") or "").strip()
                if not text:
                    continue

                page_tokens = getattr(page, "tokens", 0) or 0

                chash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                row = conn.execute(
                    "SELECT content_hash FROM kb_docs WHERE url = ?", (page.url,)
                ).fetchone()

                if row and row[0] == chash:
                    skipped_unchanged += 1
                    continue

                # Remove existing passages for this URL if updating
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

                indexed_pages += 1
            conn.commit()

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "status": "ok",
            "url": start_url,
            "pages_crawled": len(crawl_out.pages),
            "pages_indexed": indexed_pages,
            "passages_indexed": indexed_passages,
            "skipped_unchanged": skipped_unchanged,
            "failures": getattr(crawl_out, "failures", None)
            or getattr(crawl_out, "warnings", []),
            "ms": elapsed_ms,
            "db_path": str(self.db_path),
        }

    async def query(
        self,
        question: str,
        *,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Query local knowledge base using FTS5 BM25 ranking."""
        t0 = time.perf_counter()
        sanitized = re.sub(r"[^\w\s]", " ", question).strip()
        tokens = [t for t in sanitized.split() if len(t) > 2]
        if not tokens:
            return {
                "status": "ok",
                "q": question,
                "n": 0,
                "passages": [],
                "ms": int((time.perf_counter() - t0) * 1000),
            }

        fts_query = " OR ".join(tokens)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT url, title, span_start, span_end, text, bm25(kb_passages) as score
                FROM kb_passages
                WHERE kb_passages MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (fts_query, top_k),
            )
            rows = cursor.fetchall()

        passages = [
            {
                "url": r[0],
                "title": r[1],
                "span": [r[2], r[3]],
                "text": r[4],
                "score": round(r[5], 3),
            }
            for r in rows
        ]

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "status": "ok" if passages else "not_found",
            "q": question,
            "n": len(passages),
            "passages": passages,
            "ms": elapsed_ms,
        }

    def stats(self) -> dict[str, Any]:
        """Return knowledge base size and summary metrics."""
        with sqlite3.connect(self.db_path) as conn:
            doc_count = conn.execute("SELECT COUNT(*) FROM kb_docs").fetchone()[0]
            passage_count = conn.execute("SELECT COUNT(*) FROM kb_passages").fetchone()[0]
        size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        return {
            "documents": doc_count,
            "passages": passage_count,
            "db_bytes": size_bytes,
            "db_path": str(self.db_path),
        }

    def clear(self) -> None:
        """Wipe the local knowledge base."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM kb_docs")
            conn.execute("DELETE FROM kb_passages")
            conn.commit()
