"""Shared utilities: URL normalization, dedupe, query tokens, compact JSON."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, List, Set


def dumps(obj: Any) -> str:
    """One-line compact JSON - the only serialization used in tool results."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def track_params(url: str) -> str:
    """Remove tracking parameters; keep functional ones."""
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    TRACK = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "igshid", "ref_src",
        "ref_url", "share_id", "iref", "mkt_tok", "vero_id", "_ga", "yclid",
        "twclid", "wickedid", " keystroke",
    }.union({"keystroke"})
    q = [(k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=True)
         if k.lower() not in TRACK]
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(q), parts.fragment and None)) if parts.fragment else urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(q), ""))


def fingerprint_url(url: str) -> str:
    """Loose fingerprint for duplicate detection: scheme-insensitive host canon."""
    from urllib.parse import urlsplit
    try:
        p = urlsplit(url)
    except ValueError:
        return url
    host = p.netloc.lower().removeprefix("www.")
    path = p.path.rstrip("/").removesuffix("/index.html")
    return host + path


def normalize_url(url: str) -> str:
    """canonical-ish form for list dedupe: tracking params stripped."""
    return track_params(url)


STOPWORDS = set("""a an and are as at be by for from has have how i in is it its of on or s so
than that the their there they this through to too was we were what when where which who why
will with would you your about over under me my not no can could should do does did get got
""".split())


def query_tokens(q: str) -> List[str]:
    toks = re.findall(r"[a-z0-9][a-z0-9\-\+/.'#_]*", (q or "").lower())
    cleaned = [re.sub(r"[^a-z0-9\-\+/.'#_]+", "", t) for t in toks]
    return [t for t in cleaned if t] or toks


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def dedup_by(seq: Iterable[Any], key) -> List[Any]:
    out = []
    seen: Set = set()
    for item in seq:
        k = key(item)
        if k in seen:
            continue
        seen.add(k)
        out.append(item)
    return out


def to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: v for k, v in asdict(obj).items() if v is not None}
    if isinstance(obj, list):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    return obj


def term_coverage(text: str, terms: Iterable[str]) -> float:
    """Transparent signal: fraction of query terms present in text (to be used
    internally only; never returned as a score)."""
    if not text:
        return 0.0
    tokens = set(re.findall(r"[a-z0-9]{2,}", normalize_text(text)))
    hits = sum(1 for t in terms if t.lower() in tokens)
    return hits / max(1, sum(1 for t in terms))


def naive_bm25_weighted(good_tokens: List[str]) -> Counter:
    """Just a convenience Counter used by ranking for frequency weighting."""
    return Counter(t.lower() for t in good_tokens)
