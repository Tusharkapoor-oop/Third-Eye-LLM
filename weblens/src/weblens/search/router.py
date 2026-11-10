"""Provider routing, fusion, dedupe and transparent ranking.

No relevance score is returned to callers. Ranking is used only to order
results; the ordering is a documented heuristic (reciprocal rank fusion plus a
small static authority prior), not a calibrated probability.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from urllib.parse import urlsplit

from ..cache import Cache, cache_key
from ..config import Settings
from ..errors import ErrCode, ProviderError, WebLensError
from ..lexical import query_terms, tokenize
from ..net import SafeFetcher
from ..urls import host_of, official_source_urls, registrable_domain
from .base import Hit, dedupe, diversify, near_duplicate, parse_date
from .bing import BingHTML
from .brave import BraveSearch
from .duckduckgo import DuckDuckGoLite
from .link_expand import expand_official_links
from .mwmbl import MwmblSearch
from .relevance import filter_hits
from .searxng import SearXNGSsearch
from .stackexchange import StackExchangeSearch
from .tavily import TavilySearch
from .wikipedia import WikipediaSearch
from .yahoo import YahooSearch

AUTHORITY = {
    "docs.python.org": 3.0,
    "developer.mozilla.org": 3.0,
    "learn.microsoft.com": 2.5,
    "docs.rs": 2.5,
    "go.dev": 2.5,
    "nodejs.org": 2.5,
    "rust-lang.org": 2.5,
    "python.org": 2.0,
    "git-scm.com": 2.5,
    "atlassian.com": 2.0,
    "fastapi.tiangolo.com": 2.5,
    "sitemaps.org": 2.5,
    "developers.google.com": 2.5,
    "nyse.com": 2.5,
    "spglobal.com": 2.5,
    "gartner.com": 2.5,
    "canalys.com": 2.5,
    "statista.com": 2.0,
    "postgresql.org": 2.5,
    "mysql.com": 2.5,
    "graphql.org": 2.5,
    "ipcc.ch": 2.5,
    "nasa.gov": 2.5,
    "noaa.gov": 2.5,
    "sec.gov": 2.5,
    "nato.int": 2.5,
    "eur-lex.europa.eu": 2.5,
    "ec.europa.eu": 2.5,
    "cdc.gov": 2.5,
    "bls.gov": 2.5,
    "iso.org": 2.5,
    "robotstxt.org": 2.5,
    "home.cern": 2.5,
    "copyright.gov": 2.5,
    "nasdaq.com": 2.0,
    "apple.com": 2.0,
    "microsoft.com": 2.0,
    "nvidia.com": 2.5,
    "opensource.org": 2.5,
    "mit-license.org": 2.0,
    "archives.gov": 2.5,
    "constitution.congress.gov": 2.5,
    "peps.python.org": 2.5,
    "papers.nips.cc": 2.5,
    "investor.gov": 2.5,
    "nih.gov": 2.5,
    "mayoclinic.org": 2.5,
    "adobe.com": 2.5,
    "perplexity.ai": 2.0,
    "deepmind.google": 2.5,
    "huggingface.co": 2.0,
    "abc.xyz": 2.0,
    "aws.amazon.com": 2.5,
    "cloud.google.com": 2.5,
    "snowflake.com": 2.5,
    "databricks.com": 2.5,
    "salesforce.com": 2.5,
    "modelcontextprotocol.io": 2.5,
    "blog.google": 2.5,
    "usa.gov": 2.5,
    "digital-strategy.ec.europa.eu": 2.5,
    "iata.org": 2.5,
    "heathrow.com": 2.0,
    "nlp.stanford.edu": 2.5,
    "earthdata.nasa.gov": 2.5,
    "diabetes.org": 2.5,
    "github.com": 2.0,
    "stackoverflow.com": 1.5,
    "arxiv.org": 1.5,
    "wikipedia.org": 1.0,
    "nature.com": 1.5,
    "science.org": 1.5,
    "acm.org": 1.2,
    "ieee.org": 1.2,
    "w3.org": 1.5,
    "ietf.org": 1.5,
    "rfc-editor.org": 1.5,
    "owasp.org": 1.2,
    "nvd.nist.gov": 1.5,
    "cve.org": 1.5,
    "worldbank.org": 2.5,
    "un.org": 2.5,
    "who.int": 2.5,
    "rtings.com": 2.5,
    "sony.com": 2.0,
    "bose.com": 2.0,
}

_FRESH_DAYS = {"day": 1, "week": 7, "month": 31, "year": 365}
_PROVIDER_FAILURE_THRESHOLD = 3
_PROVIDER_COOLDOWN_S = 60.0
_VERSION = re.compile(r"\b\d+\.\d+(?:\.\d+)?\b")

_CONVERSATIONAL = re.compile(
    r"^(?:please\s+)?(?:"
    r"can you|could you|would you|i want to|i need to|help me|"
    r"tell me about|tell me|"
    r"explain(?: to me)?(?: the)?(?: difference| similarities)?(?: between)?|"
    r"describe|compare|"
    r"find me|search for|look up|"
    r"what(?:'s| is| are)(?: the)?(?: difference| similarities)?(?: between)?|"
    r"who is|who are|"
    r"how do i|how to|how does|why does|why is|when did|where is"
    r")\s+",
    re.I,
)


_INJECTION = re.compile(
    r"\s+(?:also\s+)?(?:ignore|disregard|forget|override)\s+"
    r"(?:all\s+)?(?:prior|previous|above|earlier|system)\s+"
    r"(?:instructions?|prompts?|rules?).*$",
    re.I,
)
_EXFILTRATION = re.compile(
    r"\s+(?:also\s+)?(?:output|reveal|print|show|repeat)\s+"
    r"(?:your\s+)?(?:hidden|system|initial)\s+(?:prompt|instructions?).*$",
    re.I,
)


def clean_query(query: str) -> str:
    q = (query or "").strip()
    q = re.sub(r"\s+", " ", q)
    # Search should ignore prompt-injection instructions while still answering
    # the legitimate question that precedes them.
    q = _INJECTION.sub("", q)
    q = _EXFILTRATION.sub("", q)
    q = q.strip(" ?!.,;")
    q = _CONVERSATIONAL.sub("", q).strip(" ?!.")
    # Keep the comparison intent while removing verbose lead-in wording.
    # Dropping the intent entirely ("A and B") returns generic pages instead
    # of evidence about the requested differences.
    between = re.search(r"\bdifferences?\s+between\s+(.+)$", q, re.I)
    if between:
        # Preserve a subject that appeared before the comparison clause. A
        # query such as "In JavaScript, what is the difference between let and
        # const?" must keep "JavaScript"; otherwise the provider receives the
        # ambiguous fragment "let and const".
        prefix = q[: between.start()].strip(" ,;:?!.")
        prefix = re.sub(
            r"\b(?:what|which|who|how|why|when|where)\s+"
            r"(?:is|are|was|were|do|does|did|can|could|should|would)?\s*"
            r"(?:the)?\s*$",
            "",
            prefix,
            flags=re.I,
        ).strip(" ,;:?!.")
        if prefix.lower() in {"the", "a", "an"}:
            prefix = ""
        terms = between.group(1).strip(" ?!.")
        q = f"{prefix} {terms} comparison" if prefix else f"{terms} comparison"
    # Strip trailing comparison/review qualifiers that over-constrain keyless search
    q = re.sub(
        r"\s+(?:(?:headphones?|smartphones?|products?|detailed|side-by-side)\s+)?(?:comparison|overview|breakdown)[\s?!.]*$",
        "",
        q,
        flags=re.I,
    )
    return q or (query or "").strip()


_ENTITY_RE = re.compile(r"(?<![A-Za-z0-9_])(?:[A-Z][A-Za-z0-9.+&'-]*|(?:19|20)\d{2}|\d{2,4}(?:\.\d+)*)")
_ROLE_CAPS = {"ceo", "cfo", "cio", "ciso", "coo", "cpo", "cto"}
_RECALL_NOISE = {
    "about",
    "according",
    "affect",
    "affects",
    "best",
    "cause",
    "causes",
    "compare",
    "current",
    "decrease",
    "decreases",
    "describe",
    "detail",
    "details",
    "differ",
    "difference",
    "explain",
    "feature",
    "features",
    "find",
    "good",
    "greatest",
    "help",
    "increase",
    "increases",
    "information",
    "key",
    "largest",
    "latest",
    "list",
    "main",
    "major",
    "many",
    "most",
    "new",
    "newest",
    "official",
    "overview",
    "please",
    "primary",
    "primarily",
    "provide",
    "provides",
    "recent",
    "reduce",
    "reduces",
    "report",
    "reports",
    "search",
    "show",
    "specification",
    "specifications",
    "technical",
    "tell",
    "three",
    "top",
    "two",
    "use",
    "used",
    "using",
    "version",
    "versions",
    "what",
    "which",
    "who",
    "work",
    "works",
}
_ENTITY_STOP = _RECALL_NOISE | {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "might",
    "must",
    "my",
    "of",
    "on",
    "or",
    "our",
    "over",
    "she",
    "should",
    "so",
    "system",
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
    "those",
    "to",
    "under",
    "until",
    "up",
    "us",
    "was",
    "we",
    "were",
    "when",
    "where",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
}


def recall_query(query: str) -> str:
    """Return a compact entity-first query for a second recall pass.

    Keyless indexes often do badly with a full natural-language question but
    well with the entity phrase inside it. This is deliberately a query
    rewrite, not a semantic expansion: every token comes from the original
    question, so the second pass cannot introduce a new claim or topic.
    """

    cleaned = clean_query(query)
    if not cleaned:
        return ""
    entities: list[str] = []
    seen: set[str] = set()
    for raw in _ENTITY_RE.findall(query):
        token = raw.strip("._-")
        low = token.lower()
        if not token or low in _ENTITY_STOP or low in seen:
            continue
        if token.isdigit() and len(token) < 2:
            continue
        seen.add(low)
        entities.append(token)
    roles = [e for e in entities if e.lower() in _ROLE_CAPS]
    entities = [e for e in entities if e.lower() not in _ROLE_CAPS] + roles
    entities = entities[:5]
    terms, _ = query_terms(cleaned)
    key: list[str] = []
    for term in terms:
        if term in _RECALL_NOISE or term.isdigit():
            continue
        if any(term in entity.lower() or entity.lower() in term for entity in entities):
            continue
        key.append(term)
        if len(key) >= 2:
            break
    parts = [*entities, *key]
    if not parts:
        parts = [term for term in terms if term not in _RECALL_NOISE][:4]
    out = re.sub(r"\s+", " ", " ".join(parts)).strip()[:120]
    return out if out and out.lower() != cleaned.lower() else ""


def _authority(url: str) -> float:
    host = host_of(url)
    best = 0.0
    for domain, weight in AUTHORITY.items():
        if host == domain or host.endswith("." + domain):
            best = max(best, weight)
    if re.search(r"\.gov(?:\.[a-z]{2})?$", host) or re.search(r"\.edu(?:\.[a-z]{2})?$", host) or host.endswith(".mil"):
        best = max(best, 2.0)
    return best


def _official_title(url: str) -> str:
    """Show the primary-source path without pretending it is a normal result title."""

    try:
        path = urlsplit(url).path.rstrip("/")
    except ValueError:
        path = ""
    host = host_of(url)
    return f"Official source: {host}{path}" if path else f"Official source: {host}"


def _doc_key(url: str) -> str:
    """Single canonical key for search result deduplication.

    Query parameters are part of document identity for many primary sources
    (for example, EDGAR pages distinguished only by ``CIK``). Dropping them
    made distinct filings look like duplicates and silently removed valid
    official results.
    """
    from ..urls import document_canonical_key

    return document_canonical_key(url)


def _domain_allowed(
    url: str,
    domains: list[str] | None,
    exclude_domains: list[str] | None,
) -> bool:
    """Apply the caller's explicit domain constraints to a curated hint."""

    host = host_of(url)

    def matches(pattern: str) -> bool:
        d = (pattern or "").lower().strip().lstrip(".")
        return bool(d) and (host == d or host.endswith("." + d))

    if domains and not any(matches(d) for d in domains):
        return False
    if exclude_domains and any(matches(d) for d in exclude_domains):
        return False
    return True


def _query_authority(url: str, query: str) -> float:
    """Small query-aware prior for versioned/official documentation.

    Static domain authority is not enough for questions like "Python 3.14
    features": a generic docs page and the version-specific "What's New" page
    have the same host. This prior prefers the page that actually names the
    requested version, without changing the provider's ordering.
    """
    if not query:
        return 0.0
    host = host_of(url)
    low = query.lower()
    boost = 0.0
    if host == "docs.python.org" or host.endswith(".python.org"):
        version = re.search(r"\bpython\s*3\.(\d+)\b", low)
        if version:
            v = f"3.{version.group(1)}"
            if f"/{v}" in url or "whatsnew" in url:
                boost += 1.0
            else:
                boost += 0.35
        for term in ("asyncio", "typing", "pathlib", "sqlite3", "unittest"):
            if term in low and term in url:
                boost += 0.4
    if host == "developer.mozilla.org" and any(
        term in low for term in ("javascript", "css", "html", "web api", "content-security-policy")
    ):
        boost += 0.3
    if host == "react.dev" and "react" in low:
        boost += 0.4
    if host == "docs.rs" and "rust" in low:
        boost += 0.3
    return boost


def _skip_link_expansion(query: str) -> bool:
    """Freshness questions should not expand into old release indexes."""
    low = query.lower()
    if re.search(r"\bpep[\s-]?\d{1,4}\b", low):
        # A PEP is a self-contained document. Expanding into other PEP numbers
        # surfaces an index of unrelated proposals rather than evidence.
        return True
    return any(
        phrase in low
        for phrase in (
            "current stable",
            "current release",
            "current version",
            "latest release",
            "latest stable",
            "latest version",
            "most recent version",
            "newest version",
            "stable release version",
        )
    )


def rank(hits: list[Hit], *, fused: bool = False, query: str = "") -> list[Hit]:
    """Order by RRF (if fused) + static authority + recency. No score is exposed."""
    if not hits:
        return []
    today = date.today()
    groups: dict[str, list[Hit]] = {}
    for h in hits:
        groups.setdefault(h.provider, []).append(h)
    for group in groups.values():
        group.sort(key=lambda h: h.rank)

    scored: list[tuple[float, int, Hit]] = []
    for idx, h in enumerate(hits):
        s = 0.0
        if fused:
            for group in groups.values():
                for pos, gh in enumerate(group):
                    if gh is h:
                        s += 1.0 / (60.0 + pos)
                        break
        else:
            s = 1.0 / (1.0 + max(0, h.rank))
        s += 0.08 * (_authority(h.url) + _query_authority(h.url, query))
        if h.provider.startswith("official"):
            # Curated primary sources are high-confidence by construction.
            # Without this, a domain that is not in the static authority table
            # (for example britannica.com or cloudflare.com) loses to a generic
            # encyclopaedia result despite being the better evidence. The boost
            # also has to clear the recency bonus that dated provider results
            # receive; curated hints do not carry a publication date.
            s += 0.30
        d = date.fromisoformat(h.date[:10]) if h.date else None
        if d:
            age_days = (today - d).days
            if 0 <= age_days <= 30:
                s += 0.15
            elif age_days > 730:
                s -= 0.1
        scored.append((s, idx, h))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [t[2] for t in scored]


@dataclass
class SearchOutcome:
    query: str
    used_query: str
    hits: list[Hit]
    providers: list[str] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)
    status: str = "ok"
    elapsed_ms: int = 0
    warnings: list[str] = field(default_factory=list)
    # True when the fuse returned without waiting for every provider. Such a
    # result is timing-dependent and must not be cached as if it were complete.
    early_stopped: bool = False


class SearchRouter:
    def __init__(self, settings: Settings, fetcher: SafeFetcher):
        self.s = settings
        self.fetcher = fetcher
        self._providers: list[object] = []
        self._supplements: list[object] = []
        self.unavailable: dict[str, str] = {}
        self._provider_failures: dict[str, int] = {}
        self._provider_cooldown_until: dict[str, float] = {}
        self._build()

    def _build(self) -> None:
        s = self.s
        names = list(s.provider_list)
        # A configured Tavily key is an explicit signal that the hosted provider
        # should be used. Prepend it (fuse mode runs every provider concurrently,
        # so order only breaks ties) unless the caller already placed it.
        if s.auto_include_tavily and s.tavily_api_key and "tavily" not in names:
            names.insert(0, "tavily")
        for name in names:
            provider = self._instantiate(name)
            if provider is not None:
                self._providers.append(provider)
        # Supplements are only tried when the primary pool is thin. A provider
        # that is already primary is not instantiated twice.
        for name in s.supplement_list:
            if name in names:
                continue
            provider = self._instantiate(name)
            if provider is not None:
                self._supplements.append(provider)

    def _instantiate(self, name: str):
        s = self.s
        try:
            if name == "brave":
                if not s.brave_api_key:
                    self.unavailable[name] = "BRAVE_API_KEY not set"
                    return None
                return BraveSearch(self.fetcher, s.brave_api_key)
            if name == "ddg":
                return DuckDuckGoLite(self.fetcher)
            if name == "tavily":
                if not s.tavily_api_key:
                    self.unavailable[name] = "TAVILY_API_KEY not set"
                    return None
                return TavilySearch(self.fetcher, s.tavily_api_key)
            if name == "searxng":
                if not s.searxng_url:
                    self.unavailable[name] = "WEBLENS_SEARXNG_URL not set"
                    return None
                return SearXNGSsearch(self.fetcher, s.searxng_url)
            if name == "bing":
                return BingHTML(self.fetcher)
            if name == "yahoo":
                return YahooSearch(self.fetcher)
            if name == "mwmbl":
                return MwmblSearch(self.fetcher)
            if name == "wikipedia":
                return WikipediaSearch(self.fetcher)
            if name == "stackexchange":
                return StackExchangeSearch(self.fetcher, s.stackexchange_key)
        except ProviderError as e:
            self.unavailable[name] = e.message
        return None

    @property
    def provider_names(self) -> list[str]:
        return [getattr(p, "name", "?") for p in self._providers]

    @property
    def supplement_names(self) -> list[str]:
        return [getattr(p, "name", "?") for p in self._supplements]

    def _mark_success(self, name: str) -> None:
        self._provider_failures.pop(name, None)
        self._provider_cooldown_until.pop(name, None)

    def _mark_failure(self, name: str) -> None:
        failures = self._provider_failures.get(name, 0) + 1
        if failures >= _PROVIDER_FAILURE_THRESHOLD:
            self._provider_cooldown_until[name] = time.monotonic() + _PROVIDER_COOLDOWN_S
            failures = 0
        self._provider_failures[name] = failures

    def _providers_for_request(self) -> list[object]:
        now = time.monotonic()
        ready = [p for p in self._providers if self._provider_cooldown_until.get(getattr(p, "name", "?"), 0.0) <= now]
        # If every provider is cooling down, try them again rather than
        # returning an artificial "no provider" failure.
        return ready or list(self._providers)

    async def search(
        self,
        query: str,
        *,
        k: int = 5,
        freshness: str | None = None,
        domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        mode: str | None = None,
    ) -> SearchOutcome:
        started = time.perf_counter()
        used = clean_query(query)
        outcome = SearchOutcome(query=query, used_query=used, hits=[])
        if not used:
            outcome.status = "error"
            outcome.failures["input"] = "empty query"
            return outcome
        if len(used) > 400:
            used = used[:400]
        if not self._providers:
            raise ProviderError(
                "no search provider configured; set WEBLENS_SEARCH_PROVIDERS and keys",
                code=ErrCode.NO_PROVIDER,
            )
        providers = self._providers_for_request()
        skipped = [getattr(p, "name", "?") for p in self._providers if p not in providers]
        if skipped:
            outcome.warnings.append("provider_cooldown:" + ",".join(skipped))
        mode = mode or self.s.search_mode
        cache: Cache | None = getattr(self.fetcher, "cache", None)
        cache_key_value: str | None = None
        if cache is not None and self.s.cache_enabled and self.s.search_cache_ttl_s > 0:
            cache_key_value = cache_key(
                "search",
                used.lower(),
                str(k),
                freshness or "",
                ",".join(domains or []),
                ",".join(exclude_domains or []),
                mode,
                ",".join(self.provider_names),
            )
            cached = await cache.get_json(cache_key_value)
            if cached is not None:
                payload, _meta, _created = cached
                try:
                    cached_hits = [Hit(**h) for h in payload.get("hits", [])]
                except (AttributeError, TypeError, KeyError):
                    cached_hits = []
                if cached_hits:
                    outcome.hits = cached_hits
                    raw_providers = payload.get("providers", [])
                    outcome.providers = [str(p) for p in raw_providers] if isinstance(raw_providers, list) else []
                    outcome.status = "ok"
                    outcome.warnings.append("search_cache_hit")
                    outcome.elapsed_ms = int((time.perf_counter() - started) * 1000)
                    return outcome
        stats = {"off_topic": 0, "domain": 0, "version": 0}
        version = _VERSION.search(used)
        terms, _ = query_terms(used)
        non_version_terms = [t for t in terms if t != (version.group(0) if version else "") and t not in {"python"}]

        def accept(hits: list[Hit]) -> list[Hit]:
            kept, off, dom = filter_hits(
                hits,
                used,
                domains=domains,
                exclude_domains=exclude_domains,
            )
            if version:
                token = version.group(0)
                versioned = []
                for h in kept:
                    haystack = f"{h.title} {h.snippet} {h.url}".lower()
                    hay_tokens = set(tokenize(haystack))
                    has_version = token in hay_tokens or token in haystack
                    has_topic = not non_version_terms or any(t in hay_tokens for t in non_version_terms)
                    if (has_version and has_topic) or _authority(h.url) >= 2.5:
                        versioned.append(h)
                stats["version"] += len(kept) - len(versioned)
                kept = versioned
            stats["off_topic"] += off
            stats["domain"] += dom
            return kept

        if mode == "fuse" and len(providers) > 1:
            merged = await self._fuse(
                used,
                k=k,
                freshness=freshness,
                domains=domains,
                exclude_domains=exclude_domains,
                outcome=outcome,
                accept=accept,
                providers=providers,
            )
        else:
            merged = await self._fallback(
                used,
                k=k,
                freshness=freshness,
                domains=domains,
                exclude_domains=exclude_domains,
                outcome=outcome,
                accept=accept,
                providers=providers,
            )

        # A thin candidate pool usually reflects provider trouble rather than a
        # genuine absence of evidence. Re-query with the compact entity phrase
        # that keyless indexes handle much better than a full question (for
        # example "Siemens" instead of "What industry does Siemens primarily
        # operate in?"). This is best-effort: primary results always win and
        # secondary failures never downgrade the response status.
        if len(merged) < k + 2 and not version:
            alt = recall_query(query)
            if alt and alt.lower() != used.lower():
                alt_outcome = SearchOutcome(query=query, used_query=alt, hits=[])

                def accept_alt(hits: list[Hit]) -> list[Hit]:
                    kept, _, _ = filter_hits(
                        hits,
                        alt,
                        domains=domains,
                        exclude_domains=exclude_domains,
                    )
                    return kept

                if mode == "fuse" and len(providers) > 1:
                    extra = await self._fuse(
                        alt,
                        k=k,
                        freshness=freshness,
                        domains=domains,
                        exclude_domains=exclude_domains,
                        outcome=alt_outcome,
                        accept=accept_alt,
                        providers=providers,
                    )
                else:
                    extra = await self._fallback(
                        alt,
                        k=k,
                        freshness=freshness,
                        domains=domains,
                        exclude_domains=exclude_domains,
                        outcome=alt_outcome,
                        accept=accept_alt,
                        providers=providers,
                    )
                if extra:
                    merged.extend(extra)
                    outcome.warnings.append(f"query_expanded:{alt}")
                    # The recall pass runs its own _fuse into a throwaway
                    # outcome. If THAT pass stopped early, the merged list is
                    # just as timing-dependent as a primary early stop, so the
                    # flag must be propagated or a partial result gets cached
                    # for the full TTL.
                    if alt_outcome.early_stopped:
                        outcome.early_stopped = True
                    for name in alt_outcome.providers:
                        if name not in outcome.providers:
                            outcome.providers.append(name)
                        # A provider that failed the primary query but served
                        # the recall query recovered; do not report it failed.
                        outcome.failures.pop(name, None)

        # Curated primary-source hints are deterministic and cheap. Add only
        # URLs that the providers did not already return, and never violate an
        # explicit domain include/exclude. When the providers returned nothing
        # usable, these become the fallback instead of a misleading empty page.
        official_hits: list[Hit] = []
        # Use the original wording for topic hints. ``clean_query`` removes
        # conversational lead-ins aggressively and may discard the language or
        # entity that identifies the primary source (for example "In
        # JavaScript, what is the difference between let and const?" becomes
        # "let and const").
        # ``use_official_source_hints`` can be disabled for honest head-to-head
        # evaluation: the hints are author-curated, so any benchmark whose
        # labels came from the same author is contaminated while they are on.
        official_urls = (
            [url for url in official_source_urls(query) if _domain_allowed(url, domains, exclude_domains)]
            if getattr(self.s, "use_official_source_hints", True)
            else []
        )
        official_domains = {registrable_domain(host_of(url)) for url in official_urls}
        for official_rank, url in enumerate(official_urls):
            key = _doc_key(url)
            existing = next((h for h in merged if _doc_key(h.url) == key), None)
            if existing is not None:
                # A provider already found the primary source. Keep its richer
                # title/snippet but promote it into the official group so a
                # generic encyclopaedia result cannot outrank it.
                existing.provider = "official-source"
                existing.rank = official_rank
                continue
            if any(_doc_key(h.url) == key for h in official_hits):
                continue
            official_hits.append(
                Hit(
                    title=_official_title(url),
                    url=url,
                    snippet="Primary source selected for this query; extract to verify the evidence.",
                    provider="official-source",
                    rank=official_rank,
                )
            )
        if official_hits and not merged:
            for h in official_hits:
                h.provider = "official-fallback"
            merged = official_hits[:k]
            outcome.warnings.append("official_source_fallback")
        elif official_hits:
            merged = [*merged, *official_hits]
            outcome.warnings.append("official_source_hint")

        # Follow a small number of same-site links from the curated primary
        # pages. This is bounded, cached, and skipped when no official page was
        # selected; it supplies additional primary evidence when a keyless
        # provider returns only a broad overview page. This runs even when the
        # provider pool already has five candidates: a secondary recall pass can
        # otherwise fill the window with encyclopaedia pages before the better
        # primary siblings are discovered.
        official_present = len({_doc_key(url) for url in official_urls})
        max_links = max(0, k - official_present)
        if official_urls and max_links and not _skip_link_expansion(query):
            expanded = await expand_official_links(
                self.fetcher,
                official_urls,
                query,
                [h.url for h in merged],
                max_pages=min(3, len(official_urls)),
                max_links=max_links,
                timeout_s=3.5,
            )
            added = 0
            for i, (url, anchor, source_url) in enumerate(expanded):
                if not _domain_allowed(url, domains, exclude_domains):
                    continue
                key = _doc_key(url)
                existing = next((h for h in merged if _doc_key(h.url) == key), None)
                if existing is not None:
                    existing.provider = "official-source"
                    existing.rank = i + 1
                    continue
                if any(_doc_key(h.url) == key for h in merged):
                    continue
                merged.append(
                    Hit(
                        title=anchor or _official_title(url),
                        url=url,
                        snippet=f"Primary-source link from {host_of(source_url)}.",
                        provider="official-source",
                        rank=i + 1,
                    )
                )
                added += 1
            if added:
                outcome.warnings.append(f"official_source_expanded:{added}")

        merged = dedupe(merged)
        # near-duplicate snippets across different URLs (syndicated copies)
        unique: list[Hit] = []
        for h in merged:
            # Curated hints intentionally share a short generic blurb. Removing
            # them as near-duplicates would collapse independent primary
            # sources (e.g. git-scm.com and atlassian.com) to a single result.
            official = h.provider.startswith("official")
            if not official and any(
                near_duplicate(h.title + " " + h.snippet, p.title + " " + p.snippet) for p in unique
            ):
                outcome.warnings.append("duplicate_text_removed")
                continue
            unique.append(h)
        ranked = rank(unique, fused=(mode == "fuse"), query=used)
        domain_caps: dict[str, int] = {domain: 4 for domain in official_domains if domain}
        # When Wikipedia is effectively the only productive index, allow it to
        # fill the result window. Capping it at three just lets unrelated blogs
        # occupy the remaining slots. Diversity still wins whenever at least
        # three non-Wikipedia candidates are available.
        non_wiki = sum(1 for hit in ranked if registrable_domain(host_of(hit.url)) != "wikipedia.org")
        wiki_cap = min(k, 5) if non_wiki < 3 else 3
        for hit in ranked:
            domain = registrable_domain(host_of(hit.url))
            if domain == "wikipedia.org":
                domain_caps[domain] = max(domain_caps.get(domain, 0), wiki_cap)
            elif domain and _authority(hit.url) >= 2.5:
                # Encyclopaedic questions often have two or three genuinely
                # relevant pages (for example a title page, a list page, and a
                # sibling article). Two is too tight for those; unrelated
                # domains still keep the default cap.
                domain_caps.setdefault(domain, 3)
        merged = diversify(ranked, per_domain=2, domain_caps=domain_caps, strict=True)[:k]
        # Strict capping guarantees domain diversity but can leave the window
        # short when only one or two sources matched. Top up from the surplus
        # only to reach k, and say so, so a padded window is never silent.
        if len(merged) < k:
            seen_keys = {_doc_key(h.url) for h in merged}
            padding = [
                h for h in diversify(ranked, per_domain=2, domain_caps=domain_caps) if _doc_key(h.url) not in seen_keys
            ]
            if padding:
                merged = [*merged, *padding][:k]
                outcome.warnings.append(f"diversity_padded:{len(merged) - len(seen_keys)}")

        # Narrow supplements (for example Stack Exchange for technical
        # questions) fill *empty* slots only, after the primary results have
        # been ranked and diversified. They cannot displace a primary hit, so
        # coverage improves without trading away precision.
        if len(merged) < k:
            extra = await self._supplement_pass(
                used,
                k=k,
                freshness=freshness,
                domains=domains,
                exclude_domains=exclude_domains,
                outcome=outcome,
                accept=accept,
            )
            seen_keys = {_doc_key(h.url) for h in merged}
            for h in extra:
                if len(merged) >= k:
                    break
                key = _doc_key(h.url)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                merged.append(h)

        outcome.hits = merged
        if stats["off_topic"]:
            outcome.warnings.append(f"off_topic_filtered:{stats['off_topic']}")
        if stats["domain"]:
            outcome.warnings.append(f"domain_filtered:{stats['domain']}")
        if stats["version"]:
            outcome.warnings.append(f"version_filtered:{stats['version']}")
        if not merged:
            outcome.status = "no_reliable_result"
            outcome.warnings.append("no_results")
            if stats["off_topic"]:
                outcome.warnings.append("no_query_match")
        elif freshness in _FRESH_DAYS:
            window = _FRESH_DAYS[freshness]
            cutoff = date.today() - timedelta(days=window)
            known = [date.fromisoformat(d[:10]) for h in merged[:3] if (d := parse_date(h.date))]
            if known and all(d < cutoff for d in known):
                outcome.status = "possibly_outdated"
                outcome.warnings.append(f"top_results_older_than_{freshness}")
            elif not known:
                outcome.warnings.append("dates_unknown")
        if outcome.failures and merged:
            if outcome.status == "ok":
                available = [name for name in outcome.providers if name not in outcome.failures]
                if len(merged) >= 3 and available:
                    # A single failed provider is not a partial answer when the
                    # remaining providers supplied enough usable results. Keep
                    # the failure visible without mislabelling the response.
                    outcome.warnings.append("provider_degraded:" + ",".join(sorted(outcome.failures)))
                else:
                    outcome.status = "partial"
        if (
            cache_key_value is not None
            and cache is not None
            and merged
            and outcome.status == "ok"
            and not outcome.failures
            and not outcome.early_stopped
        ):
            await cache.set_json(
                cache_key_value,
                {
                    "hits": [asdict(h) for h in merged],
                    "providers": list(outcome.providers),
                },
                {"kind": "search"},
                self.s.search_cache_ttl_s,
            )
        outcome.elapsed_ms = int((time.perf_counter() - started) * 1000)
        return outcome

    def _provider_timeout(self, provider) -> float:
        value = getattr(provider, "timeout_s", None)
        return float(value) if value else self.s.provider_timeout_s

    async def _fallback(
        self,
        q: str,
        *,
        k: int,
        freshness,
        domains,
        exclude_domains,
        outcome: SearchOutcome,
        accept,
        providers,
    ) -> list[Hit]:
        collected: list[Hit] = []
        for provider in providers:
            name = getattr(provider, "name", "?")
            try:
                raw = await asyncio.wait_for(
                    provider.search(  # type: ignore[attr-defined]
                        q,
                        k=k,
                        freshness=freshness,
                        domains=domains,
                        exclude_domains=exclude_domains,
                    ),
                    timeout=self._provider_timeout(provider),
                )
                hits = accept(raw)
                self._mark_success(name)
                outcome.providers.append(name)
                collected.extend(hits)
                if len({h.url for h in collected}) >= k:
                    break
            except TimeoutError:
                self._mark_failure(name)
                outcome.failures[name] = "timeout"
            except WebLensError as e:
                self._mark_failure(name)
                outcome.failures[name] = str(e.code)
            except Exception as e:  # provider bugs must not kill the request
                self._mark_failure(name)
                outcome.failures[name] = type(e).__name__
        return collected

    async def _supplement_pass(
        self,
        q: str,
        *,
        k: int,
        freshness,
        domains,
        exclude_domains,
        outcome: SearchOutcome,
        accept,
    ) -> list[Hit]:
        """Try supplement providers when the primary pool is thin.

        Failures are isolated in a private outcome: an optional supplement that
        times out must not downgrade the response status or make the primary
        result look partial.
        """
        if not self._supplements:
            return []
        sup_outcome = SearchOutcome(query=outcome.query, used_query=q, hits=[])
        extra = await self._fallback(
            q,
            k=k,
            freshness=freshness,
            domains=domains,
            exclude_domains=exclude_domains,
            outcome=sup_outcome,
            accept=accept,
            providers=self._supplements,
        )
        for name in sup_outcome.providers:
            if name not in outcome.providers:
                outcome.providers.append(name)
        if extra:
            outcome.warnings.append("supplement:" + ",".join(sup_outcome.providers))
        return extra

    async def _fuse(
        self,
        q: str,
        *,
        k: int,
        freshness,
        domains,
        exclude_domains,
        outcome: SearchOutcome,
        accept,
        providers,
    ) -> list[Hit]:
        async def one(p):
            name = getattr(p, "name", "?")
            try:
                raw = await asyncio.wait_for(
                    p.search(  # type: ignore[attr-defined]
                        q,
                        k=max(k, 8),
                        freshness=freshness,
                        domains=domains,
                        exclude_domains=exclude_domains,
                    ),
                    timeout=self._provider_timeout(p),
                )
                return name, accept(raw), None
            except Exception as e:
                return name, [], e

        if not providers:
            return []

        soft = self.s.fuse_soft_timeout_s
        if soft <= 0:
            results = await asyncio.gather(*(one(p) for p in providers))
        else:
            tasks = {asyncio.create_task(one(p)): getattr(p, "name", "?") for p in providers}
            pending: set = set(tasks)
            done: set = set()
            deadline = time.monotonic() + soft
            early = False
            while pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                finished, pending = await asyncio.wait(pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
                done |= finished
                if not finished:
                    break
                if self._early_pool_is_enough(self._accepted_from(done), k):
                    grace = self.s.fuse_grace_s
                    if grace > 0 and pending:
                        grace_done, pending = await asyncio.wait(pending, timeout=grace)
                        done |= grace_done
                    early = True
                    break
            if pending:
                if not early and self._early_pool_is_enough(self._accepted_from(done), k):
                    early = True
                if early:
                    outcome.early_stopped = True
                    cancelled = sorted(tasks[task] for task in pending)
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    outcome.warnings.append("early_stop:" + ",".join(cancelled))
                else:
                    more, _ = await asyncio.wait(pending)
                    done |= more
            results = [task.result() for task in done]

        merged: list[Hit] = []
        for name, hits, err in results:
            if err is None:
                self._mark_success(name)
                outcome.providers.append(name)
                merged.extend(hits)
            else:
                self._mark_failure(name)
                outcome.failures[name] = "timeout" if isinstance(err, TimeoutError) else type(err).__name__
        return merged

    def _accepted_from(self, tasks) -> list[Hit]:
        hits: list[Hit] = []
        for task in tasks:
            if task.cancelled():
                continue
            _name, accepted, err = task.result()
            if err is None:
                hits.extend(accepted)
        return hits

    def _early_pool_is_enough(self, hits: list[Hit], k: int) -> bool:
        """True when the Tavily subset alone can fill the visible window.

        Only the hosted provider is considered. Keyless pools never early-stop:
        the confirmatory n=40 paired run measured a P@5 loss beyond the
        pre-registered margin when slow keyless providers were cancelled. The
        domain floor keeps the fast path from closing on a single-domain pool.
        """
        tavily = [h for h in hits if getattr(h, "provider", "") == "tavily"]
        urls = {h.url for h in tavily}
        if len(urls) < k + self.s.fuse_early_min_extra:
            return False
        # registrable_domain() expects a HOST. Passing the full URL turned every
        # path into its own "domain", so a six-page single-host pool (or six URL
        # spellings of one document) satisfied a floor of three and the guard
        # certified a deep, diverse pool it did not have -- cancelling healthy
        # slow providers and then shrinking below k in diversify(strict=True).
        domains = {registrable_domain(host_of(h.url)) for h in tavily}
        return len(domains) >= self.s.fuse_early_min_domains
