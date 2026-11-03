"""Pre-scrape domain authority scoring.

The cost of extraction dominates a search request, so deciding *which* URLs are
worth scraping matters more than ranking after the fact. This module implements
a deterministic, auditable tier table plus path-level boosts.

Scores are internal: they shape ordering and diagnostics only. They are never
emitted to MCP callers (project rule R2).
"""
from __future__ import annotations

from urllib.parse import urlsplit

from .ranking import registrable_domain

# Domain-level base scores. Positive = primary source, negative = low signal.
PRIMARY_SOURCES: dict[str, float] = {
    "docs.python.org": 1.5,
    "peps.python.org": 1.5,
    "developer.mozilla.org": 1.5,
    "docs.rs": 1.5,
    "doc.rust-lang.org": 1.5,
    "go.dev": 1.4,
    "pkg.go.dev": 1.4,
    "learn.microsoft.com": 1.4,
    "kubernetes.io": 1.4,
    "postgresql.org": 1.4,
    "docs.docker.com": 1.3,
    "modelcontextprotocol.io": 1.5,
    "react.dev": 1.4,
    "nextjs.org": 1.2,
    "vite.dev": 1.3,
    "fastapi.tiangolo.com": 1.4,
    "docs.djangoproject.com": 1.4,
    "flask.palletsprojects.com": 1.3,
    "nodejs.org": 1.3,
    "typescriptlang.org": 1.3,
    "rust-lang.org": 1.2,
    "python.org": 1.1,
    "isocpp.org": 1.2,
    "cppreference.com": 1.1,
    "arxiv.org": 1.2,
    "pubmed.ncbi.nlm.nih.gov": 1.4,
    "nature.com": 1.1,
    "science.org": 1.1,
    "ieee.org": 1.0,
    "acm.org": 1.0,
    "openai.com": 1.0,
    "anthropic.com": 1.0,
    "deepmind.google": 1.0,
    "blog.google": 0.9,
    "cloudflare.com": 0.7,
    "aws.amazon.com": 0.9,
    "azure.microsoft.com": 0.9,
    "github.com": 0.8,
    "gitlab.com": 0.6,
    "stackoverflow.com": 0.45,
    "serverfault.com": 0.35,
    "superuser.com": 0.3,
    "wikipedia.org": 0.3,
    "docs.aws.amazon.com": 1.3,
    "developer.chrome.com": 1.3,
    "web.dev": 1.2,
    "sqlite.org": 1.2,
    "nginx.org": 1.2,
    "redis.io": 1.2,
    "mongodb.com": 1.0,
    "supabase.com": 1.0,
    "firebase.google.com": 1.1,
    "vercel.com": 0.9,
    "huggingface.co": 0.9,
}

PRESS_SOURCES: dict[str, float] = {
    "reuters.com": 0.6,
    "apnews.com": 0.6,
    "arstechnica.com": 0.5,
    "theregister.com": 0.4,
    "theverge.com": 0.4,
    "techcrunch.com": 0.3,
    "infoq.com": 0.5,
    "thenewstack.io": 0.4,
    "wired.com": 0.3,
    "bloomberg.com": 0.4,
    "ft.com": 0.4,
    "wsj.com": 0.3,
    "nytimes.com": 0.3,
    "bbc.com": 0.3,
    "bbc.co.uk": 0.3,
}

LOW_SIGNAL_SOURCES: dict[str, float] = {
    "linkedin.com": -1.0,
    "quora.com": -0.8,
    "pinterest.com": -1.0,
    "facebook.com": -1.0,
    "tiktok.com": -1.0,
    "instagram.com": -0.9,
    "medium.com": -0.35,
    "dev.to": -0.25,
    "w3schools.com": -0.5,
    "tutorialspoint.com": -0.9,
    "javatpoint.com": -0.9,
    "geeksforgeeks.org": -0.3,
    "scaler.com": -0.7,
    "interviewbit.com": -0.7,
    "simplilearn.com": -0.9,
    "educative.io": -0.6,
    "freecodecamp.org": -0.2,
    "codeproject.com": -0.4,
    "sourceforge.net": -0.6,
    "softpedia.com": -0.8,
    "alternativeto.net": -0.7,
    "capterra.com": -0.8,
    "g2.com": -0.7,
    "trustradius.com": -0.8,
    "reddit.com": -0.15,
    "news.ycombinator.com": 0.1,
    "x.com": -0.4,
    "twitter.com": -0.4,
}

_PATH_BOOSTS: tuple[tuple[str, float], ...] = (
    ("/docs/", 0.45),
    ("/documentation/", 0.45),
    ("/reference/", 0.35),
    ("/api/", 0.30),
    ("/manual/", 0.30),
    ("/guide/", 0.20),
    ("/issues/", 0.35),
    ("/blob/", 0.35),
    ("/pull/", 0.20),
    ("/releases/", 0.25),
    ("/changelog", 0.25),
    ("/blog/", 0.05),
)


def _suffix_match(host: str, table: dict[str, float]) -> float | None:
    """Longest suffix match so ``docs.aws.amazon.com`` beats ``amazon.com``."""
    best: tuple[int, float] | None = None
    for domain, value in table.items():
        if host == domain or host.endswith("." + domain):
            if best is None or len(domain) > best[0]:
                best = (len(domain), value)
    return best[1] if best else None


def authority_score(url: str) -> float:
    """Return a score in roughly [-1.5, +2.0]. Unknown domains score 0."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return -0.5
    host = (parts.hostname or "").lower().removeprefix("www.")
    if not host:
        return -0.5
    rd = registrable_domain(host)

    score = 0.0
    matched = False
    for table in (PRIMARY_SOURCES, PRESS_SOURCES, LOW_SIGNAL_SOURCES):
        value = _suffix_match(host, table)
        if value is not None:
            score += value
            matched = True
            break

    if not matched:
        if host.endswith((".edu", ".ac.uk", ".gov")):
            score += 0.6
        elif host.endswith(".org") and rd not in ("medium.com",):
            score += 0.05
        # A bare IP or a host with no dot is almost always noise.
        if "." not in host:
            score -= 0.6

    path = (parts.path or "/").lower()
    for fragment, boost in _PATH_BOOSTS:
        if fragment in path:
            score += boost
            break

    # GitHub repo roots and issue pages are primary evidence; gists less so.
    if rd == "github.com":
        if len([p for p in path.split("/") if p]) <= 2:
            score += 0.15
        if "/gist." in host:
            score -= 0.3

    return round(max(-1.5, min(2.0, score)), 3)


def authority_label(url: str) -> str:
    """Human-readable tier used by arena diagnostics."""
    score = authority_score(url)
    if score >= 1.2:
        return "primary-docs"
    if score >= 0.6:
        return "authoritative"
    if score >= 0.15:
        return "credible"
    if score >= -0.2:
        return "neutral"
    if score >= -0.6:
        return "low-signal"
    return "seo-farm"
