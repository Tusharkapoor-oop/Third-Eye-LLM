"""Stack Exchange adapter (official API, keyless best effort).

A supplement for programming and technical-support questions, where the
general web indexes often return off-topic "how does X differ" pages and
official documentation is not always indexed. It queries the public Stack
Exchange API (Stack Overflow) and returns question pages.

The keyless quota is small (300 requests/day per IP), so the provider only
runs for queries that look technical. Set ``WEBLENS_STACKEXCHANGE_KEY`` to a
Stack Apps key to raise the quota. It is deliberately last in the default
chain: it is a narrow, high-precision supplement, not a general web index.
"""

from __future__ import annotations

import html
import re
import time
from datetime import UTC, datetime
from urllib.parse import urlencode

from ..errors import ErrCode, ProviderError
from ..lexical import query_terms
from ..net import SafeFetcher
from .base import Hit, make_hit

_API = "https://api.stackexchange.com/2.3/search/advanced"

# A query only goes to Stack Exchange when it names a programming/technical
# concept. This keeps the small keyless quota for the queries that benefit.
_TECH = frozenset(
    """
    python asyncio javascript typescript nodejs node react vue angular svelte
    java kotlin swift golang rust cpp csharp sql postgres postgresql mysql
    sqlite redis mongodb docker kubernetes k8s git github gitlab api http
    https json regex bash shell linux ubuntu windows error exception traceback
    function class async await coroutine promise pip npm yarn django flask
    fastapi spring rails laravel php ruby html css tailwind webpack vite
    pytest unittest debug compiler database server endpoint request response
    cookie session oauth jwt import module package dependency framework library
    sdk cli terminal command zsh powershell vscode ide bug crash hang timeout
    memory leak concurrency thread process mutex lock queue cache tcp udp dns
    ssl tls encryption hash algorithm array list dict object string integer
    float boolean loop recursion iterator generator decorator lambda typing
    pydantic numpy pandas pytorch tensorflow sklearn matplotlib jupyter notebook
    csv xml yaml markdown gitignore rebase merge branch commit ci cd deployment
    aws azure gcp cloudflare serverless
    """.split()  # noqa: SIM905
)

_TAGS = {
    "python": "python",
    "asyncio": "python",
    "javascript": "javascript",
    "js": "javascript",
    "typescript": "typescript",
    "node": "node.js",
    "nodejs": "node.js",
    "react": "reactjs",
    "vue": "vue.js",
    "angular": "angular",
    "java": "java",
    "kotlin": "kotlin",
    "swift": "swift",
    "golang": "go",
    "rust": "rust",
    "cpp": "c++",
    "csharp": "c#",
    "sql": "sql",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "mysql": "mysql",
    "sqlite": "sqlite",
    "redis": "redis",
    "mongodb": "mongodb",
    "docker": "docker",
    "kubernetes": "kubernetes",
    "k8s": "kubernetes",
    "git": "git",
    "bash": "bash",
    "shell": "bash",
    "linux": "linux",
    "php": "php",
    "ruby": "ruby",
}

_STOP = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "between",
    "by",
    "can",
    "differ",
    "difference",
    "do",
    "does",
    "example",
    "examples",
    "explain",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "should",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "to",
    "use",
    "used",
    "using",
    "versus",
    "vs",
    "was",
    "ways",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "work",
    "works",
}

_IDENT = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[._][A-Za-z0-9]+)+")
_WORD = re.compile(r"[a-z0-9][a-z0-9_.+#-]*")


def _tokens(query: str) -> list[str]:
    return _WORD.findall(query.lower())


def looks_technical(query: str) -> bool:
    """True when the query names a language, tool, error, or code identifier."""
    tokens = _tokens(query)
    if any(t in _TECH for t in tokens):
        return True
    # Dotted/camel identifiers are strong signals, but a bare version such as
    # "3.11" is not. Require at least one letter.
    return any(_IDENT.fullmatch(t) and re.search(r"[a-z]", t) for t in tokens)


def _title_term(query: str) -> str:
    """Pick a distinctive identifier for the API's exact-title match."""
    for match in _IDENT.finditer(query):
        return match.group(0)
    terms, _ = query_terms(query)
    for term in terms:
        if "." in term or "_" in term:
            return term
    return ""


def _free_text(query: str) -> str:
    terms, _ = query_terms(query)
    kept = [t for t in terms if t not in _STOP and not t.replace(".", "").isdigit()]
    return " ".join(kept[:6])


def _tag(query: str) -> str:
    for token in _tokens(query):
        if token in _TAGS:
            return _TAGS[token]
    return ""


def _fromdate(freshness: str | None) -> int | None:
    seconds = {"day": 86_400, "week": 604_800, "month": 2_592_000, "year": 31_536_000}.get(freshness or "")
    return int(time.time()) - seconds if seconds else None


class StackExchangeSearch:
    name = "stackexchange"
    timeout_s = 4.0

    def __init__(self, fetcher: SafeFetcher, key: str | None = None):
        self.fetcher = fetcher
        self.key = key

    async def search(
        self,
        query: str,
        *,
        k: int = 5,
        freshness: str | None = None,
        domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[Hit]:
        if domains and not any(d.endswith(("stackoverflow.com", "stackexchange.com")) for d in domains):
            return []
        if not looks_technical(query):
            return []

        base: dict[str, str] = {
            "order": "desc",
            "sort": "relevance",
            "site": "stackoverflow",
            "pagesize": str(min(10, max(1, k))),
            "filter": "default",
        }
        tag = _tag(query)
        if tag:
            base["tagged"] = tag
        fromdate = _fromdate(freshness)
        if fromdate:
            base["fromdate"] = str(fromdate)
        if self.key:
            base["key"] = self.key

        title = _title_term(query)
        items = await self._query(base, {"title": title} if title else {"q": _free_text(query)})
        if not items and title:
            items = await self._query(base, {"q": _free_text(query)})

        hits: list[Hit] = []
        for i, item in enumerate(items):
            if len(hits) >= k:
                break
            title_text = html.unescape(item.get("title", "") or "")
            link = item.get("link", "") or ""
            score = item.get("score", 0)
            answers = item.get("answer_count", 0)
            tags = ", ".join(item.get("tags", []) or [])
            snippet = f"Score {score} · {answers} answer{'s' if answers != 1 else ''}"
            if tags:
                snippet += f" · tags: {tags}"
            date_hint = ""
            if item.get("last_activity_date"):
                try:
                    stamp = int(item["last_activity_date"])
                    date_hint = datetime.fromtimestamp(stamp, tz=UTC).date().isoformat()
                except (ValueError, OSError, OverflowError):
                    date_hint = ""
            hit = make_hit(title_text, link, snippet, provider=self.name, rank=i, date_hint=date_hint)
            if hit:
                hits.append(hit)
        return hits

    async def _query(self, base: dict[str, str], extra: dict[str, str]) -> list[dict]:
        url = f"{_API}?{urlencode({**base, **extra})}"
        resp = await self.fetcher.fetch(
            url,
            headers={"Accept": "application/json"},
            cache_ttl=1800,
            max_bytes=1_000_000,
        )
        try:
            data = resp.json()
        except ValueError as e:
            raise ProviderError("stackexchange returned invalid JSON", code=ErrCode.PROVIDER) from e
        if data.get("error_id"):
            message = data.get("error_message", "unknown")
            raise ProviderError(f"stackexchange API error: {message}", code=ErrCode.PROVIDER)
        if data.get("quota_remaining") == 0:
            raise ProviderError("stackexchange quota exhausted", code=ErrCode.PROVIDER)
        items = data.get("items")
        return items if isinstance(items, list) else []
