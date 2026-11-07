"""Quick local-only V10 diagnostic (not a published benchmark artifact)."""

from __future__ import annotations

import asyncio
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "weblens" / "src"))

from weblens.config import Settings
from weblens.service import WebLens
from weblens.urls import registrable_domain

if os.environ.get("MODE") == "off":
    import weblens.search.router as router_module

    router_module.official_source_urls = lambda query: []


def grade(item, hit: dict) -> int:
    url = str(hit.get("u") or "").lower()
    text = " ".join([str(hit.get("t") or ""), str(hit.get("s") or "")]).lower()
    host = registrable_domain(url)
    acceptable = item.get("acceptable_sources") or []
    if acceptable and any(acc.lower().lstrip("www.") in (host + url) for acc in acceptable):
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


def score(item, res):
    hits = res.get("res") or []
    grades = [grade(item, h) for h in hits]
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
        "n": len(hits),
        "status": res.get("status"),
        "warn": res.get("warn") or [],
        "fail": res.get("fail") or {},
        "urls": [h.get("u") for h in hits],
        "hits": hits,
    }


async def main() -> None:
    items = json.loads(
        (ROOT / "weblens-lab/datasets/eval_benchmark_suite_v10.json").read_text(encoding="utf-8")
    )
    split = os.environ.get("SPLIT", "development")
    if split != "all":
        items = [i for i in items if i.get("split") == split]
    settings = Settings(
        search_providers=os.environ.get("PROVIDERS", "ddg,mwmbl,wikipedia"),
        search_mode="fuse",
        cache_enabled=False,
        allow_browser=False,
        provider_timeout_s=3.5,
        max_search_tokens=900,
        search_enrich_top=0 if os.environ.get("MODE") in {"off", "hints"} else 3,
    )
    service = WebLens(settings)
    sem = asyncio.Semaphore(4)

    async def one(item):
        async with sem:
            try:
                res = await service.search(item["query"], max_results=5, max_tokens=900)
            except Exception as exc:
                res = {"status": "error", "err": type(exc).__name__, "res": []}
            return item, score(item, res)

    results = await asyncio.gather(*(one(i) for i in items))
    stem = (
        f"{os.environ.get('PROVIDERS', 'default').replace(',', '-')}-"
        f"{os.environ.get('MODE', 'on')}-{split}"
    )
    dump = ROOT / "scratch" / f"eval_current_{stem}.jsonl"
    with dump.open("w", encoding="utf-8") as fh:
        for item, s in results:
            fh.write(json.dumps({"item": item, "score": s}, ensure_ascii=False) + "\n")
    print(f"wrote={dump}")
    by_cat = {}
    for item, s in results:
        by_cat.setdefault(item["category"], []).append(s)
    print(f"items={len(results)} graded={sum(1 for i, s in results if not i.get('is_unanswerable'))}")
    for key in ("p1", "p3", "p5", "mrr", "ndcg", "hit"):
        vals = [s[key] for i, s in results if not i.get("is_unanswerable")]
        print(f"{key}={sum(vals) / len(vals):.3f}")
    print("statuses=", {k: sum(1 for _, s in results if s["status"] == k) for k in {s["status"] for _, s in results}})
    print("\nCATEGORY P5")
    for cat, vals in sorted(by_cat.items(), key=lambda kv: sum(v["p5"] for v in kv[1]) / len(kv[1])):
        print(f"{cat:28} {sum(v['p5'] for v in vals) / len(vals):.3f} n={len(vals)}")
    print("\nBOTTOM QUERIES")
    for item, s in sorted(results, key=lambda x: (x[1]["p5"], x[1]["hit"]))[:30]:
        print(
            f"{item['id']:32} p5={s['p5']:.2f} n={s['n']} status={s['status']} "
            f"grades={s['grades']} warn={s['warn'][:3]} fail={s['fail']}"
        )
        print(f"  {item['query']}")
        for u in s["urls"][:5]:
            print(f"    {u}")
    await service.close()


if __name__ == "__main__":
    asyncio.run(main())
