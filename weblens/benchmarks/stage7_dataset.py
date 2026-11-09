"""Freeze the Stage 7 Tavily comparison dataset.

The primary evaluation set is deliberately small and hand-labelled:

* ``weblens/benchmarks/queries.jsonl`` -- 58 WebLens regression queries with
  domain labels, answer terms, no-result and conflict expectations.
* ``benchmarks/eval_dataset.json`` -- 50 independent human-written queries with
  ground-truth answers and acceptable source domains.

The 10,000-row synthetic corpus under ``reports/extreme-benchmark`` is *not*
used.  Its file hash matches its card, but its ``required_factual_claims`` are
placeholders and its query text contains generated ``system_component_N``
tokens, so it cannot support honest retrieval-quality labels.

Run from ``weblens/``:

    uv run python benchmarks/stage7_dataset.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WEBLENS_DIR = ROOT / "weblens"
WEBLENS_SOURCE = WEBLENS_DIR / "benchmarks" / "queries.jsonl"
ROOT_SOURCE = ROOT / "benchmarks" / "eval_dataset.json"
OUT_DIR = ROOT / "reports" / "tavily-comparison" / "data"
OUT_DATASET = OUT_DIR / "stage7_dataset.jsonl"
OUT_MANIFEST = OUT_DIR / "stage7_manifest.json"
OUT_CARD = OUT_DIR / "DATASET-CARD.md"

# Deterministic, category-stratified 75/25 split.  The test quota was fixed
# before any query was sent to a provider.  No result was used to choose it.
TEST_QUOTA = {
    "current_facts": 5,
    "docs": 7,
    "niche_technical": 5,
    "unanswerable": 5,
    "conflicting": 5,
}

# Human-written expected-answer terms for the 50 root queries.  The terms are
# the discriminating part of the answer, not the whole sentence, so a result
# snippet can be checked without an LLM judge.
ROOT_ANSWER_TERMS: dict[int, tuple[list[str], str]] = {
    1: (["paris"], "all"),
    2: (["299,792,458", "299792458"], "any"),
    3: (["torvalds"], "all"),
    4: (["gibson"], "all"),
    5: (["quic"], "all"),
    6: (["yen"], "all"),
    7: (["h2o"], "all"),
    8: (["mars"], "all"),
    9: (["pep 703"], "all"),
    10: (["blue whale"], "all"),
    11: (["return_exceptions"], "all"),
    12: (["@>"], "all"),
    13: (["background"], "all"),
    14: (["unwrap_or_else"], "all"),
    15: (["stretch"], "all"),
    16: (["foreign_keys"], "all"),
    17: (["expire"], "all"),
    18: (["git revert", "revert"], "any"),
    19: (["405"], "all"),
    20: (["collections"], "all"),
    21: (["mupdf"], "all"),
    22: (["libxml2"], "all"),
    23: (["512"], "all"),
    24: (["11"], "all"),
    25: (["time_wait"], "all"),
    26: (["rfc 6891", "6891"], "any"),
    27: (["raii"], "all"),
    28: (["epollet"], "all"),
    29: (["2026-07-28"], "all"),
    30: (["extract"], "all"),
}

CATEGORY_MAP = {
    "docs": "docs",
    "documentation_lookups": "docs",
    "current_facts": "current_facts",
    "niche_technical": "niche_technical",
    "unanswerable": "unanswerable",
    "unanswerable_or_fabricated": "unanswerable",
    "conflicting": "conflicting",
    "conflicting_or_debatable": "conflicting",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except Exception:
        return "unknown"


def load_rows() -> list[dict[str, Any]]:
    web_rows = [json.loads(line) for line in WEBLENS_SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    root_rows = json.loads(ROOT_SOURCE.read_text(encoding="utf-8"))
    if len(web_rows) != 58:
        raise SystemExit(f"expected 58 WebLens rows, found {len(web_rows)}")
    if len(root_rows) != 50:
        raise SystemExit(f"expected 50 root rows, found {len(root_rows)}")
    return [*web_rows, *root_rows]


def convert(web_rows: list[dict[str, Any]], root_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    for r in web_rows:
        out.append(
            {
                "id": f"wl-{r['id']}",
                "query": r["query"],
                "category": CATEGORY_MAP[r["category"]],
                "answerable": bool(r["answerable"]),
                "ground_truth_answer": "",
                "answer_terms": list(r.get("answer_terms") or []),
                "support_mode": r.get("support_mode", "all"),
                "relevant_domains": list(r.get("relevant_domains") or []),
                "relevant_url_prefixes": list(r.get("relevant_url_prefixes") or []),
                "expect_research_status": list(r.get("expect_research_status") or ["ok", "partial"]),
                "expect_conflict": r["category"] == "conflicting",
                "expect_abstention": r["category"] == "unanswerable",
                "difficulty": "medium",
                "provenance": "weblens_benchmarks_queries_v1",
            }
        )

    for r in root_rows:
        rid = int(r["id"])
        category = CATEGORY_MAP[r["category"]]
        is_no = bool(r.get("is_unanswerable"))
        is_conflict = bool(r.get("has_conflict"))
        terms, mode = ROOT_ANSWER_TERMS.get(rid, ([], "all"))
        if not is_no and not is_conflict and not terms:
            raise SystemExit(f"answerable root row lacks answer terms: {rid}")
        out.append(
            {
                "id": f"ev-{rid:02d}",
                "query": r["query"],
                "category": category,
                "answerable": not is_no and not is_conflict,
                "ground_truth_answer": r["ground_truth_answer"],
                "answer_terms": terms,
                "support_mode": mode,
                "relevant_domains": list(r.get("acceptable_sources") or []),
                "relevant_url_prefixes": [],
                "expect_research_status": (
                    ["no_reliable_result"]
                    if is_no
                    else (["conflicting_sources", "ok", "partial"] if is_conflict else ["ok", "partial"])
                ),
                "expect_conflict": is_conflict,
                "expect_abstention": is_no,
                "difficulty": r.get("difficulty", "medium"),
                "provenance": "root_eval_dataset_v1",
            }
        )
    return out


def assign_splits(rows: list[dict[str, Any]]) -> None:
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cat[row["category"]].append(row)

    expected = {
        "current_facts": 20,
        "docs": 28,
        "niche_technical": 22,
        "unanswerable": 20,
        "conflicting": 18,
    }
    actual = {k: len(v) for k, v in by_cat.items()}
    if actual != expected:
        raise SystemExit(f"category counts changed: {actual} != {expected}")

    for category, cat_rows in by_cat.items():
        ordered = sorted(
            cat_rows,
            key=lambda r: sha256_bytes(f"stage7|{r['id']}".encode()).encode().hex(),
        )
        quota = TEST_QUOTA[category]
        for i, row in enumerate(ordered):
            row["split"] = "test" if i < quota else "dev"


def validate(rows: list[dict[str, Any]]) -> None:
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate ids in frozen dataset")
    queries = [r["query"].strip().lower() for r in rows]
    if len(queries) != len(set(queries)):
        raise SystemExit("duplicate query text in frozen dataset")
    if any(not r["query"].strip() for r in rows):
        raise SystemExit("empty query in frozen dataset")
    for r in rows:
        if r["category"] == "unanswerable" and not r["expect_abstention"]:
            raise SystemExit(f"unanswerable row lacks abstention flag: {r['id']}")
        if r["category"] == "conflicting" and not r["expect_conflict"]:
            raise SystemExit(f"conflicting row lacks conflict flag: {r['id']}")
        if r["answerable"] and not r["answer_terms"]:
            raise SystemExit(f"answerable row lacks answer terms: {r['id']}")


def write_outputs(rows: list[dict[str, Any]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n"
    OUT_DATASET.write_text(payload, encoding="utf-8", newline="\n")
    digest = sha256_file(OUT_DATASET)

    split_counts = Counter(r["split"] for r in rows)
    category_counts = Counter(r["category"] for r in rows)
    manifest = {
        "dataset_version": "stage7-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "dataset_path": str(OUT_DATASET.relative_to(ROOT)).replace("\\", "/"),
        "dataset_sha256": digest,
        "dataset_bytes": OUT_DATASET.stat().st_size,
        "rows": len(rows),
        "splits": dict(sorted(split_counts.items())),
        "categories": dict(sorted(category_counts.items())),
        "answerable": sum(1 for r in rows if r["answerable"]),
        "unanswerable": sum(1 for r in rows if r["expect_abstention"]),
        "conflicting": sum(1 for r in rows if r["expect_conflict"]),
        "sources": {
            str(WEBLENS_SOURCE.relative_to(ROOT)).replace("\\", "/"): {
                "sha256": sha256_file(WEBLENS_SOURCE),
                "bytes": WEBLENS_SOURCE.stat().st_size,
                "rows": 58,
            },
            str(ROOT_SOURCE.relative_to(ROOT)).replace("\\", "/"): {
                "sha256": sha256_file(ROOT_SOURCE),
                "bytes": ROOT_SOURCE.stat().st_size,
                "rows": 50,
            },
        },
        "split_rule": (
            "Deterministic SHA-256 of 'stage7|<id>' within each normalized "
            "category; fixed per-category test quotas recorded in "
            "weblens/benchmarks/stage7_dataset.py."
        ),
        "test_quota": TEST_QUOTA,
        "excluded": [
            {
                "path": "reports/extreme-benchmark/datasets/extreme_benchmark_10k.jsonl",
                "reason": (
                    "Hash matches its card, but required_factual_claims are "
                    "placeholder strings and query text includes generated "
                    "system_component_N tokens; not valid ground truth."
                ),
            }
        ],
    }
    OUT_MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    card = f"""# Stage 7 frozen dataset card

- Version: `stage7-v1`
- Frozen at: `{manifest["created_at"]}`
- Code commit: `{manifest["git_commit"]}`
- Dataset: `{manifest["dataset_path"]}`
- SHA-256: `{digest}`
- Rows: {len(rows)} ({split_counts["dev"]} dev / {split_counts["test"]} sealed test)
- Categories: {dict(category_counts)}
- Answerable: {manifest["answerable"]}; unanswerable: {manifest["unanswerable"]};
  conflict-labelled: {manifest["conflicting"]}

## Provenance

- 58 rows from `weblens/benchmarks/queries.jsonl` (WebLens regression labels).
- 50 rows from `benchmarks/eval_dataset.json` (independent human-written
  ground-truth answers and acceptable domains).
- No query is present in both sources. Labels were frozen before any Stage 7
  provider request.

## Exclusions

The 10,000-row synthetic corpus at
`reports/extreme-benchmark/datasets/extreme_benchmark_10k.jsonl` is excluded.
Its SHA-256 matches the published card, but all 10,000
`required_factual_claims` values are placeholder strings such as
`Claim-cat01_current_news-0`, and 431 query texts contain generated
`system_component_N` tokens. It cannot support honest quality scoring.

## Limitations

This is 108 English-centric queries, not 500. The categories are broad
(`docs`, `current_facts`, `niche_technical`, `unanswerable`, `conflicting`) and
do not cover multilingual retrieval, adversarial web pages, JavaScript-heavy
pages, or all 30 requested scenarios. Those scenarios are handled by the
separate security/extraction/load tests and are labelled as such; they are not
mixed into the quality denominator. Domain labels are strict and are not
human-judged relevance.
"""
    OUT_CARD.write_text(card, encoding="utf-8", newline="\n")
    print(json.dumps({k: manifest[k] for k in ("rows", "splits", "dataset_sha256")}, indent=2))


def main() -> int:
    if not WEBLENS_SOURCE.exists() or not ROOT_SOURCE.exists():
        raise SystemExit("source dataset is missing")
    web_rows = [json.loads(line) for line in WEBLENS_SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    root_rows = json.loads(ROOT_SOURCE.read_text(encoding="utf-8"))
    rows = convert(web_rows, root_rows)
    assign_splits(rows)
    validate(rows)
    write_outputs(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
