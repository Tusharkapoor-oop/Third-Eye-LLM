"""Bounded primary-source link expansion.

Curated primary-source hints identify one or two authoritative pages.  Many
documentation and reference sites expose closely related pages through their
own navigation (for example, the asyncio overview links to the task-group
reference).  Fetching those pages and following a small number of same-site
links gives callers more primary evidence without asking a search provider for
extra queries or guessing URLs.

This is deliberately conservative:

* only same registrable domain links are considered;
* boilerplate and asset links are discarded;
* links must share directory structure, query terms, or a meaningful prefix
  with the source page;
* by default at most two pages are fetched and at most three links are
  returned (callers may ask for enough links to fill their result window).
"""

from __future__ import annotations

import asyncio
import posixpath
import re
from collections.abc import Iterable
from urllib.parse import urlsplit

from lxml import html as lxml_html

from ..lexical import query_terms, tokenize
from ..urls import host_of, normalize_url, registrable_domain

_SKIP_TEXT = {
    "about",
    "about us",
    "careers",
    "contact",
    "contact us",
    "cookie settings",
    "cookies",
    "home",
    "investors",
    "learn more",
    "login",
    "log in",
    "menu",
    "new",
    "news",
    "next",
    "pdf",
    "previous",
    "privacy",
    "privacy policy",
    "read more",
    "releases",
    "search",
    "sign in",
    "sign up",
    "subscribe",
    "terms",
    "terms of service",
    "wins",
}
# Query words that are structurally common in questions but too weak to
# identify a related page. They would otherwise match navigation headings such
# as "What's New" or a generic "new" link in every release note.
_GENERIC_TERMS = {
    "beyond",
    "capable",
    "companies",
    "company",
    "current",
    "differ",
    "difference",
    "different",
    "explain",
    "explained",
    "feature",
    "features",
    "function",
    "functionality",
    "introduce",
    "introduced",
    "latest",
    "major",
    "new",
    "overview",
    "predict",
    "predicting",
    "prediction",
    "release",
    "stable",
    "time",
    "times",
    "use",
    "used",
    "using",
    "version",
    "versions",
    "work",
    "works",
}
_SKIP_EXT = (
    ".css",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".mp3",
    ".mp4",
    ".png",
    ".svg",
    ".tar",
    ".xsd",
    ".zip",
)


def _tokens(text: str) -> set[str]:
    return {t for t in tokenize(text) if len(t) >= 3}


def _same_directory(source_path: str, target_path: str) -> bool:
    directory = posixpath.dirname(source_path.rstrip("/"))
    if not directory or directory == "/":
        return False
    return target_path.startswith(directory.rstrip("/") + "/")


def _strong_prefix_match(terms: set[str], tokens: set[str]) -> bool:
    """Require both a meaningful prefix and a high stem similarity.

    "alphafold" and "alphaearth" share only a generic five-letter prefix, while
    "fts5"/"fts3" and "asyncio"/"asyncio-task" are genuinely related names.
    """
    for term in terms:
        if len(term) < 3:
            continue
        for token in tokens:
            if len(token) < 3:
                continue
            common = 0
            for a, b in zip(term, token, strict=False):
                if a != b:
                    break
                common += 1
            if common < 3:
                continue
            prefix = term[:common]
            if len(re.sub(r"\d", "", prefix)) < 3:
                continue
            if common / max(len(term), len(token)) >= 0.6:
                return True
    return False


def _prefix_match(terms: set[str], tokens: set[str]) -> bool:
    """Match meaningful prefixes, but not merely shared version numbers."""
    for term in terms:
        if len(term) < 3:
            continue
        for token in tokens:
            if len(token) < 3:
                continue
            common = 0
            for a, b in zip(term, token, strict=False):
                if a != b:
                    break
                common += 1
            if common < 3:
                continue
            prefix = term[:common]
            # Four non-numeric characters avoids treating "protein"/"programs"
            # (a shared three-letter prefix) as related, while still matching
            # real variants such as "taskgroup"/"task".
            if len(re.sub(r"\d", "", prefix)) >= 4:
                return True
    return False


def _filename_family(source_path: str, target_path: str) -> bool:
    """Return True when two pages share a meaningful filename stem.

    Documentation sets commonly name related pages ``asyncio.html`` /
    ``asyncio-task.html`` or ``fts5.html`` / ``fts3.html``. Version siblings
    such as ``3.11.html`` / ``3.10.html`` deliberately do not qualify.
    """
    source_stem = posixpath.basename(source_path).rsplit(".", 1)[0].lower()
    target_stem = posixpath.basename(target_path).rsplit(".", 1)[0].lower()
    source_tokens = _tokens(source_stem.replace("-", " ").replace("_", " "))
    target_tokens = _tokens(target_stem.replace("-", " ").replace("_", " "))
    return _strong_prefix_match(source_tokens, target_tokens)


def _candidate_score(
    anchor: str,
    target: str,
    source_url: str,
    terms: set[str],
) -> int:
    text = " ".join(anchor.split()).strip()
    if not text or text.lower().strip(" .:") in _SKIP_TEXT:
        return -1
    low_target = target.lower()
    if any(ext in low_target for ext in _SKIP_EXT):
        return -1
    try:
        target_path = urlsplit(target).path.rstrip("/")
        source_path = urlsplit(source_url).path.rstrip("/")
    except ValueError:
        return -1
    if not target_path or target_path == "/":
        return -1

    target_tokens = _tokens(text + " " + target_path)
    overlap = len(terms & target_tokens)
    fuzzy = _prefix_match(terms, target_tokens)
    family = _filename_family(source_path, target_path)
    # Same-directory links are common navigation, not evidence by themselves.
    if overlap == 0 and not fuzzy and not family:
        return -1
    same_dir = _same_directory(source_path, target_path)
    return overlap * 3 + (3 if family else 0) + (2 if same_dir else 0) + (1 if fuzzy else 0)


def _scored_same_site_links(
    html_text: str,
    source_url: str,
    query: str,
    existing_urls: Iterable[str],
) -> list[tuple[int, str, str]]:
    try:
        doc = lxml_html.fromstring(html_text)
    except (ValueError, TypeError):
        return []
    terms = {t for t in query_terms(query)[0] if len(t) >= 3}
    terms -= _GENERIC_TERMS
    source_domain = registrable_domain(host_of(source_url))
    source_path = urlsplit(source_url).path.rstrip("/")
    source_stem = posixpath.basename(source_path).rsplit(".", 1)[0].lower()
    # Terms that are part of the site or page name (for example "sqlite" on
    # sqlite.org, or "asyncio" on asyncio.html) match nearly every link and add
    # no discriminating signal. Keep them out of the overlap score.
    generic = _tokens(source_domain.replace(".", " "))
    generic |= _tokens(source_stem.replace("-", " ").replace("_", " "))
    terms -= generic
    query_versions = set(re.findall(r"\b\d+\.\d+\b", query))
    existing = {u.rstrip("/") for u in existing_urls}
    existing.add(source_url.rstrip("/"))
    scored: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    for a in doc.iter("a"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        target = normalize_url(href, base=source_url)
        if not target or target.rstrip("/") in existing or target in seen:
            continue
        if registrable_domain(host_of(target)) != source_domain:
            continue
        target_versions = set(re.findall(r"\b\d+\.\d+\b", target))
        if query_versions and target_versions and not target_versions & query_versions:
            # Do not expand a version-specific query into a different release.
            continue
        anchor = " ".join(a.text_content().split())[:160]
        score = _candidate_score(anchor, target, source_url, terms)
        if score < 0:
            continue
        seen.add(target)
        scored.append((score, target, anchor))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored


def extract_same_site_links(
    html_text: str,
    source_url: str,
    query: str,
    existing_urls: Iterable[str],
    *,
    limit: int = 3,
) -> list[tuple[str, str]]:
    """Return (url, anchor) pairs that look like related primary pages."""
    scored = _scored_same_site_links(html_text, source_url, query, existing_urls)
    return [(url, anchor) for _, url, anchor in scored[:limit]]


async def expand_official_links(
    fetcher,
    official_urls: list[str],
    query: str,
    existing_urls: Iterable[str],
    *,
    max_pages: int = 2,
    max_links: int = 3,
    timeout_s: float = 2.5,
) -> list[tuple[str, str, str]]:
    """Fetch a few official pages and return (url, anchor, source_url) links."""
    if not official_urls or max_links <= 0:
        return []

    async def one(url: str) -> tuple[str, str]:
        try:
            resp = await asyncio.wait_for(
                fetcher.fetch(url, max_bytes=1_500_000, cache_ttl=3600),
                timeout=timeout_s,
            )
            return url, resp.text
        except Exception:
            return url, ""

    pages = await asyncio.gather(*(one(url) for url in official_urls[:max_pages]))
    existing = {u.rstrip("/") for u in existing_urls}
    # Score across all fetched pages, then pick globally. Processing one page at
    # a time would let a navigational page (for example a "What's New" index)
    # consume every slot before a more specific page is considered.
    best: dict[str, tuple[int, str, str, str]] = {}
    for source_url, html_text in pages:
        if not html_text:
            continue
        for score, url, anchor in _scored_same_site_links(html_text, source_url, query, existing):
            key = url.rstrip("/")
            if key in existing:
                continue
            prev = best.get(key)
            if prev is None or score > prev[0]:
                best[key] = (score, url, anchor, source_url)
    ordered = sorted(best.values(), key=lambda item: (-item[0], item[1]))
    return [(url, anchor, source) for _, url, anchor, source in ordered[:max_links]]
