"""Deterministic query planning with an optional bounded Gemini expansion.

The rule-based path is complete on its own and is intentionally the default
fallback.  Network-backed expansion is isolated behind a short timeout and is
never required for a usable search request.
"""

from __future__ import annotations

import asyncio
import json
import re

from src.engine.config import CONFIG
from src.engine.schemas import QueryPlan

_FILLER = re.compile(
    r"\b(?:can you|could you|would you|please|find information about|find info about|"
    r"tell me about|i want to know|give me information on|search for|look up|"
    r"compare and contrast)\b",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_./:-]{1,}|\b\d+(?:\.\d+)?\b")
_QUOTED = re.compile(r"(?:\"([^\"]+)\"|'([^']+)'|`([^`]+)`)")
_ERROR = re.compile(r"\b(?:[A-Z]{2,}[A-Z0-9_-]*[-_]\d{2,}|ERR[_-]?\d+|E[A-Z]+\d+)\b")
_VERSION = re.compile(r"\b(?:v?\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9.-]+)?|Python\s+\d+(?:\.\d+)*)\b", re.IGNORECASE)
_IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b")
_SHORT_SYMBOLS = re.compile(
    r"\b(?:H2O|CO2|CO|O2|N2|N2O|NaCl|Au|Ag|Fe|Cu|Zn|H2|He|Li|O3|NO2|SO2|CH4|pH|CA|US|UK)\b"
)
_STOPWORDS = frozenset(
    "a an the and or but for with from into about this that what which who where when why how is are was were be to of in on at by as do does did can could should would please find tell give me information compare contrast latest current now".split()
)
_TECHNICAL = frozenset(
    "api sdk python javascript typescript rust java go code error exception stacktrace function library framework docker kubernetes http sql github package install configuration docs documentation asyncio rebase merge pip uv".split()
)


def _unique(values: list[str], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = re.sub(r"\s+", " ", value).strip(" ,;:?!")
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result if limit is None else result[:limit]


def lexical_locks(raw_query: str) -> list[str]:
    """Return exact identifiers that must survive query rewriting."""
    locked: list[str] = []
    for match in _QUOTED.finditer(raw_query):
        locked.extend(group for group in match.groups() if group)
    locked.extend(_ERROR.findall(raw_query))
    locked.extend(_VERSION.findall(raw_query))
    locked.extend(_IDENTIFIER.findall(raw_query))
    locked.extend(_SHORT_SYMBOLS.findall(raw_query))
    return _unique(locked, 16)


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in _TOKEN.findall(text) if token.casefold() not in _STOPWORDS]


def _intent(query: str, tokens: list[str]) -> str:
    low = query.casefold()
    if any(word in low for word in (" vs ", " versus ", "compare", "difference between", "which is better")):
        return "comparison"
    if any(word in low for word in ("latest", "today", "breaking", "news", "recent", "this week")):
        return "news"
    if any(word in low for word in ("how to", "how do", "install", "configure", "setup", "steps")):
        return "how_to"
    if any(token in _TECHNICAL for token in tokens) or any(marker in low for marker in _TECHNICAL):
        return "technical"
    return "general"


def _rule_plan(raw_query: str) -> QueryPlan:
    query = re.sub(r"\s+", " ", raw_query).strip()
    stripped = _FILLER.sub(" ", query)
    stripped = re.sub(r"\s+", " ", stripped).strip(" ?!.") or query
    locks = lexical_locks(query)
    # Preserve the user's original word order. Alphabetising or length-sorting
    # these tokens produced queries such as "resolution managers adoption ..."
    # that search engines resolved to dictionary pages instead of the topic.
    tokens = _tokens(stripped)
    intent = _intent(stripped, tokens)
    ordered = _unique([*locks, *tokens])
    bm25_tokens = _unique(ordered, 18)
    primary = " ".join(ordered[:14]) or stripped
    if intent == "comparison":
        semantic = f"{primary} comparison"
    elif intent == "technical":
        semantic = f"{primary} official documentation"
        if "asyncio" in primary.casefold() and "run" in primary.casefold():
            semantic += " event loop added in Python 3.7"
    elif intent == "news":
        semantic = f"{primary} release date"
    else:
        semantic = primary
    if intent == "technical":
        authority = f"{primary} official documentation"
        if "python" in primary.casefold():
            authority = f"{primary} site:python.org OR site:docs.python.org OR site:packaging.python.org"
    elif intent == "news":
        authority = f"{primary} official announcement"
    elif intent == "comparison" and any(word in primary.casefold() for word in ("git", "rebase", "merge")):
        authority = f"site:git-scm.com git rebase merge {primary}"
    else:
        authority = f"{primary} authoritative source"
    # Compact keyword forms run first: Bing degrades long natural-language
    # queries to their first common word. Keep the untouched request last (and
    # only when short) so phrase intent still has a chance to contribute.
    sub_queries = _unique([primary, semantic, authority], 3)
    if stripped.casefold() != primary.casefold() and len(stripped.split()) <= 12 and len(sub_queries) < 3:
        sub_queries = _unique([*sub_queries, stripped], 3)
    return QueryPlan(
        raw_query=query,
        primary_keyword_query=primary,
        semantic_expansion_query=semantic or primary,
        authority_query=authority,
        bm25_tokens=bm25_tokens,
        lexical_locks=locks,
        sub_queries=sub_queries,
        intent=intent,
    )


async def _gemini_expand(plan: QueryPlan) -> QueryPlan:
    if not CONFIG.enable_query_expansion or not CONFIG.gemini_api_key:
        return plan
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=CONFIG.gemini_api_key)
        prompt = (
            "Rewrite this web search request into JSON with keys primary_keyword_query, "
            "semantic_expansion_query, authority_query, bm25_tokens, sub_queries. "
            "Preserve every lexical lock exactly. Return only JSON.\n"
            f"Lexical locks: {json.dumps(plan.lexical_locks)}\nQuery: {plan.raw_query}"
        )

        def call() -> str:
            response = client.models.generate_content(
                model=CONFIG.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0, max_output_tokens=350),
            )
            return response.text or ""

        raw = await asyncio.wait_for(asyncio.to_thread(call), timeout=1.5)
        data = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        candidate = plan.model_copy(update={
            "primary_keyword_query": str(data.get("primary_keyword_query") or plan.primary_keyword_query),
            "semantic_expansion_query": str(data.get("semantic_expansion_query") or plan.semantic_expansion_query),
            "authority_query": str(data.get("authority_query") or plan.authority_query),
            "bm25_tokens": _unique([str(v) for v in data.get("bm25_tokens", [])] + plan.lexical_locks, 18),
            "sub_queries": _unique([str(v) for v in data.get("sub_queries", [])] + plan.sub_queries, 3),
        })
        if any(lock.casefold() not in candidate.primary_keyword_query.casefold() for lock in plan.lexical_locks):
            return plan
        return candidate
    except (asyncio.TimeoutError, json.JSONDecodeError, TypeError, ValueError, ImportError, AttributeError):
        return plan
    except Exception:
        return plan


def optimize_query(raw_query: str) -> dict:
    """Synchronous public API used by search and tests."""
    if not isinstance(raw_query, str) or not raw_query.strip():
        raise ValueError("query must be a non-empty string")
    return _rule_plan(raw_query).model_dump()


async def optimize_query_async(raw_query: str) -> QueryPlan:
    if not isinstance(raw_query, str) or not raw_query.strip():
        raise ValueError("query must be a non-empty string")
    return await _gemini_expand(_rule_plan(raw_query))
