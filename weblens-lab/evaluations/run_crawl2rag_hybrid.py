"""Recall@5 gate for Crawl2RAG BM25 vs local dense + BM25 hybrid retrieval.

The dataset names a small technical-documentation corpus and one target page per
query. Pages are extracted through the normal WebLens extraction path, then
indexed through Crawl2RAG. The runner compares BM25-only and hybrid retrieval
and exits non-zero when the hybrid Recall@5 gate is missed.

This is a local diagnostic. It is not a hosted benchmark and it does not report
latency or answer quality.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent.parent
# Canonical source. The root src/weblens tree is a mirror; importing both risks
# silently measuring an older copy of Crawl2RAG.
sys.path.insert(0, str(ROOT / "weblens" / "src"))

from weblens.apps.crawl2rag import Crawl2RAG  # noqa: E402
from weblens.config import Settings  # noqa: E402
from weblens.service import WebLens  # noqa: E402

DEFAULT_DATASET = ROOT / "weblens-lab" / "datasets" / "crawl2rag_technical_v1.json"
DEFAULT_DB = ROOT / "weblens-lab" / "sandbox" / "temporary" / "crawl2rag_hybrid.db"
DEFAULT_CACHE = ROOT / "weblens-lab" / "sandbox" / "temporary" / "crawl2rag_cache"


async def _load_pages(service: WebLens, dataset: dict) -> list[MagicMock]:
    base = dataset["base_url"]
    pages: list[MagicMock] = []
    for name in dataset["pages"]:
        url = base + name
        out = await service.extract(url, full=True)
        if out.get("status") != "ok" or not out.get("x"):
            print(f"skip {url}: {out.get('status')}")
            continue
        pages.append(
            MagicMock(
                url=url,
                title=out.get("t") or name,
                text=out["x"],
                tokens=out.get("tok") or 0,
            )
        )
    return pages


async def run(args: argparse.Namespace) -> int:
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    settings = Settings(
        cache_dir=args.cache,
        embedding_enabled=True,
        embedding_model_dir=args.model_dir,
    )
    service = WebLens(settings)
    try:
        pages = await _load_pages(service, dataset)
        if len(pages) < args.min_pages:
            print(
                json.dumps(
                    {
                        "error": "too_few_pages",
                        "indexed_pages": len(pages),
                        "min_pages": args.min_pages,
                    }
                )
            )
            return 2

        args.db.parent.mkdir(parents=True, exist_ok=True)
        args.db.unlink(missing_ok=True)
        kb = Crawl2RAG(service, db_path=args.db, auto_embedder=True)
        with patch.object(
            service.crawler,
            "crawl",
            new=AsyncMock(return_value=MagicMock(pages=pages, failures=[])),
        ):
            ingest = await kb.ingest(
                dataset["base_url"], max_pages=len(pages) + 5
            )

        if args.require_hybrid and (
            not ingest.get("embeddings_indexed")
            or ingest.get("embedding_error")
            or ingest.get("embedding_model") is None
        ):
            print(
                json.dumps(
                    {
                        "error": "hybrid_required_but_unavailable",
                        "ingest": ingest,
                    }
                )
            )
            return 2

        rows = []
        for item in dataset["queries"]:
            query = item["q"]
            target = dataset["base_url"] + item["target"]
            bm25 = await kb.query(query, top_k=5, hybrid=False)
            hybrid = await kb.query(query, top_k=5, hybrid=True)
            bm25_urls = [p["url"] for p in bm25["passages"]]
            hybrid_urls = [p["url"] for p in hybrid["passages"]]
            row = {
                "q": query,
                "target": target,
                "bm25_hit": target in bm25_urls,
                "hybrid_hit": target in hybrid_urls,
                "bm25_mode": bm25["mode"],
                "hybrid_mode": hybrid["mode"],
                "bm25_top": bm25_urls,
                "hybrid_top": hybrid_urls,
            }
            rows.append(row)
            if args.verbose or not (row["bm25_hit"] and row["hybrid_hit"]):
                print(
                    f"{'BM25=Y' if row['bm25_hit'] else 'BM25=N'} "
                    f"{'HYB=Y' if row['hybrid_hit'] else 'HYB=N'} {query}"
                )
                if not row["hybrid_hit"] or not row["bm25_hit"]:
                    print("  bm25:", bm25_urls)
                    print("  hyb :", hybrid_urls)

        n = len(rows)
        if args.require_hybrid:
            fallbacks = [r["q"] for r in rows if r["hybrid_mode"] != "hybrid"]
            if fallbacks:
                print(
                    json.dumps(
                        {
                            "error": "hybrid_mode_fallback",
                            "queries": fallbacks,
                        }
                    )
                )
                return 2

        bm25_recall = sum(r["bm25_hit"] for r in rows) / n if n else 0.0
        hybrid_recall = sum(r["hybrid_hit"] for r in rows) / n if n else 0.0
        summary = {
            "dataset": dataset.get("name"),
            "pages": len(pages),
            "passages": ingest.get("passages_indexed"),
            "embeddings": ingest.get("embeddings_indexed"),
            "embedding_model": ingest.get("embedding_model"),
            "embedding_error": ingest.get("embedding_error"),
            "n": n,
            "bm25_recall@5": round(bm25_recall, 4),
            "hybrid_recall@5": round(hybrid_recall, 4),
            "hybrid_modes": sorted({r["hybrid_mode"] for r in rows}),
            "threshold": args.threshold,
            "gate": "pass" if hybrid_recall >= args.threshold else "fail",
        }
        print(json.dumps(summary, indent=2))
        return 0 if hybrid_recall >= args.threshold else 1
    finally:
        await service.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument("--min-pages", type=int, default=20)
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument("--require-hybrid", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
