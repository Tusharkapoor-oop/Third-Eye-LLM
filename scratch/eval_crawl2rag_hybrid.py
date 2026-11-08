"""Local technical-docs Recall@5 check for Crawl2RAG BM25 vs hybrid retrieval.

This is a scratch diagnostic, not an official benchmark report. It fetches a
small set of Python standard-library documentation pages, indexes the extracted
markdown into Crawl2RAG, and measures whether the target page appears in the
top 5 for BM25-only and hybrid dense + BM25 retrieval.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "weblens" / "src"))

from weblens.apps.crawl2rag import Crawl2RAG  # noqa: E402
from weblens.service import WebLens  # noqa: E402

BASE = "https://docs.python.org/3/library/"

CORPUS = [
    "asyncio-task.html",
    "pathlib.html",
    "sqlite3.html",
    "json.html",
    "re.html",
    "typing.html",
    "dataclasses.html",
    "unittest.mock.html",
    "urllib.parse.html",
    "logging.html",
    "argparse.html",
    "heapq.html",
    "collections.html",
    "threading.html",
    "multiprocessing.html",
    "http.server.html",
    "csv.html",
    "datetime.html",
    "inspect.html",
    "textwrap.html",
]

QUERIES = [
    ("How do I run multiple coroutines concurrently?", "asyncio-task.html"),
    ("How do I join a directory and a filename into a path?", "pathlib.html"),
    ("How can I avoid SQL injection when building statements?", "sqlite3.html"),
    ("How do I turn a Python mapping into a serialized text representation?", "json.html"),
    ("How do I check whether a pattern occurs at the beginning of a string?", "re.html"),
    ("How do I declare a value that may be an integer or a string?", "typing.html"),
    ("How do I automatically generate init and repr methods for a class?", "dataclasses.html"),
    ("How do I test code that depends on an external service without calling it?", "unittest.mock.html"),
    ("How do I percent-encode a query string?", "urllib.parse.html"),
    ("How do I send log messages to a file with a chosen level?", "logging.html"),
    ("How do I add a required positional argument to a command line program?", "argparse.html"),
    ("How do I remove and return the smallest item from a heap?", "heapq.html"),
    ("How do I get a default value for a missing dictionary key?", "collections.html"),
    ("How do I run a function in a background thread?", "threading.html"),
    ("How do I start a new operating system process?", "multiprocessing.html"),
    ("How do I serve the current directory over HTTP?", "http.server.html"),
    ("How do I read comma-separated values into a list of rows?", "csv.html"),
    ("How do I parse a date from an ISO 8601 string?", "datetime.html"),
    ("How do I retrieve the source code of a Python function?", "inspect.html"),
    ("How do I wrap a long paragraph to a fixed width?", "textwrap.html"),
    ("How do I create a full-text search virtual table?", "sqlite3.html"),
]


async def main() -> None:
    service = WebLens()
    pages = []
    for name in CORPUS:
        url = BASE + name
        out = await service.extract(url, full=True)
        if out.get("status") != "ok" or not out.get("x"):
            print(f"SKIP {url}: {out.get('status')}")
            continue
        pages.append(
            MagicMock(
                url=url,
                title=out.get("t") or name,
                text=out["x"],
                tokens=out.get("tok") or 0,
            )
        )
    print(f"indexed_pages={len(pages)}")

    db_path = Path(__file__).resolve().parent / "crawl2rag_hybrid.db"
    db_path.unlink(missing_ok=True)
    kb = Crawl2RAG(service, db_path=db_path, auto_embedder=True)
    with patch.object(
        service.crawler,
        "crawl",
        new=AsyncMock(return_value=MagicMock(pages=pages, failures=[])),
    ):
        result = await kb.ingest("https://docs.python.org/3/library/", max_pages=100)
    print(
        "ingest",
        json.dumps(
            {
                k: result.get(k)
                for k in (
                    "status",
                    "pages_indexed",
                    "passages_indexed",
                    "embeddings_indexed",
                    "embedding_model",
                    "embedding_error",
                    "ms",
                )
            }
        )
    )

    rows = []
    for query, target in QUERIES:
        target_url = BASE + target
        bm25 = await kb.query(query, top_k=5, hybrid=False)
        hybrid = await kb.query(query, top_k=5, hybrid=True)
        bm25_urls = [p["url"] for p in bm25["passages"]]
        hybrid_urls = [p["url"] for p in hybrid["passages"]]
        rows.append(
            {
                "query": query,
                "target": target_url,
                "bm25_hit": target_url in bm25_urls,
                "hybrid_hit": target_url in hybrid_urls,
                "bm25_mode": bm25["mode"],
                "hybrid_mode": hybrid["mode"],
                "bm25_top": bm25_urls,
                "hybrid_top": hybrid_urls,
            }
        )
        print(
            f"{'BM25=Y' if rows[-1]['bm25_hit'] else 'BM25=N'} "
            f"{'HYB=Y' if rows[-1]['hybrid_hit'] else 'HYB=N'} "
            f"{query}"
        )
        if not rows[-1]["bm25_hit"] or not rows[-1]["hybrid_hit"]:
            print("  bm25:", bm25_urls)
            print("  hyb :", hybrid_urls)

    bm25_recall = sum(r["bm25_hit"] for r in rows) / len(rows)
    hybrid_recall = sum(r["hybrid_hit"] for r in rows) / len(rows)
    print(
        f"n={len(rows)} bm25_recall@5={bm25_recall:.3f} "
        f"hybrid_recall@5={hybrid_recall:.3f}"
    )
    out_path = Path(__file__).resolve().parent / "crawl2rag_hybrid_results.jsonl"
    out_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    print("wrote", out_path)
    await service.close()


if __name__ == "__main__":
    asyncio.run(main())
