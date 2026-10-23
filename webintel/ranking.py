"""Transparent ranking signals, shared by search and extract.

PRINCIPLE (R2): all numeric signal values here are INTERNAL ONLY. They shape
ordering but are never returned to callers, because none of them have been
calibrated against a labelled evaluation set. Returned objects carry no
score/confidence/relevance fields - a startup scan in bench/gates.py enforces it.
"""
from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Dict, List, Sequence

from .utils import normalize_text, query_tokens

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .search.base import SearchHit

# Multi-label TLD suffixes that need 3 labels for "registrable domain"
MULTI_LABEL_SUFFIXES = {"co.uk", "org.uk", "gov.uk", "ac.uk", "com.au", "co.jp", "co.in",
                        "com.br", "co.za", "com.tr", "edu.cn", "com.cn", "com.mx"}


def registrable_domain(host: str) -> str:
    h = host.strip("[]").lower()
    labels = h.split(".")
    if len(labels) < 2:
        return h
    tail2 = ".".join(labels[-2:])
    if tail2 in MULTI_LABEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return tail2


DOMAIN_CREDIBILITY: Dict[str, float] = {
    # small hand-curated prior; absence = neutral. Shapes ordering only.
    "docs.python.org": 1.0, "python.org": 0.7, "learn.microsoft.com": 1.0,
    "developer.mozilla.org": 1.0, "docs.rs": 1.0, "rust-lang.org": 0.8, "go.dev": 0.9,
    "github.com": 0.4, "stackoverflow.com": 0.2, "arxiv.org": 0.8, "pubmed.ncbi.nlm.nih.gov": 1.0,
    "nature.com": 0.6, "wikipedia.org": 0.4, "pypi.org": 0.8, "npmjs.com": 0.5,
    "fastapi.tiangolo.com": 0.9, "docs.djangoproject.com": 0.9, "nextjs.org": 0.9,
    "react.dev": 0.9, "vite.dev": 0.9, "developers.google.com": 0.8, "cloudflare.com": 0.6,
    "openai.com": 0.6, "modelcontextprotocol.io": 1.0,
}


TERM_DOT = re.compile(r"[./]+")
TERM_W = re.compile(r"[a-z]{3,}")


def expand_terms(q: str) -> list[str]:
    """Query tokens + pragmatic subterms:
    'path.read_text' -> {'path','read_text','read','text'}"""
    raw = query_tokens(q)
    out: set[str] = set()
    for t in raw:
        if t:
            out.add(t)
    for t in tuple(out):
        for part in TERM_DOT.split(t):
            if len(part) >= 3:
                out.add(part)
                if "_" in part and len(part) >= 5:
                    pieces = [pf for pf in part.split("_") if len(pf) >= 3]
                    out.add(part)          # whole compound matches page's snake_case
                    out.update(pieces)     # word parts catch escaped/display variants
    res = [t for t in out if t]
    return res


def title_overlap(query: str, title: str) -> float:
    q = expand_terms(query)
    if not q:
        return 0.0
    t = normalize_text(title)
    return sum(1 for tok in q if tok in t) / len(q)


def snippet_overlap(query: str, snippet: str) -> float:
    q = expand_terms(query)
    if not q:
        return 0.0
    s = normalize_text(snippet)
    return sum(1 for tok in q if tok in s) / len(q)


def rank_search_hits(hits: Sequence["SearchHit"], query: str) -> List["SearchHit"]:
    """Baseline: provider SERP rank (strongest prior), title/snippet term coverage,
     small credibility prior; then cap 2 results per registrable domain."""
    scored = []
    for h in hits:
        host = h.url.split("/")[2] if "://" in h.url else ""
        rd = registrable_domain(host)
        cred = DOMAIN_CREDIBILITY.get(rd, 0.0)
        s = (3.0 - min(h.provider_rank, 12) * 0.25) + 2.0 * title_overlap(query, h.title) \
            + 0.8 * snippet_overlap(query, h.snippet) + 0.6 * cred
        scored.append((s, h))
    scored.sort(key=lambda x: -x[0])
    per_rd: Dict[str, int] = {}
    final = []
    for _, h in scored:
        rd = registrable_domain(h.url.split("/")[2]) if "://" in h.url else "?"
        if per_rd.get(rd, 0) >= 2:
            continue
        per_rd[rd] = per_rd.get(rd, 0) + 1
        final.append(h)
    return final


# ---------------------------------------------------------------- chunk scoring
_WORD = re.compile(r"[a-z0-9]{2,}", re.I)


def _tfidflite(blocks: Sequence[str], query_terms: Sequence[str]) -> List[float]:
    """Idf computed within the page's own block distribution (self-contained).
    Compound query terms ('read_text') also match their word parts ('read','text')."""
    n_blocks = max(1, len(blocks))
    df: Counter = Counter()
    term_sets = []
    for b in blocks:
        toks = set(t.lower() for t in _WORD.findall(b) if t)
        term_sets.append(toks)
        for t in toks:
            df[t] += 1
    parts_map: dict[str, tuple[str, ...]] = {}
    for qt in query_terms:
        parts = tuple(p for p in re.split(r"[_]+", qt) if len(p) >= 3) if "_" in qt else (qt,)
        parts_map[qt] = parts or (qt,)
    scores = []
    for toks in term_sets:
        s = 0.0
        for qt, parts in parts_map.items():
            hit = qt in toks or any(p in toks for p in parts)
            if hit:
                dfkey = qt if qt in df else parts[0]
                s += 1.0 * (1.0 + (n_blocks / (1 + df[dfkey])) * 0.05)
        scores.append(s)
    return scores


def score_chunks(blocks: List[str], query: str, headings: List[str]) -> List[float]:
    """Chunk relevance for extract_url(query=...). Transparent lexicon signal:
    idf-weighted term hits + heading-term overlap. No model, no LLM call."""
    q = expand_terms(query)
    if not q:
        return [0.0] * len(blocks)
    base = _tfidflite(blocks, q)
    hd_toks = [normalize_text(x) for x in headings if x]
    out = []
    for bi, b in enumerate(blocks):
        bt = normalize_text(b)
        heading_bonus = sum(1 for qtk in q for h in hd_toks if qtk in h) * 0.05
        out.append(base[bi] + heading_bonus)
    return out


def near_duplicate_text(a: str, b: str, thresh: float = 0.9) -> bool:
    an, bn = normalize_text(a)[:400], normalize_text(b)[:400]
    if not an or not bn:
        return False
    if an == bn:
        return True
    return SequenceMatcher(None, an, bn).ratio() >= thresh
