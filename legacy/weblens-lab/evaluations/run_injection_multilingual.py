"""Run the multilingual prompt-injection detection gate.

The corpus contains imperative injection payloads and benign technical prose in
English, Spanish, Chinese, Russian, and Arabic. Detection is the existing
``scan_injection`` heuristic, so this runner measures rule coverage and false
positives, not a trained classifier.

Exit codes:
  0  recall >= threshold and false-positive rate <= max_fpr
  1  gate missed
  2  malformed dataset
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "weblens" / "src"))

from weblens.security.injection import scan_injection  # noqa: E402

DEFAULT_DATASET = ROOT / "weblens-lab" / "datasets" / "injection_multilingual_v1.json"


def _printable(text: str) -> str:
    return text.encode("unicode_escape").decode("ascii")


def _rate(hits: int, total: int) -> float:
    return round(hits / total, 4) if total else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--threshold", type=float, default=0.85)
    parser.add_argument("--max-fpr", type=float, default=0.0)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    try:
        dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
        payloads = list(dataset["payloads"])
        benign = list(dataset["benign"])
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"error": "dataset_error", "detail": str(exc)}))
        return 2
    if not payloads or not benign:
        print(
            json.dumps(
                {
                    "error": "dataset_empty",
                    "payloads": len(payloads),
                    "benign": len(benign),
                }
            )
        )
        return 2

    payload_rows: list[dict[str, Any]] = []
    for item in payloads:
        flags = scan_injection(str(item.get("text", "")))
        payload_rows.append(
            {
                "id": item.get("id"),
                "lang": item.get("lang"),
                "category": item.get("category"),
                "text": item.get("text", ""),
                "flags": flags,
                "hit": bool(flags),
            }
        )

    benign_rows: list[dict[str, Any]] = []
    for item in benign:
        flags = scan_injection(str(item.get("text", "")))
        benign_rows.append(
            {
                "id": item.get("id"),
                "lang": item.get("lang"),
                "text": item.get("text", ""),
                "flags": flags,
                "false_positive": bool(flags),
            }
        )

    hits = sum(1 for row in payload_rows if row["hit"])
    fps = sum(1 for row in benign_rows if row["false_positive"])
    recall = _rate(hits, len(payload_rows))
    fpr = _rate(fps, len(benign_rows))

    by_lang: dict[str, dict[str, int]] = defaultdict(
        lambda: {"payloads": 0, "hits": 0, "benign": 0, "fps": 0}
    )
    for row in payload_rows:
        bucket = by_lang[str(row["lang"])]
        bucket["payloads"] += 1
        bucket["hits"] += int(row["hit"])
    for row in benign_rows:
        bucket = by_lang[str(row["lang"])]
        bucket["benign"] += 1
        bucket["fps"] += int(row["false_positive"])

    by_category: dict[str, dict[str, int]] = defaultdict(
        lambda: {"payloads": 0, "hits": 0}
    )
    for row in payload_rows:
        bucket = by_category[str(row["category"])]
        bucket["payloads"] += 1
        bucket["hits"] += int(row["hit"])

    languages = {
        lang: {
            "payloads": data["payloads"],
            "recall": _rate(data["hits"], data["payloads"]),
            "benign": data["benign"],
            "fpr": _rate(data["fps"], data["benign"]),
        }
        for lang, data in sorted(by_lang.items())
    }
    categories = {
        category: {
            "payloads": data["payloads"],
            "recall": _rate(data["hits"], data["payloads"]),
        }
        for category, data in sorted(by_category.items())
    }

    misses = [row for row in payload_rows if not row["hit"]]
    false_positives = [row for row in benign_rows if row["false_positive"]]
    if args.verbose or misses or false_positives:
        for row in misses:
            print(
                f"MISS {row['id']} [{row['lang']}/{row['category']}] "
                f"{_printable(str(row['text']))}"
            )
        for row in false_positives:
            print(
                f"FP   {row['id']} [{row['lang']}] flags={row['flags']} "
                f"{_printable(str(row['text']))}"
            )

    flag_counts = Counter(flag for row in payload_rows for flag in row["flags"])
    summary = {
        "dataset": dataset.get("name"),
        "payloads": len(payload_rows),
        "benign": len(benign_rows),
        "recall": recall,
        "fpr": fpr,
        "threshold": args.threshold,
        "max_fpr": args.max_fpr,
        "gate": (
            "pass"
            if recall >= args.threshold and fpr <= args.max_fpr
            else "fail"
        ),
        "misses": len(misses),
        "false_positives": len(false_positives),
        "languages": languages,
        "categories": categories,
        "top_flags": dict(flag_counts.most_common(12)),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0 if summary["gate"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
