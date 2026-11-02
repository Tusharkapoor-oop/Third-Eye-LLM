"""Evidence primitives shared by the three-system evaluation runners.

This module deliberately keeps evidence metadata separate from provider payloads.
Provider output is untrusted data; the lab owns the experiment identity, timing,
and hash fields.  Secrets are never accepted as part of the evidence record.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

EvidenceStatus = Literal[
    "PASS",
    "FAIL",
    "PARTIAL",
    "BLOCKED",
    "NOT RUN",
    "UNSUPPORTED",
    "UNVERIFIED",
    "REJECTED",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_json(value: Any) -> str:
    """Hash canonical JSON without persisting provider credentials."""

    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def result_provenance(
    *,
    system: Literal["local_weblens", "deployed_weblens", "tavily_direct"],
    backend_provider: str | None,
    model: str | None,
    cache_state: Literal["cold", "warm", "unknown"],
    experiment_id: str,
    dataset_version: str,
    success: bool,
    latency_ms: float,
    response: Any,
    status: EvidenceStatus,
    error: str | None = None,
) -> dict[str, Any]:
    """Build the required provenance envelope for one provider result."""

    record: dict[str, Any] = {
        "system": system,
        "backend_provider": backend_provider,
        "model": model,
        "cache_state": cache_state,
        "experiment_id": experiment_id,
        "dataset_version": dataset_version,
        "timestamp": utc_now(),
        "success": success,
        "latency_ms": round(max(0.0, latency_ms), 3),
        "response_hash": sha256_json(response),
        "status": status,
    }
    if error:
        record["error"] = error[:500]
    return record


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def redact_error(error: BaseException | str | None) -> str | None:
    """Return a short error suitable for evidence logs.

    The caller must still avoid putting secrets in exception messages.  This
    function only limits size and removes common bearer/key-shaped values.
    """

    if error is None:
        return None
    text = str(error)[:500]
    for marker in ("tvly-", "sk-", "Bearer "):
        start = text.find(marker)
        if start >= 0:
            end = start + len(marker)
            while end < len(text) and text[end] not in " ,;)'\"\\n":
                end += 1
            text = text[:start] + marker + "<redacted>" + text[end:]
    return text
