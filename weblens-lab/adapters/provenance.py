"""Shared provenance and status helpers for evaluation adapters."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def results_hash(items: list[Any]) -> str:
    serializable = []
    for item in items:
        if hasattr(item, "__dict__"):
            serializable.append(
                {
                    "url": getattr(item, "url", None),
                    "title": getattr(item, "title", None),
                    "content": getattr(item, "content", None),
                    "date": getattr(item, "published_date", None),
                }
            )
        else:
            serializable.append(item)
    return canonical_hash(serializable)


def classify_search_status(raw_status: str | None, hit_count: int) -> str:
    """Map an engine status to the evaluation taxonomy without losing evidence states.

    A response that carries results is never counted as a failure just because a
    secondary provider failed; that conflation made earlier runs under-report
    WebLens reliability.
    """
    status = (raw_status or "unknown").lower()
    if hit_count > 0:
        return "ok" if status == "ok" else "partial"
    if status in ("ok", "partial", "no_reliable_result", "possibly_outdated", "conflicting_sources"):
        return "empty"
    return "error"
