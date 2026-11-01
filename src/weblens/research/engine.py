"""Deterministic, evidence-first research loop.

No LLM is called. Every finding is a verbatim sentence from a fetched page with
its URL, fetch timestamp and exact character span. Missing evidence is reported
as gaps instead of filled with a guess.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field

from ..config import Settings
from ..extract.passages import Passage, query_terms, select_passages, tokenize
from ..extract.service import ExtractionService
from ..search.router import SearchRouter, clean_query
from ..tokens import count_json_tokens
from ..urls import registrable_domain

FRESH = ("latest", "current", "today", "now", "2026", "2025", "price", "release", "news", "recent")
GAP_IGNORE = {
    "python", "javascript", "typescript", "java", "go", "golang", "rust", "csharp",
    "php", "ruby", "linux", "windows", "macos", "android", "ios", "web",
}
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9`#*])")
NUM = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>ms|milliseconds?|s|sec|seconds?|kb|mb|gb|tb|%|"
    r"usd|dollars?|€|£|\$)",
    re.IGNORECASE,
)
UNIT_NORM = {
    "ms": "ms", "millisecond": "ms", "milliseconds": "ms",
    "s": "s", "sec": "s", "second": "s", "seconds": "s",
    "kb": "kb", "mb": "mb", "gb": "gb", "tb": "tb",
    "%": "%", "usd": "usd", "dollar": "usd", "dollars": "usd",
    "€": "eur", "£": "gbp", "$": "usd",
}


@dataclass
class Finding:
    claim: str
    url: str
    fetched_at: str
    span: list[int]
    heading: str | None = None
    injection: list[str] | None = None
    published: str | None = None


@dataclass
class ResearchOutcome:
    status: str
    query: str
    findings: list[Finding]
    gaps: list[str]
    searched: list[str]
    elapsed_ms: int
    tokens: int
    warnings: list[str] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    cut: bool = False
    budget: int = 2000


def decompose(query: str) -> list[str]:
    q = clean_query(query)
    out = [q]
    low = q.lower()
    if not any(w in low for w in ("tutorial", "documentation", "docs", "example", "guide")):
        if low.startswith(("how ", "what ", "why ", "can ", "does ")):
            out.append(q + " documentation")
    if " vs " in low or " versus " in low or "compare" in low:
        out.append(q + " comparison")
    if any(w in low for w in ("how", "example", "code")):
        out.append(q + " example")
    seen: list[str] = []
    for x in out:
        if x not in seen:
            seen.append(x)
    return seen[:4]


def sentence_candidates(passage: Passage, query: str, limit: int = 2) -> list[Finding]:
    terms, phrases = query_terms(query)
    text = passage.text
    spans: list[tuple[int, int]] = []
    pos = 0
    for m in SENT_SPLIT.finditer(text):
        spans.append((pos, m.start()))
        pos = m.end()
    if pos < len(text):
        spans.append((pos, len(text)))
    scored: list[tuple[float, int, int]] = []
    for a, b in spans:
        raw = text[a:b]
        # Drop leading markdown headings so evidence starts at the sentence,
        # not at a section title or site chrome.
        mhead = re.match(r"\s*(?:#{1,6}[^\n]*\n)+\s*", raw)
        if mhead:
            a += mhead.end()
            raw = text[a:b]
        claim = raw.strip()
        if len(claim) < 30 or len(claim) > 700:
            continue
        low = claim.lower()
        if low.startswith(("```", "copy path", "more file actions", "skip to", "sign in", "advertisement")):
            continue
        if "copy path" in low[:80]:
            continue
        toks = set(tokenize(claim))
        hits = sum(1 for t in terms if t in toks)
        if terms and hits == 0:
            continue
        score = hits / max(1, len(terms))
        if any(p in low for p in phrases):
            score += 0.5
        if re.search(r"\b\d", claim):
            score += 0.15
        if claim.endswith(":"):
            score -= 0.2
        # Prefer compact statements over long legal/boilerplate paragraphs.
        score -= min(0.25, len(claim) / 3000)
        if re.search(r"(?<!^)\b[A-Z][a-z]{2,}\b", claim):
            score += 0.05
        qlow = query.lower()
        if qlow.startswith(("what is", "what are", "who is", "define", "meaning")):
            if re.search(
                r"\b(?:is|are|refers? to|means|defined as|stands for|returns?|provides?|creates?|allows?|used to)\b",
                claim,
                re.IGNORECASE,
            ):
                score += 0.3
            if re.search(r"(?:async def|>>>|```|\{\s*$)", claim):
                score -= 0.25
        if "license" in terms and re.search(
            r"\b(?:Apache|MIT|GPLv?\d?|BSD|MPL|Unlicense|CC[- ]BY)\b", claim
        ):
            score += 0.8
        lead = len(raw) - len(raw.lstrip())
        start = passage.start + a + lead
        end = start + len(claim)
        scored.append((score, start, end))

    # License names often span newlines in extracted legal pages, so they are
    # not single sentences. Emit one exact-span candidate when the query asks
    # for a license.
    if "license" in terms:
        pattern = re.compile(
            r"\b(?:Apache|MIT|GPLv?\d?|BSD|MPL|Unlicense|CC[- ]BY)\b"
            r"[\s\S]{0,50}?(?:\bLicense\b|\bVersion\b)[\s\S]{0,30}?\d+(?:\.\d+)?"
            r"(?:\s*,\s*\d{4})?",
            re.IGNORECASE,
        )
        for m in pattern.finditer(text):
            raw = text[m.start() : m.end()]
            claim = raw.strip()
            if len(claim) < 10 or len(claim) > 120:
                continue
            lead = len(raw) - len(raw.lstrip())
            start = passage.start + m.start() + lead
            scored.append((2.0, start, start + len(claim)))
    scored.sort(key=lambda t: (-t[0], t[1]))
    out: list[Finding] = []
    for _, start, end in scored[:limit]:
        claim = text[start - passage.start : end - passage.start]
        if claim and claim == claim.strip():
            out.append(
                Finding(
                    claim=claim,
                    url="",  # filled by caller
                    fetched_at="",
                    span=[start, end],
                    heading=passage.heading,
                    injection=passage.injection,
                )
            )
    return out


def detect_conflicts(findings: list[Finding], query: str) -> list[dict]:
    """Conservative numeric contradiction check (same subject + unit, different value)."""
    qlow = query.lower()
    relevant = any(
        w in qlow
        for w in (
            "price",
            "cost",
            "much",
            "many",
            "fast",
            "latency",
            "time",
            "size",
            "memory",
            "percent",
            "%",
        )
    )
    if not relevant:
        return []
    claims: list[dict] = []
    for f in findings:
        for m in NUM.finditer(f.claim):
            unit = UNIT_NORM.get(m.group("unit").lower(), m.group("unit").lower())
            try:
                value = float(m.group("num").replace(",", ""))
            except ValueError:
                continue
            before = f.claim[max(0, m.start() - 120) : m.start()]
            subject = {
                t for t in tokenize(before)[-8:]
                if len(t) > 2 and t not in {"the", "and", "with", "for", "from", "that", "this"}
            }
            mult = 1.0
            if unit == "s":
                mult = 1000.0
            elif unit == "usd":
                mult = 1.0
            claims.append(
                {
                    "unit": unit,
                    "value": value * mult,
                    "subject": subject,
                    "finding": f,
                    "raw": m.group(0),
                }
            )
    conflicts: list[dict] = []
    for i in range(len(claims)):
        for j in range(i + 1, len(claims)):
            a, b = claims[i], claims[j]
            if a["unit"] != b["unit"]:
                continue
            if registrable_domain(a["finding"].url.split("/")[2]) == registrable_domain(b["finding"].url.split("/")[2]):
                continue
            sa, sb = a["subject"], b["subject"]
            if not sa or not sb:
                continue
            overlap = len(sa & sb) / max(1, len(sa | sb))
            if overlap < 0.5:
                continue
            va, vb = a["value"], b["value"]
            if va == vb:
                continue
            if max(va, vb) == 0 or abs(va - vb) / max(va, vb) < 0.05:
                continue
            conflicts.append(
                {
                    "unit": a["unit"],
                    "a": {"v": a["raw"], "c": a["finding"].claim, "u": a["finding"].url, "s": a["finding"].span},
                    "b": {"v": b["raw"], "c": b["finding"].claim, "u": b["finding"].url, "s": b["finding"].span},
                    "warn": "heuristic_numeric_conflict",
                }
            )
            if len(conflicts) >= 3:
                return conflicts
    return conflicts


class ResearchEngine:
    def __init__(self, settings: Settings, router: SearchRouter, extractor: ExtractionService):
        self.s = settings
        self.router = router
        self.extractor = extractor

    async def research(
        self,
        query: str,
        *,
        max_tokens: int | None = None,
        max_searches: int = 4,
        max_pages: int = 6,
    ) -> ResearchOutcome:
        started = time.perf_counter()
        budget = max(300, min(8000, max_tokens or self.s.max_research_tokens))
        q = clean_query(query)
        score_q = query.strip() or q
        queries = decompose(q)[: max(1, min(6, max_searches))]
        warnings: list[str] = []
        outcome = ResearchOutcome(
            status="ok",
            query=q,
            findings=[],
            gaps=[],
            searched=queries,
            elapsed_ms=0,
            tokens=0,
            budget=budget,
        )
        if not q:
            outcome.status = "no_reliable_result"
            outcome.gaps.append("empty_query")
            return outcome

        async def one(qq: str):
            try:
                return await self.router.search(
                    qq,
                    k=5,
                    freshness="month" if any(w in q.lower() for w in FRESH) else None,
                )
            except Exception as e:
                return e

        results = await asyncio.gather(*(one(x) for x in queries))
        hit_scores: dict[str, float] = {}
        hit_map = {}
        for r in results:
            if isinstance(r, Exception):
                warnings.append(f"search_failed:{type(r).__name__}")
                continue
            for pos, h in enumerate(r.hits):
                hit_scores[h.url] = hit_scores.get(h.url, 0.0) + 1.0 / (1.0 + pos)
                hit_map[h.url] = h
        if not hit_map:
            outcome.status = "no_reliable_result"
            outcome.gaps.append("no_search_results")
            outcome.warnings = warnings
            return self._finish(outcome, started, budget)

        ranked = sorted(hit_map.values(), key=lambda h: (-hit_scores.get(h.url, 0.0), h.url))
        targets = ranked[: max(1, min(12, max_pages))]
        sem = asyncio.Semaphore(4)

        async def fetch_one(hit):
            async with sem:
                try:
                    doc = await self.extractor.fetch_doc(hit.url, allow_browser=False)
                    return hit, doc
                except Exception as e:
                    return hit, e

        fetched = await asyncio.gather(*(fetch_one(h) for h in targets))
        findings: list[Finding] = []
        seen_claims: set[str] = set()
        used_urls: set[str] = set()
        stale_dates: list[str] = []
        for hit, doc in fetched:
            if isinstance(doc, Exception):
                warnings.append(f"fetch_failed:{type(doc).__name__}")
                continue
            passages, cov = select_passages(doc.text, score_q, title=doc.title, max_passages=3, max_chars=5000)
            if cov == 0:
                warnings.append(f"no_query_match:{registrable_domain(hit.url.split('/')[2])}")
                continue
            used_urls.add(hit.url)
            for p in passages:
                for f in sentence_candidates(p, score_q, limit=1):
                    norm = re.sub(r"\W+", " ", f.claim.lower()).strip()
                    if norm[:120] in seen_claims:
                        continue
                    seen_claims.add(norm[:120])
                    f.url = doc.final_url or hit.url
                    f.fetched_at = doc.fetched_at
                    f.published = doc.date_iso()
                    findings.append(f)
                    if f.published:
                        stale_dates.append(f.published)

        # Rank findings by query-term coverage, then source diversity.
        terms, _ = query_terms(q)
        def fscore(f: Finding) -> float:
            toks = set(tokenize(f.claim))
            cov = sum(1 for t in terms if t in toks) / max(1, len(terms))
            return cov + (0.05 if f.published else 0)

        findings.sort(key=lambda f: (-fscore(f), f.url, f.span[0]))
        # Prefer at most two claims per domain in the short list.
        per_domain: dict[str, int] = {}
        kept: list[Finding] = []
        for f in findings:
            d = registrable_domain(f.url.split("/")[2])
            if per_domain.get(d, 0) >= 3:
                continue
            per_domain[d] = per_domain.get(d, 0) + 1
            kept.append(f)
            if len(kept) >= 8:
                break
        outcome.findings = kept

        # Budget findings.
        while outcome.findings:
            if count_json_tokens(self.payload(outcome, final=False)) <= budget:
                break
            outcome.findings.pop()
            outcome.cut = True

        # Gaps: query terms with no supporting finding.
        supported = set()
        for f in outcome.findings:
            supported |= set(tokenize(f.claim))
        missing = [t for t in terms if t not in supported and t not in GAP_IGNORE]
        outcome.gaps = [f"no_source_for:{t}" for t in missing[:6]]

        # Freshness / conflicts.
        if any(w in q.lower() for w in FRESH):
            if stale_dates:
                from datetime import date

                from ..search.base import parse_date

                ages = [(date.today() - d).days for d in (parse_date(x) for x in stale_dates) if d]
                if ages and min(ages) > 365:
                    outcome.status = "possibly_outdated"
                    outcome.warnings.append("all_sources_older_than_1y")
            else:
                outcome.warnings.append("dates_unknown")
        outcome.conflicts = detect_conflicts(outcome.findings, q)
        if outcome.conflicts:
            outcome.status = "conflicting_sources"
        elif not outcome.findings:
            outcome.status = "no_reliable_result"
            outcome.gaps.append("no_supported_claim")
        elif outcome.gaps:
            outcome.status = "partial"
        if warnings:
            outcome.warnings.extend(warnings)
            outcome.warnings = list(dict.fromkeys(outcome.warnings))
        return self._finish(outcome, started, budget)

    def _body(self, out: ResearchOutcome, findings: list[Finding]) -> dict:
        items = [
            {
                "c": f.claim,
                "u": f.url,
                "at": f.fetched_at,
                "s": f.span,
                **({"h": f.heading} if f.heading else {}),
                **({"d": f.published} if f.published else {}),
                **({"inj": f.injection} if f.injection else {}),
            }
            for f in findings
        ]
        body: dict[str, object] = {
            "status": out.status,
            "q": out.query,
            "n": len(items),
            "f": items,
            "gaps": out.gaps,
            "searched": out.searched,
            "tok": 0,
        }
        if out.conflicts:
            body["conflicts"] = out.conflicts
        if out.cut:
            body["cut"] = True
        if out.warnings:
            body["warn"] = out.warnings
        return body

    def payload(self, out: ResearchOutcome, *, final: bool = True) -> dict:
        if not final:
            return self._body(out, out.findings)
        budget = max(200, out.budget)
        target = max(120, budget - 6)
        findings = list(out.findings)
        for _ in range(80):
            body = self._body(out, findings)
            body["ms"] = out.elapsed_ms
            body["tok"] = 0
            if count_json_tokens(body) <= target:
                break
            if not findings:
                break
            findings.pop()
            out.cut = True
        body = self._body(out, findings)
        body["ms"] = out.elapsed_ms
        if out.cut:
            body["cut"] = True
        if not findings and out.findings:
            if out.status == "ok":
                out.status = "partial"
            body["status"] = out.status
            body["warn"] = list(
                dict.fromkeys([*(body.get("warn") or []), "budget_exhausted"])
            )
        body["tok"] = count_json_tokens({**body, "tok": 0})
        if count_json_tokens(body) > budget:
            body["warn"] = list(
                dict.fromkeys([*(body.get("warn") or []), "budget_exhausted"])
            )
            body["tok"] = count_json_tokens({**body, "tok": 0})
        out.findings = findings
        out.tokens = body["tok"]  # type: ignore[assignment]
        return body

    def _finish(self, out: ResearchOutcome, started: float, budget: int) -> ResearchOutcome:
        out.elapsed_ms = int((time.perf_counter() - started) * 1000)
        body = self.payload(out)
        out.tokens = body["tok"]  # type: ignore[assignment]
        return out
