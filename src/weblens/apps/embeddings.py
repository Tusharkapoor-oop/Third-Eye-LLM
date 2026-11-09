"""Optional local ONNX sentence embeddings for hybrid Crawl2RAG retrieval.

The default search stack stays lexical: SQLite FTS5/BM25 needs no model and no
network.  When a local all-MiniLM-L6-v2 ONNX directory is present, Crawl2RAG can
add dense candidates and fuse them with BM25 using reciprocal rank fusion.  The
imports are deliberately lazy so installing WebLens without the ``hybrid`` extra
still works and the package never downloads a model implicitly.
"""

from __future__ import annotations

from collections.abc import Sequence
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Protocol

from ..config import Settings

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"


class EmbeddingUnavailable(RuntimeError):
    """Raised when optional embedding dependencies or model files are missing."""


class Embedder(Protocol):
    """Minimal interface Crawl2RAG needs from a sentence embedder."""

    model_name: str
    dim: int

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one L2-normalised vector per input text."""


def _model_candidates(settings: Settings) -> list[Path]:
    # An explicit model directory is authoritative: if the user points at a
    # missing path we fail closed instead of silently loading a different model.
    if settings.embedding_model_dir is not None:
        return [Path(settings.embedding_model_dir).expanduser()]
    return [
        settings.cache_dir / "models" / DEFAULT_MODEL_NAME,
        Path.home() / ".cache" / "weblens" / "models" / DEFAULT_MODEL_NAME,
    ]


def default_model_dir(settings: Settings) -> Path | None:
    """Return the first local model directory containing both required files."""
    for candidate in _model_candidates(settings):
        if (candidate / "model.onnx").is_file() and (candidate / "tokenizer.json").is_file():
            return candidate
    return None


def build_default_embedder(settings: Settings) -> OnnxEmbedder | None:
    """Build the local ONNX embedder when the model and optional deps exist.

    Returning ``None`` is intentional: hybrid search is an enhancement, not a
    hard dependency.  Callers should continue with BM25-only retrieval.
    """
    if not settings.embedding_enabled:
        return None
    model_dir = default_model_dir(settings)
    if model_dir is None:
        return None

    # Probe for the optional packages without importing them. The heavy ONNX
    # and tokenizer imports stay lazy until the first encode call, so starting
    # the MCP server does not pay that cost when hybrid search is unused.
    if any(find_spec(name) is None for name in ("numpy", "onnxruntime", "tokenizers")):
        return None

    return OnnxEmbedder(
        model_dir,
        max_length=settings.embedding_max_length,
        batch_size=settings.embedding_batch_size,
    )


class OnnxEmbedder:
    """CPU-only mean-pooled encoder for a local all-MiniLM-L6-v2 ONNX model."""

    def __init__(
        self,
        model_dir: Path | str,
        *,
        max_length: int = 256,
        batch_size: int = 16,
        model_name: str = DEFAULT_MODEL_NAME,
    ):
        self.model_dir = Path(model_dir).expanduser()
        self.max_length = max(8, int(max_length))
        self.batch_size = max(1, int(batch_size))
        self.model_name = model_name
        self.dim = 384
        self._session: Any = None
        self._tokenizer: Any = None
        self._np: Any = None

    def _ensure_loaded(self) -> None:
        if self._session is not None:
            return

        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:  # pragma: no cover - depends on optional extras
            raise EmbeddingUnavailable("hybrid search requires numpy, onnxruntime, and tokenizers") from exc

        model_path = self.model_dir / "model.onnx"
        tokenizer_path = self.model_dir / "tokenizer.json"
        if not model_path.is_file() or not tokenizer_path.is_file():
            raise EmbeddingUnavailable(f"embedding model not found under {self.model_dir}")

        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        self._session = ort.InferenceSession(
            str(model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.enable_truncation(max_length=self.max_length)
        self._np = np

    def _encode_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if self._session is None or self._tokenizer is None or self._np is None:
            raise EmbeddingUnavailable("embedder is not loaded")
        np = self._np

        encodings = self._tokenizer.encode_batch([str(t) for t in texts])
        width = min(
            self.max_length,
            max((len(e.ids) for e in encodings), default=1),
        )
        width = max(1, width)
        ids = np.zeros((len(encodings), width), dtype=np.int64)
        mask = np.zeros((len(encodings), width), dtype=np.int64)
        for row, encoding in enumerate(encodings):
            values = encoding.ids[:width]
            ids[row, : len(values)] = values
            mask[row, : len(values)] = encoding.attention_mask[:width]

        token_type_ids = np.zeros_like(ids)
        outputs = self._session.run(
            None,
            {
                "input_ids": ids,
                "attention_mask": mask,
                "token_type_ids": token_type_ids,
            },
        )
        hidden = outputs[0]
        weights = mask[..., None].astype(np.float32)
        pooled = (hidden * weights).sum(axis=1) / np.maximum(weights.sum(axis=1), 1e-9)
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        pooled = pooled / np.maximum(norms, 1e-9)
        vectors = pooled.astype(np.float32, copy=False)
        self.dim = int(vectors.shape[1])
        return vectors.tolist()

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_loaded()
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self._encode_batch(texts[start : start + self.batch_size]))
        return vectors
