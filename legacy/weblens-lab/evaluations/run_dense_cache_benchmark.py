"""Measure exact dense retrieval with and without the in-memory matrix cache.

This is a synthetic, local-only benchmark. It creates a temporary SQLite index
with a fixed embedding dimension and measures the cost of rebuilding the dense
matrix for every query versus reusing the cached matrix. No network, model
download, or external corpus is involved.

Example:
    python weblens-lab/evaluations/run_dense_cache_benchmark.py \
        --sizes 1000,5000,10000,50000 --repeats 3
"""

from __future__ import annotations

import argparse
import gc
import json
import sqlite3
import statistics
import sys
import tempfile
import time
from array import array
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "weblens" / "src"))

from weblens.apps.crawl2rag import Crawl2RAG  # noqa: E402
from weblens.config import Settings  # noqa: E402

DIM = 384
MODEL = "bench-384"


class BenchEmbedder:
    """Deterministic 384-d embedder; the actual values are irrelevant here."""

    model_name = MODEL
    dim = DIM

    def encode(self, texts):
        return [[1.0] + [0.0] * (DIM - 1) for _ in texts]


def _median_ms(fn, repeats: int) -> tuple[float, list[float]]:
    samples: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return statistics.median(samples), samples


def _build_index(n_rows: int, tmp_path: Path) -> Crawl2RAG:
    settings = Settings(cache_dir=tmp_path, embedding_max_scan=n_rows + 1)
    service = SimpleNamespace(s=settings)
    kb = Crawl2RAG(
        service,
        db_path=tmp_path / f"bench_{n_rows}.db",
        embedder=BenchEmbedder(),
        auto_embedder=False,
    )
    vector = array("f", [1.0] + [0.0] * (DIM - 1)).tobytes()
    with sqlite3.connect(kb.db_path) as conn:
        conn.executemany(
            "INSERT INTO kb_embeddings (passage_rowid, url, model, dim, vec) VALUES (?, ?, ?, ?, ?)",
            ((rowid, f"https://bench.example/{rowid}", MODEL, DIM, vector) for rowid in range(1, n_rows + 1)),
        )
        conn.commit()
    return kb


def run_size(n_rows: int, repeats: int, tmp_path: Path) -> dict:
    kb = _build_index(n_rows, tmp_path)
    limit = 40

    # Warm the query-embedding cache and confirm both paths work.
    kb._dense_scores("bench query", limit)
    kb._dense_cache = None
    kb._dense_scores("bench query", limit)

    def rebuild() -> None:
        kb._dense_cache = None
        kb._dense_scores("bench query", limit)

    def cached() -> None:
        kb._dense_scores("bench query", limit)

    rebuild_ms, rebuild_samples = _median_ms(rebuild, repeats)
    cached_ms, cached_samples = _median_ms(cached, repeats)
    speedup = rebuild_ms / cached_ms if cached_ms > 0 else None
    return {
        "rows": n_rows,
        "rebuild_ms": round(rebuild_ms, 3),
        "cached_ms": round(cached_ms, 3),
        "speedup": round(speedup, 2) if speedup is not None else None,
        "rebuild_samples_ms": [round(value, 3) for value in rebuild_samples],
        "cached_samples_ms": [round(value, 3) for value in cached_samples],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sizes",
        default="1000,5000,10000,50000",
        help="Comma-separated passage counts to benchmark.",
    )
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args(argv)
    sizes = [int(value) for value in args.sizes.split(",") if value.strip()]
    if not sizes or any(size < 1 for size in sizes):
        parser.error("--sizes must contain positive integers")
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")

    with tempfile.TemporaryDirectory(prefix="weblens-dense-bench-") as tmp:
        tmp_path = Path(tmp)
        for size in sizes:
            print(json.dumps(run_size(size, args.repeats, tmp_path)))
            # Let CPython finalize benchmark-held SQLite connections before
            # TemporaryDirectory cleanup so Windows releases the DB file.
            gc.collect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
