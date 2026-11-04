"""Precision Query Intelligence and Expansion Engine.

Transforms natural language prompts into optimized lexical queries, semantic expansions,
and authority-targeted sub-queries with Lexical Lock for exact technical tokens.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field

from config import CONFIG

# Conversational filler phrases to strip from raw search prompts
CONVERSATIONAL_FILLERS = (
    r"^(can\s+you\s+(please\s+)?(tell\s+me|find|search|show\s+me|explain))\s+",
    r"^(could\s+you\s+(please\s+)?(tell\s+me|find|search|show\s+me|explain))\s+",
    r"^(what\s+is\s+the\s+(best\s+way\s+to|meaning\s+of|difference\s+between))\s+",
    r"^(how\s+(do\s+i|can\s+we|to))\s+",
    r"^(i\s+(want\s+to|need\s+to|am\s+looking\s+for))\s+",
    r"^(please\s+(find|search|show|explain))\s+",
    r"^(give\s+me\s+(an\s+overview\s+of|information\s+about))\s+",
    r"^(compare\s+and\s+contrast)\s+",
    r"^(tell\s+me\s+about)\s+",
)

# Technical / coding intent keywords
TECH_INTENT_KEYWORDS = frozenset({
    "error", "bug", "exception", "traceback", "stacktrace", "function", "method",
    "class", "async", "await", "promise", "api", "sdk", "library", "framework",
    "install", "pip", "npm", "cargo", "docker", "python", "typescript", "javascript",
    "rust", "golang", "c++", "linux", "git", "github", "react", "nextjs", "fastapi",
})


@dataclass
class QueryPlan:
    """Structured query decomposition and expansion plan."""

    raw_query: str
    primary_keyword_query: str
    semantic_expansion_query: str
    authority_query: str
    bm25_tokens: list[str]
    sub_queries: list[str] = field(default_factory=list)
    lexical_locks: list[str] = field(default_factory=list)
    is_technical: bool = False


def extract_lexical_locks(query: str) -> list[str]:
    """Extract exact-match lexical tokens that must be preserved verbatim.

    Includes quoted strings, semver versions, dotted identifiers, error codes, and flags.
    """
    locks: list[str] = []

    # 1. Quoted terms: "something specific" or 'something specific'
    quoted = re.findall(r'["\']([^"\']{2,60})["\']', query)
    locks.extend(quoted)

    # 2. Semantic versioning: v1.2.3, 2.0.0, 3.11.4
    versions = re.findall(r"\bv?\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9.]+)?\b", query)
    locks.extend(versions)

    # 3. Programming identifiers / dotted paths: os.path.exists, TaskGroup.create_task
    identifiers = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+\b", query)
    locks.extend(identifiers)

    # 4. Error names: TypeError, ConnectionResetError, 404, 502
    errors = re.findall(r"\b(?:[A-Z][a-zA-Z]*(?:Error|Exception|Warning)|HTTP\s*\d{3}|\b[45]\d{2}\b)\b", query)
    locks.extend(errors)

    # 5. CLI flags: --max-results, -rf
    flags = re.findall(r"(?:--[a-zA-Z0-9_-]+|-[a-zA-Z])", query)
    locks.extend(flags)

    return list(dict.fromkeys(locks))


def clean_conversational_query(raw_query: str) -> str:
    """Strip conversational filler while keeping core question intact."""
    clean = raw_query.strip()
    for pattern in CONVERSATIONAL_FILLERS:
        clean = re.sub(pattern, "", clean, flags=re.IGNORECASE).strip()

    # Normalize multiple whitespace and trailing question marks
    clean = re.sub(r"\s+", " ", clean)
    clean = clean.rstrip("?").strip()
    return clean if clean else raw_query.strip()


def build_rule_based_plan(raw_query: str) -> QueryPlan:
    """Deterministic, zero-latency rule-based query expansion plan."""
    cleaned = clean_conversational_query(raw_query)
    locks = extract_lexical_locks(raw_query)

    # Detect technical intent
    words = re.findall(r"\b[a-zA-Z0-9_.-]+\b", raw_query.lower())
    is_tech = bool(set(words) & TECH_INTENT_KEYWORDS) or bool(locks)

    # Primary keyword query
    primary = cleaned

    # Semantic expansion: replace common action verbs with domain equivalents
    semantic = cleaned
    semantic = re.sub(r"\b(fix|resolve)\b", "solution workaround troubleshooting", semantic, flags=re.IGNORECASE)
    semantic = re.sub(r"\b(create|make|build)\b", "implementation tutorial guide", semantic, flags=re.IGNORECASE)
    semantic = re.sub(r"\b(compare|vs)\b", "benchmark comparison differences", semantic, flags=re.IGNORECASE)

    # Authority query: target official sources for technical queries
    if is_tech:
        authority = f"{cleaned} (site:github.com OR site:stackoverflow.com OR site:docs.* OR site:*.org)"
    else:
        authority = f"{cleaned} (site:wikipedia.org OR site:reuters.com OR site:apnews.com OR site:*.gov)"

    # BM25 tokens: High-IDF tokens, excluding short stopwords
    stopwords = frozenset({
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
        "by", "is", "are", "was", "were", "be", "been", "have", "has", "had", "do", "does",
        "did", "can", "could", "will", "would", "should", "what", "which", "who", "when",
        "where", "why", "how", "all", "each", "every", "both", "some", "any", "this", "that",
    })
    bm25 = [w for w in words if len(w) > 2 and w not in stopwords]
    # Always ensure lexical lock tokens are in BM25 tokens
    for lock in locks:
        lock_clean = lock.lower().strip('"\'')
        if lock_clean and lock_clean not in bm25:
            bm25.insert(0, lock_clean)

    # Decompose comparisons: "X vs Y" -> ["X", "Y", "X vs Y"]
    sub_queries: list[str] = [primary]
    vs_match = re.search(r"(.+?)\s+(?:vs\.?|versus|compared\s+to)\s+(.+)", cleaned, re.IGNORECASE)
    if vs_match:
        part1 = vs_match.group(1).strip()
        part2 = vs_match.group(2).strip()
        sub_queries = [cleaned, f"{part1} overview features", f"{part2} overview features"]

    return QueryPlan(
        raw_query=raw_query,
        primary_keyword_query=primary,
        semantic_expansion_query=semantic,
        authority_query=authority,
        bm25_tokens=bm25,
        sub_queries=sub_queries[:3],
        lexical_locks=locks,
        is_technical=is_tech,
    )


async def plan_query_fast(raw_query: str) -> QueryPlan:
    """Asynchronous query planner using Gemini 2.5 Flash with 1.5s timeout.

    Falls back instantly to rule-based expansion if Gemini key is missing or call times out.
    """
    rule_plan = build_rule_based_plan(raw_query)

    if not CONFIG.gemini_api_key:
        return rule_plan

    try:
        from google import genai
        client = genai.Client(api_key=CONFIG.gemini_api_key)

        prompt = (
            "You are an expert search engine query optimizer. Given the user query, output a JSON object with:\n"
            "- primary_keyword_query: concise search query without conversational filler\n"
            "- semantic_expansion_query: query using synonyms and conceptual terms\n"
            "- sub_queries: list of up to 3 parallel sub-queries for multi-hop retrieval\n"
            "- bm25_tokens: list of 5-10 essential search keyword tokens\n\n"
            f"User query: {raw_query}"
        )

        async def _call_gemini() -> str:
            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model="gemini-3.5-flash",
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                ),
            )
            return resp.text or ""

        # Enforce strict 1.5s timeout as specified in instructions
        raw_json = await asyncio.wait_for(_call_gemini(), timeout=1.5)
        parsed = json.loads(raw_json)

        return QueryPlan(
            raw_query=raw_query,
            primary_keyword_query=parsed.get("primary_keyword_query", rule_plan.primary_keyword_query),
            semantic_expansion_query=parsed.get("semantic_expansion_query", rule_plan.semantic_expansion_query),
            authority_query=rule_plan.authority_query,
            bm25_tokens=parsed.get("bm25_tokens", rule_plan.bm25_tokens),
            sub_queries=parsed.get("sub_queries", rule_plan.sub_queries)[:3],
            lexical_locks=rule_plan.lexical_locks,
            is_technical=rule_plan.is_technical,
        )
    except Exception:
        # Fall back instantly on timeout, import failure, or API quota error
        return rule_plan

