"""Query-term relevance and domain filtering for provider results.

Search providers sometimes return results that do not contain any of the query
terms (bot pages, ad interstitials, unrelated trending content). Those results
are discarded before they reach callers or the research loop. The filter is a
lexical coverage rule, not a calibrated relevance score, and no score is exposed.
"""

from __future__ import annotations

import math
import re
from urllib.parse import urlsplit

from ..lexical import query_terms, tokenize
from .base import Hit


def host_of_url(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().strip(".")
    except ValueError:
        return ""


def domain_pattern(value: str) -> str:
    """Normalize a caller-supplied domain filter to a bare host suffix."""
    v = (value or "").strip().lower()
    if "://" in v:
        v = v.split("://", 1)[1]
    v = v.split("/", 1)[0].split(":", 1)[0].strip(".")
    if v.startswith("www."):
        v = v[4:]
    return v


def domain_matches(host: str, pattern: str) -> bool:
    if not host or not pattern:
        return False
    return host == pattern or host.endswith("." + pattern)


def _normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def is_relevant(hit: Hit, terms: list[str], phrases: list[str]) -> bool:
    """Require lexical query coverage in title, snippet or URL.

    Half of the content terms must appear (at least one). Quoted phrases must
    appear verbatim after punctuation normalization. Queries with no content
    terms are not filtered.
    """
    if not terms and not phrases:
        return True
    haystack = f"{hit.title} {hit.snippet} {hit.url}"
    tokens = set(tokenize(haystack))
    if terms:
        covered = sum(1 for term in terms if term in tokens)
        # Short queries need both terms; longer queries need at least 40% so
        # an authoritative page that covers the topic but not every modifier
        # ("usage") is not discarded.
        required = 1 if len(terms) == 1 else max(2, math.ceil(len(terms) * 0.4))
        if covered < required:
            return False
    if phrases:
        flat = _normalized(haystack)
        if not any(_normalized(p) in flat for p in phrases if p):
            return False
    return True


def filter_hits(
    hits: list[Hit],
    query: str,
    *,
    domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> tuple[list[Hit], int, int]:
    """Return (kept, off_topic_count, domain_filtered_count)."""
    terms, phrases = query_terms(query)
    include = [p for p in (domain_pattern(d) for d in (domains or [])) if p]
    exclude = [p for p in (domain_pattern(d) for d in (exclude_domains or [])) if p]
    kept: list[Hit] = []
    off_topic = 0
    domain_filtered = 0
    for hit in hits:
        host = host_of_url(hit.url)
        if include and not any(domain_matches(host, p) for p in include):
            domain_filtered += 1
            continue
        if exclude and any(domain_matches(host, p) for p in exclude):
            domain_filtered += 1
            continue
        if not is_relevant(hit, terms, phrases):
            off_topic += 1
            continue
        kept.append(hit)
    return kept, off_topic, domain_filtered
