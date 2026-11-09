"""Shared lexical primitives.

Kept free of package-level imports so both search and extraction can use it
without a circular dependency.
"""

from __future__ import annotations

import re

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "if",
    "then",
    "than",
    "that",
    "this",
    "these",
    "those",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "by",
    "from",
    "as",
    "at",
    "it",
    "its",
    "how",
    "what",
    "why",
    "when",
    "where",
    "who",
    "which",
    "do",
    "does",
    "did",
    "can",
    "could",
    "should",
    "would",
    "will",
    "may",
    "might",
    "must",
    "i",
    "you",
    "we",
    "they",
    "he",
    "she",
    "my",
    "your",
    "our",
    "their",
    "about",
    "into",
    "over",
    "under",
    "between",
    "vs",
    "versus",
}

TOKEN = re.compile(r"[a-z0-9][a-z0-9_+.#:-]*", re.I)


def normalize_token(token: str) -> str:
    """Lowercase and drop sentence punctuation while keeping internal dots."""
    t = token.lower().strip("._+:#-")
    # A trailing dot is sentence punctuation unless it is a version-like token.
    if t.endswith(".") and not re.search(r"\d\.\d", t):
        t = t.rstrip(".")
    return t


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for raw in TOKEN.findall(text):
        t = normalize_token(raw)
        if not t:
            continue
        out.append(t)
        # Index identifier parts too: "asyncio.timeout" should match "asyncio"
        # and "timeout" without losing the exact form.
        if any(sep in t for sep in "._-:#"):
            for part in re.split(r"[._\-:#]", t):
                if len(part) >= 3 and not part.isdigit():
                    out.append(part)
    return out


def query_terms(query: str) -> tuple[list[str], list[str]]:
    """Return (unique content terms, quoted phrases)."""
    phrases = [p.strip().lower() for p in re.findall(r'"([^"]{2,80})"', query)]
    cleaned = re.sub(r"\"[^\"]*\"", " ", query)
    seen: list[str] = []
    for t in tokenize(cleaned):
        if t in STOPWORDS or len(t) < 2 or t.isdigit() and len(t) < 4:
            continue
        if t not in seen:
            seen.append(t)
    return seen, phrases
