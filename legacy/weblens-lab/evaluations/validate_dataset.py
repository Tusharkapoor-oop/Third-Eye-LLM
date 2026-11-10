"""Validate the versioned WebLens evaluation inputs without changing them.

The current repository contains a curated 30-query seed, not the requested
100,000-query program.  This validator makes that gap explicit and produces a
machine-readable manifest that can be checked into evidence for each future
dataset version.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from provenance import sha256_file, write_json


REQUIRED_FIELDS = {
    "id",
    "query",
    "category",
    "difficulty",
    "split",
    "ground_truth_answer",
    "acceptable_sources",
    "is_unanswerable",
}

TARGETS = {
    "primary_unique_queries": 100_000,
    "preferred_unique_queries": 250_000,
    "stress_unique_queries": 500_000,
    "document_corpus": 100_000,
    "adversarial_cases": 10_000,
}


def _normalize(text: str) -> str:
    return re.sub(r"\W+", " ", text.casefold(), flags=re.UNICODE).strip()


def _near_duplicate_pairs(items: list[dict[str, Any]], threshold: float = 0.92) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    normalized = [(str(item["id"]), _normalize(str(item["query"]))) for item in items]
    # The seed is intentionally small.  For large versions this function is
    # replaced by an indexed MinHash/LSH pass; it never pretends to be semantic.
    for i, (left_id, left) in enumerate(normalized):
        for right_id, right in normalized[i + 1 :]:
            if left == right:
                continue
            score = SequenceMatcher(None, left, right).ratio()
            if score >= threshold:
                pairs.append({"left_id": left_id, "right_id": right_id, "similarity": round(score, 4)})
    return pairs


def validate_dataset(dataset_path: Path, adversarial_path: Path, version: str) -> dict[str, Any]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    adversarial = json.loads(adversarial_path.read_text(encoding="utf-8"))
    ids = [str(item.get("id", "")) for item in dataset]
    queries = [str(item.get("query", "")) for item in dataset]
    missing = {
        str(item.get("id", f"row-{index}")): sorted(REQUIRED_FIELDS - set(item))
        for index, item in enumerate(dataset)
        if REQUIRED_FIELDS - set(item)
    }
    exact_duplicates = [query for query, count in Counter(_normalize(q) for q in queries).items() if count > 1]
    near_duplicates = _near_duplicate_pairs(dataset)
    categories = Counter(str(item.get("category", "unknown")) for item in dataset)
    splits = Counter(str(item.get("split", "unknown")) for item in dataset)
    synthetic = sum(1 for item in dataset if str(item.get("provenance", "")).casefold() == "synthetic")
    unanswerable = sum(1 for item in dataset if item.get("is_unanswerable") is True)
    unique_count = len(set(_normalize(query) for query in queries if query.strip()))
    schema_ok = not missing and not exact_duplicates and not near_duplicates
    status = "PASS" if schema_ok and unique_count >= TARGETS["primary_unique_queries"] else "PARTIAL"
    return {
        "status": status,
        "dataset_version": version,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "files": {
            "benchmark": {"path": str(dataset_path), "sha256": sha256_file(dataset_path), "records": len(dataset)},
            "adversarial": {"path": str(adversarial_path), "sha256": sha256_file(adversarial_path), "records": len(adversarial)},
        },
        "targets": TARGETS,
        "achieved": {
            "total_records": len(dataset),
            "unique_queries": unique_count,
            "documents": 0,
            "adversarial_cases": len(adversarial),
            "synthetic_records": synthetic,
            "curated_seed_records": len(dataset) - synthetic,
            "unanswerable_records": unanswerable,
        },
        "coverage": {
            "categories": len(categories),
            "category_distribution": dict(sorted(categories.items())),
            "split_distribution": dict(sorted(splits.items())),
            "missing_required_fields": missing,
            "exact_duplicate_normalized_queries": exact_duplicates,
            "near_duplicate_pairs": near_duplicates,
            "schema_status": "PASS" if schema_ok else "FAIL",
            "label_quality": "PARTIAL" if missing else "UNVERIFIED",
        },
        "interpretation": (
            "Curated seed set validated; primary 100,000-query target is not met. "
            "No synthetic expansion is counted as real-world evidence."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--adversarial", type=Path, required=True)
    parser.add_argument("--version", default="v9.0.0-seed")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = validate_dataset(args.dataset, args.adversarial, args.version)
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": str(args.output), "unique_queries": result["achieved"]["unique_queries"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
