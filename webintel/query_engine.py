"""Precision query intelligence.

Raw agent prompts ("my python thing crashes when i gather tasks, wat do") are a
poor fit for a lexical search backend. This module turns them into a
``QueryPlan`` with four independent artefacts:

1. ``primary_keyword_query`` - high-precision lexical query for SearXNG/Bing.
2. ``semantic_expansion_query`` - alternative terminology, for conceptual
   queries where the user's wording does not appear in the source.
3. ``authority_query`` - same intent, constrained to primary sources.
4. ``bm25_tokens`` - distilled high-IDF terms used by the passage reranker.

A Gemini call (``gemini-2.5-flash``) is attempted with a hard 1.5 s budget. On
any error, timeout, missing key or malformed JSON the deterministic rule engine
wins. Expansion is therefore never a single point of failure.
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Optional

from .schemas import GeminiQueryPlan, Intent, QueryPlan

EXPANSION_TIMEOUT_S = 1.5
MAX_LOCKS = 10
MAX_BM25_TOKENS = 16

# ---------------------------------------------------------------------------
# Lexical locks
# ---------------------------------------------------------------------------
_QUOTED = re.compile(r'"([^"\n]{2,120})"|\u201c([^\u201d\n]{2,120})\u201d')
_BACKTICK = re.compile(r"`([^`\n]{1,160})`")
_VERSION = re.compile(r"\bv?\d+\.\d+(?:\.\d+)?(?:-[a-z0-9.]+)?\b", re.I)
_IDENT = re.compile(
    r"\b(?:[A-Za-z_][A-Za-z0-9_]*"
    r"(?:(?:::|\\.|->|_)[A-Za-z_][A-Za-z0-9_]*)+"
    r"|[a-z]+[A-Z][A-Za-z0-9]*"
    r"|[A-Za-z_][A-Za-z0-9_]*\(\))"
)
_FILE = re.compile(r"\b[\w./-]+\.(?:py|js|ts|tsx|jsx|json|toml|ya?ml|md|txt|rs|go|java|cpp|c|h|sql|sh|ps1|bat)\b", re.I)
_ERROR_CODE = re.compile(r"\b(?:[A-Z][A-Za-z]*(?:Error|Exception|Warning)|E[A-Z]{4,}|HTTP\s?[45]\d\d)\b")
_HEX = re.compile(r"\b0x[0-9a-fA-F]{4,}\b")
_PATH = re.compile(r"(?:[A-Za-z]:\\[^\s\"']+|~?/(?:[\w.-]+/)+[\w.-]+)")

_TECH_MARKERS = re.compile(
    r"(Traceback|Exception|Error:|stack ?trace|segfault|undefined is not|"
    r"\b(?:python|javascript|typescript|rust|golang|java|c\+\+|sql|bash|powershell|react|next\.?js|"
    r"fastapi|django|flask|docker|kubernetes|npm|pip|uv|cargo|git|api|sdk|json|yaml|http|"
    r"async|await|thread|coroutine|compile|runtime|dependency|webpack|vite)\b)",
    re.I,
)
_COMPARISON = re.compile(r"\b(vs\.?|versus|compare|comparison|difference between|better than|pros and cons|"
                         r"which (?:is|one)|alternatives?|benchmark)\b", re.I)
_NEWS = re.compile(r"\b(latest|today|yesterday|this (?:week|month|year)|breaking|announced|"
                   r"release[ds]?|changelog|roadmap|news|20(?:2[4-9]|3\d))\b", re.I)
_RESEARCH = re.compile(r"\b(how does|why does|explain|mechanism|architecture|trade-?offs?|"
                       r"internals?|under the hood|design|research|survey|state of the art)\b", re.I)

_LEAD_FILLER = re.compile(
    r"^(?:please|pls|hey|hi|hello|can you|could you|i need to|i want to|i'm trying to|"
    r"im trying to|help me|tell me|show me|give me|find me|what(?:'s| is) the best way to|"
    r"how (?:do|can|should) i|how to)\s+",
    re.I,
)
_TAIL_FILLER = re.compile(r"\s+(?:please|thanks|thank you|for me|asap)\s*[.!?]*$", re.I)

_SYNONYMS: dict[str, str] = {
    "not working": "fails error",
    "doesn't work": "fails error",
    "does not work": "fails error",
    "won't work": "fails error",
    "bug": "bug issue",
    "crash": "crash exception traceback",
    "crashes": "crashes exception traceback",
    "slow": "performance latency slow",
    "fast": "performance throughput low-latency",
    "install": "install installation setup",
    "setup": "setup configuration install",
    "config": "configuration config settings",
    "auth": "authentication authorization",
    "db": "database",
    "docs": "documentation reference",
    "price": "pricing cost",
    "pricing": "pricing cost plans",
    "vs": "versus comparison",
    "compare": "comparison versus",
    "latest": "latest release changelog",
    "mcp": "model context protocol mcp",
}

_CODE_TERMS = {
    "error", "exception", "traceback", "async", "await", "coroutine", "function",
    "class", "method", "module", "package", "import", "compile", "runtime", "python",
    "javascript", "typescript", "rust", "golang", "sql", "api", "sdk", "cli",
}


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        v = v.strip()
        if not v:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def extract_lexical_locks(text: str, limit: int = MAX_LOCKS) -> list[str]:
    """Preserve strings that must survive query rewriting verbatim.

    Quoted terms, backticked identifiers, versions, compound identifiers, file
    names, error class names, hex constants and absolute paths are collected in
    first-seen order. Losing any of these is the classic cause of "the search
    engine searched for the wrong thing".
    """
    if not text:
        return []
    found: list[tuple[int, str]] = []
    for pattern in (_QUOTED, _BACKTICK, _ERROR_CODE, _FILE, _IDENT, _VERSION, _HEX, _PATH):
        for m in pattern.finditer(text):
            value = next((g for g in m.groups() if g), m.group(0))
            value = value.strip().strip("\u201c\u201d\"'`")
            if 1 <= len(value) <= 160:
                found.append((m.start(), value))
    found.sort(key=lambda item: item[0])
    return _dedupe([v for _, v in found])[:limit]


def detect_intent(text: str, technical: bool) -> Intent:
    q = text or ""
    if _COMPARISON.search(q):
        return "comparison"
    if _NEWS.search(q):
        return "news"
    if technical:
        return "code"
    if _RESEARCH.search(q):
        return "research"
    return "general"


def is_technical(text: str, locks: Optional[list[str]] = None) -> bool:
    q = text or ""
    if _TECH_MARKERS.search(q):
        return True
    tokens = set(re.findall(r"[a-z0-9_+.#]+", q.lower()))
    if tokens & _CODE_TERMS:
        return True
    locks = locks if locks is not None else extract_lexical_locks(q)
    return any(
        re.search(r"[_()\[\]{}]|::|\d+\.\d+", lock) or lock.endswith((".py", ".js", ".ts", ".rs", ".go"))
        for lock in locks
    )


def _strip_filler(text: str) -> str:
    q = _LEAD_FILLER.sub("", (text or "").strip())
    q = _TAIL_FILLER.sub("", q)
    return re.sub(r"\s+", " ", q).strip(" ?!.,") or (text or "").strip()


def _content_tokens(text: str) -> list[str]:
    from .utils import STOPWORDS

    raw = re.findall(r"[A-Za-z0-9][A-Za-z0-9_+.#:/-]*", text or "")
    out: list[str] = []
    for tok in raw:
        low = tok.lower().strip(".,:;!?")
        if not low or low in STOPWORDS or len(low) < 2 and not low.isdigit():
            continue
        out.append(low)
    return _dedupe(out)


def _distil_bm25(text: str, locks: list[str]) -> list[str]:
    tokens = _content_tokens(text)
    # Identifiers and versions are the highest-IDF terms available; put them first.
    lock_tokens = [lock.lower() for lock in locks]
    merged = _dedupe(lock_tokens + tokens)
    return merged[:MAX_BM25_TOKENS]


def _semantic_query(text: str, locks: list[str], technical: bool, intent: Intent) -> str:
    base = _strip_filler(text)
    low = base.lower()
    additions: list[str] = []
    for phrase, expansion in _SYNONYMS.items():
        if phrase in low and expansion not in low:
            additions.append(expansion)
    # Identifiers are meaningless to a semantic engine but essential to the
    # lexical one; keep at most three here to avoid keyword stuffing.
    lexical = " ".join(locks[:3]) if technical else ""
    parts = [base, " ".join(additions), lexical]
    if intent == "code" and "example" not in low:
        parts.append("working example")
    if intent == "comparison" and "benchmark" not in low:
        parts.append("comparison benchmark")
    return re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()[:380]


def _authority_query(text: str, technical: bool, intent: Intent) -> str:
    base = _strip_filler(text)
    if intent == "comparison":
        sites = "site:github.com OR site:docs.* OR site:arxiv.org"
    elif technical:
        sites = ("site:github.com OR site:stackoverflow.com OR site:developer.mozilla.org "
                 "OR site:docs.python.org OR site:learn.microsoft.com")
    elif intent == "news":
        sites = "site:reuters.com OR site:arstechnica.com OR site:theverge.com OR site:techcrunch.com"
    else:
        sites = "site:github.com OR site:arxiv.org OR site:docs.*"
    return f"{base} ({sites})"[:400]


def rule_plan(text: str) -> QueryPlan:
    """Deterministic plan. Always available, zero latency, no network."""
    t0 = time.perf_counter()
    locks = extract_lexical_locks(text)
    technical = is_technical(text, locks)
    intent = detect_intent(text, technical)
    stripped = _strip_filler(text)
    primary = stripped

    # Lexical lock preservation: a query rewritten without the exact error
    # string is a different query. Re-attach any lock the cleaner dropped.
    missing = [lock for lock in locks if lock.lower() not in primary.lower()]
    if missing:
        primary = (primary + " " + " ".join(missing)).strip()

    plan = QueryPlan(
        original=text,
        primary_keyword_query=primary[:400] or text[:400],
        semantic_expansion_query=_semantic_query(text, locks, technical, intent),
        authority_query=_authority_query(text, technical, intent),
        bm25_tokens=_distil_bm25(text, locks),
        lexical_locks=locks,
        technical=technical,
        intent=intent,
        source="rules",
    )
    plan.expand_ms = int((time.perf_counter() - t0) * 1000)
    return plan


# ---------------------------------------------------------------------------
# Gemini expansion
# ---------------------------------------------------------------------------
_CLIENTS: dict[str, object] = {}

_EXPANSION_PROMPT = """You rewrite search queries for a lexical web search engine and a passage reranker.

Return STRICT JSON with exactly these keys:
  primary_keyword_query   - 3-12 tokens, exact technical terms kept verbatim, no filler words
  semantic_expansion_query- same information need using alternative terminology/synonyms
  authority_query         - the primary query plus a site: restriction to primary sources
  bm25_tokens             - 4-14 lowercase high-information terms for passage scoring
  technical               - true if this needs code/docs/repos

Rules:
- The following verified lexical locks MUST appear verbatim in primary_keyword_query: {locks}
- Never invent error codes, versions, or identifiers.
- Write all fields in English, regardless of the input language.
- Output JSON only, no markdown fences.

User query: {query}
"""


def _gemini_key() -> Optional[str]:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or None


def gemini_client():
    """Lazy singleton client. Returns None when no key is configured."""
    key = _gemini_key()
    if not key:
        return None
    cached = _CLIENTS.get(key)
    if cached is not None:
        return cached
    try:
        from google import genai

        client = genai.Client(api_key=key)
        _CLIENTS[key] = client
        return client
    except Exception:
        return None


def gemini_available() -> bool:
    return _gemini_key() is not None


async def _expand_with_gemini(text: str, fallback: QueryPlan, timeout_s: float) -> QueryPlan:
    client = gemini_client()
    if client is None:
        return fallback
    prompt = _EXPANSION_PROMPT.format(
        locks=", ".join(fallback.lexical_locks) or "(none detected)",
        query=text[:1200],
    )
    try:
        from google.genai import types

        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=os.environ.get("WEBINTEL_QUERY_MODEL", "gemini-2.5-flash"),
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                    response_schema=GeminiQueryPlan,
                ),
            ),
            timeout=timeout_s,
        )
        raw = (getattr(response, "text", None) or "").strip()
        if not raw:
            return fallback
        parsed = GeminiQueryPlan.model_validate_json(raw)
    except Exception:
        return fallback

    primary = parsed.primary_keyword_query.strip()
    # Never trust the model to preserve locks: re-attach missing ones.
    missing = [lock for lock in fallback.lexical_locks if lock.lower() not in primary.lower()]
    if missing:
        primary = (primary + " " + " ".join(missing)).strip()

    tokens = _dedupe([t.lower() for t in parsed.bm25_tokens if t.strip()])
    tokens = _dedupe([lock.lower() for lock in fallback.lexical_locks] + tokens)[:MAX_BM25_TOKENS]
    technical = bool(parsed.technical or fallback.technical)
    return QueryPlan(
        original=text,
        primary_keyword_query=primary[:400] or fallback.primary_keyword_query,
        semantic_expansion_query=(parsed.semantic_expansion_query.strip()[:400]
                                  or fallback.semantic_expansion_query),
        authority_query=(parsed.authority_query.strip()[:400]
                         or fallback.authority_query),
        bm25_tokens=tokens or fallback.bm25_tokens,
        lexical_locks=fallback.lexical_locks,
        technical=technical,
        intent=detect_intent(text, technical),
        source="gemini",
    )


async def expand_query(text: str, timeout_s: float = EXPANSION_TIMEOUT_S) -> QueryPlan:
    """Rule plan first, Gemini refinement with a hard timeout.

    The rule plan is computed before the network call so that a timeout still
    leaves a fully-formed, high-precision query plan.
    """
    t0 = time.perf_counter()
    fallback = rule_plan(text)
    if not gemini_available():
        fallback.expand_ms = int((time.perf_counter() - t0) * 1000)
        return fallback
    plan = await _expand_with_gemini(text, fallback, timeout_s)
    plan.expand_ms = int((time.perf_counter() - t0) * 1000)
    return plan
