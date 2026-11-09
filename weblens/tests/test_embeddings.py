"""Tests for optional local dense retrieval in Crawl2RAG."""

from __future__ import annotations

import math
import sqlite3
from array import array
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from weblens.apps import crawl2rag as crawl2rag_module
from weblens.apps.crawl2rag import Crawl2RAG
from weblens.apps.embeddings import (
    EmbeddingUnavailable,
    OnnxEmbedder,
    build_default_embedder,
)
from weblens.config import Settings
from weblens.service import WebLens


class FakeEmbedder:
    """Deterministic 3-d embedder with a semantic split for the test corpus."""

    model_name = "fake-mini"
    dim = 3

    def encode(self, texts):
        vectors = []
        for text in texts:
            low = text.lower()
            if any(
                term in low
                for term in (
                    "citation",
                    "evidence",
                    "attribution",
                    "source",
                    "provenance",
                    "lineage",
                )
            ):
                vectors.append([1.0, 0.0, 0.0])
            elif any(term in low for term in ("provider", "duckduckgo", "search", "router")):
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


class CountingEmbedder(FakeEmbedder):
    """Fake embedder that records every encode batch."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def encode(self, texts):
        items = list(texts)
        self.calls.append(items)
        return super().encode(items)


class FlakyEmbedder(FakeEmbedder):
    """Fake embedder that can fail a query embedding on demand."""

    def __init__(self):
        self.fail_queries = False

    def encode(self, texts):
        items = list(texts)
        if self.fail_queries and items == ["evidence"]:
            raise RuntimeError("temporary inference failure")
        return super().encode(items)


@pytest.fixture
def service():
    return WebLens()


def _crawl(pages):
    return MagicMock(pages=pages, failures=[])


def _page(url: str, title: str, text: str):
    return MagicMock(url=url, title=title, text=text, tokens=20)


@pytest.mark.asyncio
async def test_hybrid_query_finds_dense_match_without_lexical_overlap(service, tmp_path):
    kb = Crawl2RAG(
        service,
        db_path=tmp_path / "kb.db",
        embedder=FakeEmbedder(),
        auto_embedder=False,
    )
    pages = [
        _page(
            "https://docs.example.com/intro",
            "Intro",
            "WebLens prioritizes exact citations and source spans.",
        ),
        _page(
            "https://docs.example.com/api",
            "API",
            "The SearchRouter aggregates DuckDuckGo and Wikipedia providers.",
        ),
    ]

    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=_crawl(pages))):
        result = await kb.ingest("https://docs.example.com", max_pages=5)

    assert result["status"] == "ok"
    assert result["embeddings_indexed"] > 0
    assert result["embedding_model"] == "fake-mini"

    # Neither "provenance" nor "lineage" appears in the indexed text, so BM25
    # alone returns nothing. Dense retrieval must still recover the citation
    # passage and label the response as hybrid.
    out = await kb.query("provenance lineage", top_k=5)
    assert out["mode"] == "hybrid"
    assert out["warnings"] == []
    assert out["n"] >= 1
    assert out["passages"][0]["url"] == "https://docs.example.com/intro"
    assert out["passages"][0]["signals"]["dense_rank"] == 1

    forced_bm25 = await kb.query("provenance lineage", hybrid=False)
    assert forced_bm25["mode"] == "bm25"
    assert forced_bm25["n"] == 0


@pytest.mark.asyncio
async def test_hybrid_query_fuses_lexical_and_dense_rankings(service, tmp_path):
    kb = Crawl2RAG(
        service,
        db_path=tmp_path / "kb.db",
        embedder=FakeEmbedder(),
        auto_embedder=False,
    )
    pages = [
        _page(
            "https://docs.example.com/intro",
            "Intro",
            "WebLens prioritizes exact citations and evidence spans.",
        ),
        _page(
            "https://docs.example.com/api",
            "API",
            "The SearchRouter aggregates DuckDuckGo and Wikipedia providers.",
        ),
    ]

    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=_crawl(pages))):
        await kb.ingest("https://docs.example.com", max_pages=5)

    out = await kb.query("evidence first intelligence", top_k=5)
    assert out["mode"] == "hybrid"
    assert out["n"] >= 1
    top = out["passages"][0]
    assert top["url"] == "https://docs.example.com/intro"
    assert top["signals"]["bm25_rank"] == 1
    assert top["signals"]["dense_rank"] == 1


@pytest.mark.asyncio
async def test_dense_python_fallback_without_numpy(service, tmp_path, monkeypatch):
    monkeypatch.setattr(crawl2rag_module, "_try_numpy", lambda: None)
    kb = Crawl2RAG(
        service,
        db_path=tmp_path / "kb.db",
        embedder=FakeEmbedder(),
        auto_embedder=False,
    )
    pages = [
        _page(
            "https://docs.example.com/intro",
            "Intro",
            "WebLens prioritizes exact citations and evidence spans.",
        ),
        _page(
            "https://docs.example.com/api",
            "API",
            "The SearchRouter aggregates DuckDuckGo and Wikipedia providers.",
        ),
    ]
    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=_crawl(pages))):
        await kb.ingest("https://docs.example.com", max_pages=5)

    out = await kb.query("evidence", top_k=5)
    assert out["mode"] == "hybrid"
    assert out["n"] >= 1
    assert out["passages"][0]["url"] == "https://docs.example.com/intro"
    assert kb._dense_cache is None


@pytest.mark.asyncio
async def test_dense_cache_reuses_matrix_and_query_embedding(service, tmp_path):
    embedder = CountingEmbedder()
    kb = Crawl2RAG(
        service,
        db_path=tmp_path / "kb.db",
        embedder=embedder,
        auto_embedder=False,
    )
    pages = [
        _page(
            "https://docs.example.com/intro",
            "Intro",
            "WebLens prioritizes exact citations and evidence spans.",
        ),
        _page(
            "https://docs.example.com/api",
            "API",
            "The SearchRouter aggregates DuckDuckGo and Wikipedia providers.",
        ),
    ]
    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=_crawl(pages))):
        await kb.ingest("https://docs.example.com", max_pages=5)

    embedder.calls.clear()
    first = await kb.query("evidence", top_k=5)
    cache = kb._dense_cache
    assert first["mode"] == "hybrid"
    assert cache is not None

    second = await kb.query("evidence", top_k=5)
    assert second["mode"] == "hybrid"
    assert kb._dense_cache is cache
    first_rows = [(p["url"], tuple(p["span"]), p["text"]) for p in first["passages"]]
    second_rows = [(p["url"], tuple(p["span"]), p["text"]) for p in second["passages"]]
    assert first_rows == second_rows
    assert sum(call == ["evidence"] for call in embedder.calls) == 1


@pytest.mark.asyncio
async def test_dense_cache_invalidated_by_ingest(service, tmp_path):
    kb = Crawl2RAG(
        service,
        db_path=tmp_path / "kb.db",
        embedder=FakeEmbedder(),
        auto_embedder=False,
    )
    first_page = _page(
        "https://docs.example.com/intro",
        "Intro",
        "WebLens prioritizes exact citations and evidence spans.",
    )
    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=_crawl([first_page]))):
        await kb.ingest("https://docs.example.com", max_pages=5)

    out = await kb.query("evidence", top_k=5)
    assert out["mode"] == "hybrid"
    assert kb._dense_cache is not None

    second_page = _page(
        "https://docs.example.com/security",
        "Security",
        "The injection detector blocks untrusted instructions.",
    )
    with patch.object(
        service.crawler,
        "crawl",
        new=AsyncMock(return_value=_crawl([second_page])),
    ):
        await kb.ingest("https://docs.example.com", max_pages=5)

    assert kb._dense_cache is None
    rebuilt = await kb.query("evidence", top_k=5)
    assert rebuilt["mode"] == "hybrid"
    assert kb._dense_cache is not None


@pytest.mark.asyncio
async def test_noop_ingest_keeps_dense_cache(service, tmp_path):
    kb = Crawl2RAG(
        service,
        db_path=tmp_path / "kb.db",
        embedder=FakeEmbedder(),
        auto_embedder=False,
    )
    page = _page(
        "https://docs.example.com/intro",
        "Intro",
        "WebLens prioritizes exact citations and evidence spans.",
    )
    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=_crawl([page]))):
        await kb.ingest("https://docs.example.com", max_pages=5)

    await kb.query("evidence", top_k=5)
    cache = kb._dense_cache
    assert cache is not None

    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=_crawl([page]))):
        result = await kb.ingest("https://docs.example.com", max_pages=5)

    assert result["skipped_unchanged"] == 1
    assert kb._dense_cache is cache


@pytest.mark.asyncio
async def test_dense_cache_invalidated_by_clear(service, tmp_path):
    kb = Crawl2RAG(
        service,
        db_path=tmp_path / "kb.db",
        embedder=FakeEmbedder(),
        auto_embedder=False,
    )
    page = _page(
        "https://docs.example.com/intro",
        "Intro",
        "WebLens prioritizes exact citations and evidence spans.",
    )
    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=_crawl([page]))):
        await kb.ingest("https://docs.example.com", max_pages=5)

    await kb.query("evidence", top_k=5)
    assert kb._dense_cache is not None

    kb.clear()
    assert kb._dense_cache is None
    out = await kb.query("evidence", top_k=5)
    assert out["mode"] == "bm25"
    assert out["n"] == 0


@pytest.mark.asyncio
async def test_dense_cache_rebuilds_when_index_changes_externally(service, tmp_path):
    kb = Crawl2RAG(
        service,
        db_path=tmp_path / "kb.db",
        embedder=FakeEmbedder(),
        auto_embedder=False,
    )
    page = _page(
        "https://docs.example.com/intro",
        "Intro",
        "WebLens prioritizes exact citations and evidence spans.",
    )
    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=_crawl([page]))):
        await kb.ingest("https://docs.example.com", max_pages=5)

    await kb.query("evidence", top_k=5)
    cache = kb._dense_cache
    assert cache is not None
    before_count = cache[1]

    extra_text = "Evidence remains traceable to its original source span."
    extra_url = "https://docs.example.com/extra"
    with sqlite3.connect(kb.db_path) as conn:
        conn.execute(
            "INSERT INTO kb_passages (url, title, passage_index, span_start, span_end, text) VALUES (?, ?, ?, ?, ?, ?)",
            (extra_url, "Extra", 0, 0, len(extra_text), extra_text),
        )
        rowid = conn.execute("SELECT rowid FROM kb_passages WHERE url = ?", (extra_url,)).fetchone()[0]
        conn.execute(
            "INSERT INTO kb_embeddings (passage_rowid, url, model, dim, vec) VALUES (?, ?, ?, ?, ?)",
            (
                rowid,
                extra_url,
                "fake-mini",
                3,
                array("f", [1.0, 0.0, 0.0]).tobytes(),
            ),
        )
        conn.commit()

    out = await kb.query("evidence", top_k=5)
    assert out["mode"] == "hybrid"
    assert kb._dense_cache is not cache
    assert kb._dense_cache[1] == before_count + 1
    assert any(passage["url"] == extra_url for passage in out["passages"])


@pytest.mark.asyncio
async def test_transient_dense_error_keeps_embedder_enabled(service, tmp_path):
    embedder = FlakyEmbedder()
    kb = Crawl2RAG(
        service,
        db_path=tmp_path / "kb.db",
        embedder=embedder,
        auto_embedder=False,
    )
    pages = [
        _page(
            "https://docs.example.com/intro",
            "Intro",
            "WebLens prioritizes exact citations and evidence spans.",
        ),
        _page(
            "https://docs.example.com/api",
            "API",
            "The SearchRouter aggregates DuckDuckGo and Wikipedia providers.",
        ),
    ]
    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=_crawl(pages))):
        await kb.ingest("https://docs.example.com", max_pages=5)

    embedder.fail_queries = True
    degraded = await kb.query("evidence", top_k=5)
    assert degraded["mode"] == "bm25"
    assert any("temporary inference failure" in warning for warning in degraded["warnings"])
    assert kb.embedder is embedder
    assert kb._embedding_error is None
    assert kb._dense_cache is None

    embedder.fail_queries = False
    recovered = await kb.query("evidence", top_k=5)
    assert recovered["mode"] == "hybrid"
    assert recovered["warnings"] == []
    assert kb.embedder is embedder


@pytest.mark.asyncio
async def test_bm25_only_when_embeddings_are_disabled(service, tmp_path):
    kb = Crawl2RAG(
        service,
        db_path=tmp_path / "kb.db",
        auto_embedder=False,
    )
    pages = [
        _page(
            "https://docs.example.com/intro",
            "Intro",
            "WebLens prioritizes exact citations and evidence spans for every answer.",
        )
    ]

    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=_crawl(pages))):
        result = await kb.ingest("https://docs.example.com", max_pages=5)

    assert result["embeddings_indexed"] == 0
    assert result["embedding_model"] is None
    out = await kb.query("exact citations")
    assert out["mode"] == "bm25"
    assert out["n"] == 1


@pytest.mark.asyncio
async def test_failed_embedder_falls_back_and_reports_error(service, tmp_path):
    class BrokenEmbedder:
        model_name = "broken"
        dim = 3

        def encode(self, texts):
            raise EmbeddingUnavailable("model files missing")

    kb = Crawl2RAG(
        service,
        db_path=tmp_path / "kb.db",
        embedder=BrokenEmbedder(),
        auto_embedder=False,
    )
    pages = [
        _page(
            "https://docs.example.com/intro",
            "Intro",
            "WebLens prioritizes exact citations and evidence spans for every answer.",
        )
    ]

    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=_crawl(pages))):
        result = await kb.ingest("https://docs.example.com", max_pages=5)

    assert result["status"] == "ok"
    assert "model files missing" in result["embedding_error"]
    assert result["embeddings_indexed"] == 0

    out = await kb.query("exact citations")
    assert out["mode"] == "bm25"
    assert out["n"] == 1


@pytest.mark.asyncio
async def test_stats_and_clear_include_embeddings(service, tmp_path):
    kb = Crawl2RAG(
        service,
        db_path=tmp_path / "kb.db",
        embedder=FakeEmbedder(),
        auto_embedder=False,
    )
    pages = [
        _page(
            "https://docs.example.com/intro",
            "Intro",
            "WebLens prioritizes exact citations and evidence spans for every answer.",
        )
    ]

    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=_crawl(pages))):
        await kb.ingest("https://docs.example.com", max_pages=5)

    stats = kb.stats()
    assert stats["documents"] == 1
    assert stats["passages"] > 0
    assert stats["embeddings"] == stats["passages"]
    assert stats["embedding_model"] == "fake-mini"
    assert stats["embedding_dim"] == 3

    kb.clear()
    cleared = kb.stats()
    assert cleared["documents"] == 0
    assert cleared["passages"] == 0
    assert cleared["embeddings"] == 0


@pytest.mark.asyncio
async def test_dense_scan_cap_falls_back_to_bm25(tmp_path):
    service = WebLens(Settings(cache_dir=tmp_path, embedding_max_scan=1))
    kb = Crawl2RAG(
        service,
        db_path=tmp_path / "kb.db",
        embedder=FakeEmbedder(),
        auto_embedder=False,
    )
    pages = [
        _page(
            "https://docs.example.com/intro",
            "Intro",
            "WebLens prioritizes exact citations and evidence spans for every answer.",
        ),
        _page(
            "https://docs.example.com/api",
            "API",
            "The SearchRouter aggregates DuckDuckGo and Wikipedia providers.",
        ),
    ]

    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=_crawl(pages))):
        await kb.ingest("https://docs.example.com", max_pages=5)

    out = await kb.query("evidence", top_k=5)
    assert out["mode"] == "bm25"
    assert out["n"] >= 1
    assert any("dense scan exceeds" in warning for warning in out["warnings"])
    assert kb.embedder is not None
    assert kb._embedding_error is None
    assert kb._dense_cache is None
    assert kb._dense_overflow is not None

    again = await kb.query("evidence", top_k=5)
    assert again["mode"] == "bm25"
    assert any("dense scan exceeds" in warning for warning in again["warnings"])

    # A healthy embedder must stay available after a size-based fallback.
    kb.clear()
    assert kb._dense_cache is None
    assert kb._dense_overflow is None
    small_page = _page(
        "https://docs.example.com/evidence",
        "Evidence",
        "Evidence spans remain attached to every cited answer.",
    )
    with patch.object(service.crawler, "crawl", new=AsyncMock(return_value=_crawl([small_page]))):
        await kb.ingest("https://docs.example.com", max_pages=5)

    recovered = await kb.query("evidence", top_k=5)
    assert recovered["mode"] == "hybrid"
    assert recovered["warnings"] == []
    assert kb.embedder is not None
    assert kb._dense_overflow is None


def test_missing_onnx_model_raises_unavailable(tmp_path):
    embedder = OnnxEmbedder(tmp_path / "missing")
    with pytest.raises(EmbeddingUnavailable):
        embedder.encode(["hello"])


def test_build_default_embedder_honours_disabled_flag(tmp_path):
    settings = Settings(
        cache_dir=tmp_path,
        embedding_enabled=False,
        embedding_model_dir=tmp_path / "model",
    )
    assert build_default_embedder(settings) is None


def test_build_default_embedder_without_model_returns_none(tmp_path):
    settings = Settings(
        cache_dir=tmp_path,
        embedding_enabled=True,
        embedding_model_dir=tmp_path / "missing",
    )
    assert build_default_embedder(settings) is None


def test_real_onnx_embedder_if_model_is_present():
    embedder = build_default_embedder(Settings())
    if embedder is None:
        pytest.skip("optional ONNX embedding model is not installed")

    vectors = embedder.encode(["hello world", "hello world"])
    assert len(vectors) == 2
    assert len(vectors[0]) == embedder.dim == 384
    assert math.isclose(sum(value * value for value in vectors[0]), 1.0, rel_tol=1e-5)
    similarity = sum(a * b for a, b in zip(vectors[0], vectors[1], strict=True))
    assert similarity > 0.99


def test_model_dir_expands_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    settings = Settings(embedding_model_dir=Path("~/models/mini"))
    assert settings.embedding_model_dir == tmp_path / "models" / "mini"
