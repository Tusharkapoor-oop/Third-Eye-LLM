"""Search provider interface and shared result model."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from ..urls import normalize_url, registrable_domain


@dataclass
class Hit:
    title: str
    url: str
    snippet: str
    date: str | None = None  # ISO YYYY-MM-DD
    provider: str = ""
    rank: int = 0
    meta: dict[str, str] = field(default_factory=dict)


class SearchProvider(Protocol):
    name: str

    async def search(
        self,
        query: str,
        *,
        k: int,
        freshness: str | None = None,
        domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[Hit]: ...


class ProviderUnavailable(RuntimeError):
    pass


_DATE_PATTERNS = [
    re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})\b", re.I),
    re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(20\d{2})\b", re.I),
]
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_date(text: str | None) -> str | None:
    """Extract the first plausible ISO date from a provider string."""
    if not text:
        return None
    t = text.strip()
    m = _DATE_PATTERNS[0].search(t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return None
    m = _DATE_PATTERNS[1].search(t)
    if m:
        try:
            return date(int(m.group(3)), _MONTHS[m.group(2)[:3].lower()], int(m.group(1))).isoformat()
        except (ValueError, KeyError):
            return None
    m = _DATE_PATTERNS[2].search(t)
    if m:
        try:
            return date(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2))).isoformat()
        except (ValueError, KeyError):
            return None
    return None


def clean_snippet(text: str, limit: int = 320) -> str:
    """Strip markup/entities/whitespace from a provider snippet."""
    if not text:
        return ""
    import html as html_mod

    t = re.sub(r"<[^>]{0,200}>", " ", text)
    t = html_mod.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^(?:Web result|Image result|Video result)\s*[·•]\s*", "", t, flags=re.I)
    if len(t) > limit:
        cut = t[:limit]
        p = max(cut.rfind(". "), cut.rfind("; "), cut.rfind(" "))
        t = (cut[:p] if p > limit * 0.6 else cut).rstrip() + "…"
    return t


def make_hit(
    title: str,
    url: str,
    snippet: str,
    *,
    provider: str,
    rank: int,
    date_hint: str | None = None,
) -> Hit | None:
    canon = normalize_url(url)
    if not canon:
        return None
    title = re.sub(r"\s+", " ", (title or "")).strip()[:220]
    if not title:
        title = canon
    return Hit(
        title=title,
        url=canon,
        snippet=clean_snippet(snippet),
        date=parse_date(date_hint) or parse_date(snippet),
        provider=provider,
        rank=rank,
    )


def dedupe(hits: list[Hit]) -> list[Hit]:
    """Exact canonical-URL dedupe, keeping the first (best-ranked) occurrence."""
    seen: dict[str, Hit] = {}
    out: list[Hit] = []
    for h in hits:
        key = h.url.rstrip("/")
        if key in seen:
            # enrich provenance and keep longer snippet
            prev = seen[key]
            if len(h.snippet) > len(prev.snippet):
                prev.snippet = h.snippet
            if not prev.date and h.date:
                prev.date = h.date
            if h.provider and h.provider not in prev.meta.get("providers", ""):
                prev.meta["providers"] = (prev.meta.get("providers", "") + "," + h.provider).strip(",")
            continue
        seen[key] = h
        out.append(h)
    return out


def diversify(hits: list[Hit], per_domain: int = 2) -> list[Hit]:
    """Cap results per registrable domain while preserving order."""
    counts: dict[str, int] = {}
    out: list[Hit] = []
    overflow: list[Hit] = []
    for h in hits:
        d = registrable_domain(h.url.split("/")[2]) if "/" in h.url else ""
        if counts.get(d, 0) >= per_domain:
            overflow.append(h)
            continue
        counts[d] = counts.get(d, 0) + 1
        out.append(h)
    return out + overflow


def near_duplicate(a: str, b: str, threshold: float = 0.85) -> bool:
    ta = {w for w in re.findall(r"[a-z0-9]{3,}", a.lower())}
    tb = {w for w in re.findall(r"[a-z0-9]{3,}", b.lower())}
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold
