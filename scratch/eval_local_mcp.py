"""Local-MCP V10 search diagnostic (not a published three-system artifact)."""

from __future__ import annotations

import asyncio
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "weblens" / "src"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "weblens-lab"))

from adapters.local_mcp_adapter.adapter import LocalMCPAdapter  # noqa: E402
from weblens.urls import registrable_domain  # noqa: E402


def grade(item: dict, url: str, title: str, content: str) -> int:
    low_url = (url or "").lower()
    host = registrable_domain(low_url)
    text = " ".join([title or "", content or ""]).lower()
    acceptable = item.get("acceptable_sources") or []
    if acceptable and any(acc.lower().lstrip("www.") in (host + low_url) for acc in acceptable):
        return 2
    keywords = [
        k.lower()
        for k in str(item.get("ground_truth_answer", "")).replace(",", " ").split()
        if len(k) > 2
    ]
    if keywords:
        covered = sum(1 for k in keywords if k in text)
        if covered / len(keywords) >= 0.6:
            return 1
    return 0


def metrics(item: dict, result) -> dict:
    grades = [grade(item, r.url, r.title, r.content) for r in result.results]
    top = grades[:5]
    binary = [1 if g else 0 for g in top]
    first = next((i + 1 for i, g in enumerate(grades) if g), None)
    dcg = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(top))
    ideal = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(sorted(top, reverse=True)))
    return {
        "grades": grades,
        "p1": binary[0] if binary else 0.0,
        "p3": sum(binary[:3]) / 3 if binary else 0.0,
        "p5": sum(binary[:5]) / 5 if binary else 0.0,
        "mrr": 1 / first if first else 0.0,
        "ndcg": dcg / ideal if ideal else 0.0,
        "hit": bool(binary),
        "status": result.status,
        "raw_status": result.raw_status,
        "urls": [r.url for r in result.results],
    }


async def main() -> None:
    items = json.loads(
        (ROOT / "weblens-lab/datasets/eval_benchmark_suite_v10.json").read_text(encoding="utf-8")
    )
    split = os.environ.get("SPLIT", "all")
    if split != "all":
        items = [i for i in items if i.get("split") == split]
    limit = int(os.environ.get("LIMIT", "0"))
    if limit:
        items = items[:limit]

    adapter = LocalMCPAdapter()
    await adapter.start()
    rows = []
    try:
        for idx, item in enumerate(items, 1):
            result = await adapter.search(item["query"], max_results=5)
            rows.append({"id": item["id"], "category": item["category"], "score": metrics(item, result)})
            if idx % 20 == 0:
                print(f"progress={idx}/{len(items)}", flush=True)
    finally:
        await adapter.close()

    dump = ROOT / "scratch" / f"eval_local_mcp_{split}.jsonl"
    with dump.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    graded = [row["score"] for row in rows if not next(i for i in items if i["id"] == row["id"]).get("is_unanswerable")]
    print(f"wrote={dump}")
    print(f"items={len(rows)} graded={len(graded)}")
    for key in ("p1", "p3", "p5", "mrr", "ndcg", "hit"):
        print(f"{key}={sum(r[key] for r in graded) / len(graded):.3f}")
    print("statuses=", {s: sum(1 for r in rows if r["score"]["status"] == s) for s in {r["score"]["status"] for r in rows}})


asyncio.run(main())
