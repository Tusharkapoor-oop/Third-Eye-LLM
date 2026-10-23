"""Token budgeting and measurement.

R1: every result earns its tokens. The estimator uses tiktoken cl100k_base lazily
(measured in bench/baseline.json; see docs/benchmark-method.md). If tiktoken is
missing we fall back to a calibrated char->token ratio for estimation ONLY of a
hard cap - never for reported metrics (metrics require the real tokenizer).
"""
from __future__ import annotations

import os
from typing import List, Sequence

_TOKENIZER_NAME = os.environ.get("WEBINTEL_TOKENIZER", "cl100k_base")
_enc = None  # lazy
_ratio_fallback = 3.6  # chars/token; only used to enforce a cap, never reported


def _get_enc():
    global _enc
    if _enc is None:
        try:
            import tiktoken
            _enc = tiktoken.get_encoding(_TOKENIZER_NAME)
        except Exception:
            _enc = False  # permanent fallback
    return _enc


def count_tokens(text: str) -> int:
    """Real tokenizer count (used for reported metrics)."""
    enc = _get_enc()
    if enc:
        return len(enc.encode(text))
    return int(len(text) / _ratio_fallback)


def estimate_tokens(text: str) -> int:
    """Cheap estimate for budget enforcement only."""
    return count_tokens(text) if len(text) < 20_000 else int(len(text) / _ratio_fallback)


class TokenBudget:
    """Accumulates a bounded budget; objects are admitted while it fits."""

    def __init__(self, max_tokens: int):
        self.max = max_tokens
        self.used = 0
        self.dropped = 0

    def remaining(self) -> int:
        return max(0, self.max - self.used)

    def admit(self, text: str, est: int | None = None) -> bool:
        n = estimate_tokens(text) if est is None else est
        if self.used + n <= self.max:
            self.used += n
            return True
        self.dropped += 1
        return False


def trim_text(text: str, max_tokens: int) -> str:
    """Hard-truncate text to roughly max_tokens (estimate-based)."""
    est = estimate_tokens(text)
    if est <= max_tokens:
        return text
    # binary search cut point by chars
    target_chars = int(len(text) * max_tokens / est)
    for cut in range(target_chars, max(0, target_chars - 400), -50):
        if estimate_tokens(text[:cut]) <= max_tokens:
            return text[:cut].rstrip()
    return text[:target_chars]


def json_tokens(obj) -> int:
    """Tokens of a JSON-serialized object as the model will see it (compact, 1-line)."""
    import json
    return count_tokens(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def shortest(values: Sequence[str]) -> str:
    return min(values, key=len) if values else ""
