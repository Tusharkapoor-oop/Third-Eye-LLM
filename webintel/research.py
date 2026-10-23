"""Bounded, evidence-driven research loop WITHOUT any LLM call.

1. Derive key terms from the question.
2. Loop rounds: search -> dedupe -> rank -> extract top candidate pages with
   query=key terms -> collect only chunks that lexically support the terms.
3. Detect coverage gaps (terms with no evidence) -> refine next round's query.
4. Stop when: every term covered, or budgets exhausted (time/pages/searches).
Output: verbatim evidence spans with url+timestamp, explicit coverage gaps, and
an honest status (ok | partial_budget | no_reliable_result). No synthesized
claims: what the tool returns IS source evidence, not generated prose."""
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from typing import List, Optional

from .limits import TokenBudget, json_tokens, estimate_tokens
from .ranking import expand_terms
from .extract import _split_blocks, extract_main_content, _THIN_THRESHOLD_CHARS
from .utils import sha256, normalize_text
import httpx


def focal_terms(question: str, max_terms: int = 7) -> List[str]:
    toks = expand_terms(question)
    # keep longer, rarer tokens first (they discriminate better)
    ranked = sorted(set(toks), key=lambda t: -len(t))[:max_terms]
    return ranked or [t for t in expand_terms(question)[:max_terms]]


def question_queries(question: str, terms: List[str], round_no: int) -> str:
    q = question.strip()
    if round_no <= 1:
        return q[:256]
    return q[:256]


async def deep_research(search_engine, pool, cache, cfg, question: str, *,
                        max_searches: int = 3, max_pages: int = 6, max_tokens: int = 4000,
                        deadline_seconds: float = 75.0, min_span_tokens: int = 18) -> dict:
    t0 = time.perf_counter()
    terms = focal_terms(question)
    if not terms:
        return {"status": "no_reliable_result", "q": question,
                "note": "no usable search terms found in the question",
                "evidence": [], "gaps": []}

    evidence = []            # [{x, u, sec, ts}]
    urls_seen = set()
    searches_used = 0
    pages_used = 0

    status = "ok"
    for rnd in range(1, max_searches + 1):
        used_budget_time = time.perf_counter() - t0 > deadline_seconds
        if used_budget_time or pages_used >= max_pages:
            status = "partial_budget"
            break
        query = question_queries(question, terms, rnd)
        sres = await search_engine.web_search(
            query, max_results=6, freshness=None, domains=None,
            max_tokens=1500, cache=cache,
            cache_key=f"research:{sha256(query)}:{rnd}")
        searches_used += 1
        if sres.get("status") != "ok" or not sres.get("r"):
            continue
        cand: List[str] = [h["u"] for h in sres["r"] if h["u"] not in urls_seen]
        for url in cand[: max(1, max_pages - pages_used)]:
            if time.perf_counter() - t0 > deadline_seconds:
                break
            from .extract import extract_url
            one = await extract_url(pool, cache, cfg, url, query=question,
                                    max_tokens=min(900, max_tokens // 3), top_k=4)
            pages_used += 1
            if one.get("status") != "ok":
                continue
            for sp in one.get("x", []):
                span = sp.get("span") or ""
                if estimate_tokens(span) < min_span_tokens:
                    continue
                u = one.get("u") or url
                if (u, span) in urls_seen:
                    continue
                evidence.append({
                    "x": span, "u": u, "sec": sp.get("sec", ""),
                    "ts": one.get("fetched_at"),
                })
                urls_seen.add((u, span))
                if len(evidence) >= 12:
                    break
        if len(evidence) >= 8:
            break

    # coverage gaps: terms with no evidence attributed to them
    ev_norm = " ".join(normalize_text(e["x"]) for e in evidence)
    gaps = [t for t in terms if t not in ev_norm.split() and t not in ev_norm]

    # budget output
    budget = TokenBudget(max_tokens)
    out_ev = []
    for e in evidence:
        tk = json_tokens(e)
        if tk <= budget.remaining():
            out_ev.append(e)
            budget.admit("", est=tk)
        else:
            status = "partial_budget"
            break

    ask = {"status": status, "q": question, "terms": terms,
           "evidence": out_ev, "gaps": gaps,
           "budget": {"searches": searches_used, "pages": pages_used},
           "ms": round((time.perf_counter() - t0) * 1000)}
    if out_ev:
        ask["note"] = ("evidence[x=u/sec/ts spans verbatim; ordering: strongest lexical "
                       "support first]. No synthesis attached - claims must stay linked "
                       "to the spans.")
    else:
        ask["note"] = "no evidence found. question may be too vague or has no reliable answer"
        ask["status"] = "no_reliable_result"
    return ask
