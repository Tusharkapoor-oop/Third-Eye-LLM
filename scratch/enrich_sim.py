"""Simulate richer search snippets by extracting the top candidate pages."""

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


def metrics(item, hits):
    grades = [grade(item, h) for h in hits]
    top = grades[:5]
    binary = [1 if g else 0 for g in top]
    dcg = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(top))
    ideal = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(sorted(top, reverse=True)))
    return grades, {
        "p1": binary[0] if binary else 0.0,
        "p3": sum(binary[:3]) / 3 if binary else 0.0,
        "p5": sum(binary[:5]) / 5 if binary else 0.0,
        "ndcg": dcg / ideal if ideal else 0.0,
        "hit": bool(binary),
    }


async def main() -> None:
    rows = [
        json.loads(line)
        for line in (ROOT / "scratch" / "eval_current_ddg-mwmbl-wikipedia.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    graded = [r for r in rows if not r["item"].get("is_unanswerable") and r["item"].get("acceptable_sources")]
    graded.sort(key=lambda r: (r["score"]["p5"], r["score"]["hit"]))
    target = graded if os.environ.get("ALL") else graded[:18]
    service = WebLens(
        Settings(
            search_providers="ddg,mwmbl,wikipedia",
            cache_enabled=False,
            allow_browser=False,
            provider_timeout_s=3.5,
        )
    )
    sem = asyncio.Semaphore(6)

    async def enrich(item, hit):
        async with sem:
            try:
                out = await asyncio.wait_for(
                    service.extractor.extract(hit["u"], query=item["query"], max_tokens=500),
                    timeout=8,
                )
            except Exception as exc:
                return None, f"{type(exc).__name__}"
            if not out.passages:
                return None, out.status
            best = max(
                out.passages,
                key=lambda p: sum(
                    1 for w in item["query"].lower().split() if w.strip("?.,") in p.text.lower()
                ),
            )
            return best.text, out.status

    total_before = {"p1": 0.0, "p3": 0.0, "p5": 0.0, "ndcg": 0.0, "hit": 0.0}
    total_after = dict(total_before)
    for row in target:
        item, s = row["item"], row["score"]
        hits = [dict(h) for h in s["hits"]]
        before, _ = metrics(item, hits)
        top_n = int(os.environ.get("TOP", "3"))
        enriched = await asyncio.gather(*(enrich(item, h) for h in hits[:top_n]))
        changed = []
        for i, (text, status) in enumerate(enriched):
            if text:
                old = hits[i].get("s") or ""
                hits[i]["s"] = text
                changed.append((i, status, old, text))
        after, m_after = metrics(item, hits)
        _, m_before = metrics(item, s["hits"])
        for key in total_before:
            total_before[key] += m_before[key]
            total_after[key] += m_after[key]
        print("=" * 110)
        print(item["id"], "before", before, "after", after)
        print("Q:", item["query"], "| A:", item["ground_truth_answer"], "| acc:", item["acceptable_sources"])
        for i, status, old, text in changed:
            print(f"  [{i}] {hits[i]['u']} ({status})")
            print(f"      OLD: {old[:180]}")
            print(f"      NEW: {text[:240]}")
    print("=" * 110)
    n = len(target)
    for key in total_before:
        print(f"{key}: {total_before[key] / n:.3f} -> {total_after[key] / n:.3f}")
    await service.close()


if __name__ == "__main__":
    asyncio.run(main())
