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

from ..lexical import STOPWORDS, normalize_token, query_terms, tokenize
from .base import Hit

_REFERENCE_HOSTS = (
    "dictionary.com",
    "thesaurus.com",
    "freethesaurus.com",
    "powerthesaurus.org",
    "merriam-webster.com",
    "dictionary.cambridge.org",
    "wiktionary.org",
    "wordhippo.com",
    "thefreedictionary.com",
    "vocabulary.com",
    "collinsdictionary.com",
    "grammarbrain.com",
    "wordflowhub.com",
)
_DEFINITION_WORDS = frozenset(
    {
        "meaning",
        "definition",
        "define",
        "synonym",
        "antonym",
        "thesaurus",
        "word",
        "spell",
        "spelling",
        "pronounce",
        "pronunciation",
        "grammar",
    }
)
_AUTHORITY_SUFFIXES = (".gov", ".edu", ".mil")
_HOST_PART = re.compile(r"[a-z0-9]+")
_PROPER = re.compile(r"\b[A-Z][A-Za-z0-9]*\b")


def _stems(token: str) -> set[str]:
    """Return suffix-stripped variants so center/centers and predict/predicts match."""
    out = {token}
    if len(token) <= 4:
        return out
    for suffix in ("s", "es", "ed", "ing"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            out.add(token[: -len(suffix)])
    if token.endswith("y"):
        out.add(token[:-1] + "i")
    return out


def _host_stems(host: str) -> set[str]:
    out: set[str] = set()
    for part in _HOST_PART.findall(host):
        out |= _stems(part)
    return out


def _entity_stems(query: str) -> set[str]:
    """Capitalized entity/identifier stems from the query (Apple, NVIDIA, SEC)."""
    entities: set[str] = set()
    for raw in _PROPER.findall(query):
        token = normalize_token(raw)
        if token and token not in STOPWORDS and len(token) >= 2:
            entities |= _stems(token)
    return entities


def _is_authority(host: str, entities: set[str]) -> bool:
    if not host:
        return False
    if host.endswith(_AUTHORITY_SUFFIXES):
        return True
    return bool(_host_stems(host) & entities)


def _is_reference_site(host: str) -> bool:
    return any(domain_matches(host, d) for d in _REFERENCE_HOSTS)


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


def is_relevant(hit: Hit, terms: list[str], phrases: list[str], *, entities: set[str] | None = None) -> bool:
    """Require lexical query coverage in title, snippet or URL.

    At least 40% of content terms must appear (minimum two for multi-term
    queries). Quoted phrases must
    appear verbatim after punctuation normalization. Queries with no content
    terms are not filtered.

    Authoritative hosts (``.gov``/``.edu``/``.mil`` or a host that carries a
    query entity such as ``nvidia.com``) only need one covering term: official
    filings and product pages often have opaque titles that would otherwise be
    discarded. Suffix stripping keeps plural/verb forms from splitting an
    otherwise relevant page.
    """
    if not terms and not phrases:
        return True
    haystack = f"{hit.title} {hit.snippet} {hit.url}"
    tokens: set[str] = set()
    for token in tokenize(haystack):
        tokens |= _stems(token)
    authority = _is_authority(host_of_url(hit.url), entities or set())
    if terms:
        covered = sum(1 for term in terms if _stems(term) & tokens)
        # Short queries need both terms; longer queries need at least 40% so
        # an authoritative page that covers the topic but not every modifier
        # ("usage") is not discarded.
        required = 1 if len(terms) == 1 else max(2, math.ceil(len(terms) * 0.4))
        if covered < required and not (authority and covered >= 1):
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
    entities = _entity_stems(query)
    definition_query = bool(set(re.findall(r"[a-z]+", query.lower())) & _DEFINITION_WORDS)
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
        if not definition_query and _is_reference_site(host):
            off_topic += 1
            continue
        if not is_relevant(hit, terms, phrases, entities=entities):
            off_topic += 1
            continue
        kept.append(hit)
    return kept, off_topic, domain_filtered
