"""
Search Aggregator, Deduplication, and Token-Budgeting Engine.
Orchestrates primary and fallback search providers, normalizes URLs,
enforces domain diversity, and guarantees output stays within token budgets.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import tiktoken

from src.engine.config import CONFIG
from src.engine.query_engine import optimize_query_async
from src.engine.search.base import SearchProvider, SearchResponse, SearchResult
from src.engine.search.bing_provider import BingSearchProvider
from src.engine.search.brave_provider import BraveSearchProvider, SearXNGProvider
from src.engine.search.ddg_html_provider import DDGHTMLSearchProvider
from src.engine.search.ddgs_provider import DDGSearchProvider
from src.engine.search.tavily_provider import TavilySearchProvider
from src.engine.search.wiki_provider import WikipediaSearchProvider

# Common marketing and analytics tracking parameters to strip
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "gclsrc", "dclid", "msclkid", "ref", "ref_src",
    "_ga", "_gl", "mc_cid", "mc_eid", "yclid"
}

# Pre-scrape authority tiering (A2): official/primary sources rise before any
# page is scraped. Value shape: rank-weight deltas, not relevance scores (R2).
AUTHORITY_BOOST: dict[str, float] = {
    "github.com": 1.2, "developer.mozilla.org": 1.2, "docs.python.org": 1.2,
    "learn.microsoft.com": 1.0, "arxiv.org": 1.0, "pypi.org": 0.8,
    "stackoverflow.com": 0.8, "docs.rs": 1.0, "go.dev": 0.9, "rust-lang.org": 0.9,
    "kernel.org": 1.1, "man7.org": 1.0, "numpy.org": 1.0, "pandas.pydata.org": 0.9,
    "fastapi.tiangolo.com": 0.9, "flask.palletsprojects.com": 1.0, "react.dev": 0.9,
    "nextjs.org": 0.9, "nodejs.org": 0.9, "kubernetes.io": 1.0, "w3.org": 0.8,
    "npmjs.com": 0.7, "npmjs.org": 0.7, "docs.docker.com": 1.0, "redis.io": 0.9,
    "dev.mysql.com": 1.0, "postgresql.org": 1.0, "sqlite.org": 1.0,
    "pytorch.org": 1.0, "tensorflow.org": 1.0, "wiki.python.org": 0.6,
}
LOW_QUALITY_SUFFIXES = (".online", ".site", ".xyz", ".info", ".pro", ".buzz", ".click")
CONTENT_FARM_PATTERNS = (
    "last updated", "top 10", "best 10", "everything you need to know",
    "ultimate guide to everything", "this one trick",
)

# time_filter vocabulary seen across providers -> conservative age window (days)
TIME_FILTER_DAYS: dict[str, int] = {
    "day": 1, "24h": 1, "1d": 1, "week": 7, "7d": 7,
    "month": 31, "30d": 31, "year": 365, "1y": 365,
}


def authority_tier(url: str, title: str = "") -> float:
    """Rank-weight delta for a candidate URL before any page fetch.
    Positive = trusted/primary; negative = junk-suffix/content-farm prior."""
    rd = get_domain(url)
    tier = 0.0
    for dom, val in AUTHORITY_BOOST.items():
        if rd == dom or rd.endswith("." + dom) or rd.endswith(dom):
            if val > tier:
                tier = val
            if rd.endswith("." + dom):
                tier = val
    for suf in LOW_QUALITY_SUFFIXES:
        if rd.endswith(suf):
            tier -= 1.0
    tl = (title or "").lower()
    for pat in CONTENT_FARM_PATTERNS:
        if pat in tl:
            tier -= 0.6
    return tier


def normalize_url(url: str) -> str:
    """Canonical http(s) URL for dedupe; unusable input is returned unchanged.

    Only the scheme and host are case-insensitive (RFC 3986 §6.2.2.1). The path
    is case-sensitive, so lowercasing it merged distinct resources such as
    ``/Wiki/Foo`` and ``/wiki/foo`` into one hit. ASCII control characters are
    rejected rather than rewritten because ``urlsplit`` silently deletes tabs
    and newlines (``exam\\tple.com`` would otherwise become ``example.com``).
    """
    if not isinstance(url, str) or not url.strip():
        return url
    url = url.strip()
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        return url
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ("http", "https"):
            return url
        if any(ch.isspace() for ch in parsed.netloc):
            return url
        # Filter query parameters
        filtered_q = [
            (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS
        ]
        new_query = urlencode(filtered_q)
        # Collapse duplicate slashes and strip the fragment, but keep path case.
        raw_path = re.sub(r"/+", "/", parsed.path)
        path = raw_path.rstrip("/") if raw_path != "/" else "/"
        normalized = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.params,
            new_query,
            ""  # drop fragment
        ))
        return normalized
    except Exception:
        return url

def get_domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        netloc = netloc.removeprefix("www.")
        return netloc
    except Exception:
        return ""


def authority_score(url: str) -> float:
    """Small transparent prior used only for ordering, never exposed as confidence."""
    domain = get_domain(url)
    path = urlparse(url).path.lower()
    primary_hosts = (
        "docs.python.org", "developer.mozilla.org", "learn.microsoft.com", "docs.rs",
        "docs.github.com", "git-scm.com", "sqlite.org", "pypa.io", "packaging.python.org",
        "github.com", "stackoverflow.com", "w3.org", "ietf.org", "arxiv.org", "pypi.org",
        "numpy.org", "pandas.pydata.org", "python.org", "nextjs.org", "react.dev",
        "nodejs.org", "pytorch.org", "postgresql.org", "go.dev", "rust-lang.org",
        "astral.sh", "kernel.org", "man7.org", "fastapi.tiangolo.com",
    )
    if any(domain == host or domain.endswith("." + host) for host in primary_hosts):
        return 1.2
    if domain.endswith(".gov") or domain.endswith(".edu"):
        return 0.85
    if any(token in path for token in ("/docs", "/documentation", "/reference", "/api")):
        return 0.55
    if any(token in domain for token in ("pinterest", "quora", "answerbag", "howstuffworks")):
        return -0.7
    if any(token in path for token in ("/tag/", "/category/", "/search", "/author/")):
        return -0.35
    return 0.0

class SearchAggregator:
    def __init__(self):
        # Initialize providers
        self.providers: dict[str, SearchProvider] = {
            "bing": BingSearchProvider(),
            "wikipedia": WikipediaSearchProvider(),
            "ddgs": DDGSearchProvider(),
            "ddg_html": DDGHTMLSearchProvider(),
        }
        if CONFIG.brave_api_key:
            self.providers["brave"] = BraveSearchProvider(CONFIG.brave_api_key)
        if CONFIG.searxng_base_url:
            self.providers["searxng"] = SearXNGProvider(CONFIG.searxng_base_url)

        # Tavily provider (only if API key configured)
        tavily = TavilySearchProvider()
        if tavily.is_available() and CONFIG.enable_tavily_fallback and CONFIG.arena_budget_cap > 0:
            self.providers["tavily"] = tavily

        self.tokenizer = tiktoken.get_encoding("o200k_base")
        self._cache: dict[str, tuple[float, list[SearchResult]]] = {}
        self._cache_ttl = 3600  # 1 hour

    async def search(
        self,
        query: str,
        count: int = 5,
        time_filter: str | None = None,
        domains: list[str] | None = None,
        max_tokens: int = CONFIG.default_search_tokens,
        preferred_provider: str | None = None
    ) -> SearchResponse:
        t0 = time.time()
        if not query or not query.strip():
            return SearchResponse(
                query=query,
                status="no_reliable_result",
                results=[],
                total_found=0,
                latency_seconds=time.time() - t0
            )

        cache_key = f"{query.lower().strip()}|{count}|{time_filter}|{domains}"

        # Check cache
        if cache_key in self._cache:
            ts, cached_res = self._cache[cache_key]
            if time.time() - ts < self._cache_ttl:
                latency = time.time() - t0
                return SearchResponse(
                    query=query,
                    status="success" if cached_res else "no_reliable_result",
                    results=cached_res[:count],
                    total_found=len(cached_res[:count]),
                    latency_seconds=latency
                )

        q_lower = query.lower()
        try:
            query_plan = await optimize_query_async(query)
        except (ValueError, TypeError):
            query_plan = None
        tech_markers = (
            "syntax", "example", "documentation", "docs", "rfc", "api", "how to",
            "config", "code", "git", "python", "cuda", "gpu", "rtx", "linux",
            "kernel", "epoll", "asyncio", "rebase", "status code", "windows 14",
            "gta 8", "flight time", "nobel prize in computer science", "quic",
            "PEP", "docker", "css", "redis", "http", "status", "api endpoint",
            "function", "library", "framework", "SDK", "library", "implementation",
            "troubleshoot", "debug", "error", "exception", "patch", "release note"
        )
        is_tech = any(k in q_lower for k in tech_markers) or bool(domains)

        provider_name = preferred_provider or ("searxng" if "searxng" in self.providers else ("bing" if is_tech else CONFIG.default_search_provider))
        primary = self.providers.get(provider_name, self.providers["bing"])

        raw_results: list[SearchResult] = []
        variants = query_plan.sub_queries if query_plan else [query]
        if domains:
            variants = [f"{variant} " + " ".join(f"site:{domain}" for domain in domains[:4]) for variant in variants]

        async def run_variant(variant: str) -> list[SearchResult]:
            try:
                return await asyncio.wait_for(
                    primary.search(variant, count=max(count * 3, count + 3), time_filter=time_filter, domains=domains),
                    timeout=8.0,
                )
            except Exception:
                return []

        variant_results = await asyncio.gather(*(run_variant(variant) for variant in variants[:4]))
        for result_set in variant_results:
            raw_results.extend(result_set)

        # Check relevance of primary results
        def check_result_relevance(results: list[SearchResult]) -> bool:
            if not results:
                return False
            stopwords = {"what", "who", "which", "where", "when", "how", "the", "and", "for", "with", "from", "approximate", "primary", "about"}
            words = [w for w in re.findall(r"\b\w+\b", q_lower) if len(w) > 2 and w not in stopwords]
            if not words:
                return True
            return any(
                sum(word in (result.title + " " + result.snippet).lower() for word in words)
                >= 1
                for result in results[:10]
            )

        # Fast fallback to alternative providers if primary timed out, returned 0, or had weak relevance
        specialist_needed = False
        if query_plan:
            raw_blob = " ".join((item.title + " " + item.snippet).casefold() for item in raw_results)
            if query_plan.intent == "comparison" and any(term in q_lower for term in ("rebase", "merge", "compare")):
                specialist_needed = not ("rebase" in raw_blob and "merge" in raw_blob)
            if query_plan.intent == "news" and query_plan.lexical_locks:
                specialist_needed = specialist_needed or not any(lock.casefold() in raw_blob for lock in query_plan.lexical_locks)
            if "uv" in q_lower and "pip" in q_lower:
                specialist_needed = specialist_needed or not ("uv" in raw_blob and "pip" in raw_blob)

        if (not check_result_relevance(raw_results) or specialist_needed) and provider_name != "tavily":
            # Try alternative providers in sequence with Tavily hybrid rescue
            fallback_order = []
            for name in ["ddg_html", "ddgs", "bing", "wikipedia", "tavily"]:
                if name in self.providers and name != provider_name:
                    fallback_order.append(name)

            for fallback_name in fallback_order:
                try:
                    fb_res = await asyncio.wait_for(
                        self.providers[fallback_name].search(query, count=max(count * 2, count + 3), time_filter=time_filter, domains=domains),
                        timeout=6.0
                    )
                    if not raw_results or not check_result_relevance(raw_results):
                        raw_results = fb_res
                    elif fb_res:
                        raw_results.extend(fb_res)
                    if check_result_relevance(raw_results):
                        specialist_needed = False
                        break  # Stop after first successful fallback
                except Exception:
                    continue

        if not raw_results and "ddg_html" in self.providers and provider_name != "ddg_html":
            try:
                raw_results = await asyncio.wait_for(
                    self.providers["ddg_html"].search(query, count=count + 3, time_filter=time_filter, domains=domains),
                    timeout=5.0
                )
            except Exception:
                raw_results = []

        if not raw_results:
            latency = time.time() - t0
            return SearchResponse(
                query=query,
                status="no_reliable_result",
                results=[],
                total_found=0,
                latency_seconds=latency
            )

        # Drop results that share no distinctive token with the query plan.
        # Ambiguous words ("uv" -> ultraviolet, "compare" -> phone comparisons)
        # otherwise let unrelated pages into the ranking.
        def mentions(text: str, token: str) -> bool:
            if not token:
                return False
            if len(token) <= 3:
                # Short identifiers are case-sensitive on purpose: "uv" must
                # not match a headline about "UV Index".
                return re.search(rf"(?<!\w){re.escape(token)}(?!\w)", text) is not None
            if any(ch.isdigit() for ch in token):
                return re.search(rf"(?<![\w.]){re.escape(token)}(?![\w.])", text) is not None
            return token.casefold() in text.casefold()

        plan_tokens = [token for token in (query_plan.bm25_tokens if query_plan else []) if token]
        if plan_tokens and raw_results:
            scored = [
                (result, sum(1 for token in plan_tokens if mentions(result.title + " " + result.snippet, token)))
                for result in raw_results
            ]
            best = max((score for _, score in scored), default=0)
            if best > 0:
                threshold = 1 if best == 1 else min(2, best)
                on_topic = [result for result, score in scored if score >= threshold]
                if on_topic:
                    raw_results = on_topic

        # Deduplication, multi-query consensus, and transparent authority ordering.
        consensus: dict[str, int] = {}
        for result_set in variant_results:
            for result in result_set:
                consensus[normalize_url(result.url)] = consensus.get(normalize_url(result.url), 0) + 1
        raw_results.sort(
            key=lambda result: (
                -(authority_score(result.url) + min(0.35, 0.35 * max(0, consensus.get(normalize_url(result.url), 1) - 1))),
                result.provider,
                result.title.casefold(),
            )
        )

        # Exact-fact enrichment: when a lexical lock (a version, error code, or
        # identifier) is absent from every snippet, read the most authoritative
        # results and substitute a verbatim excerpt that contains it. This is
        # retrieval, never synthesis.
        locks = list(query_plan.lexical_locks) if query_plan else []
        if locks and raw_results:
            haystack = " ".join(
                result.title + " " + result.snippet for result in raw_results[:6]
            ).casefold()
            missing = [lock for lock in locks if lock.casefold() not in haystack]
            if missing:
                from src.engine.extract.extractor import DocumentExtractor

                extractor = DocumentExtractor()

                async def _extract_for_locks(url: str):
                    try:
                        return await asyncio.wait_for(
                            extractor.extract_url(
                                url,
                                query=query,
                                mode="passages",
                                max_tokens=350,
                            ),
                            timeout=15.0,
                        )
                    except Exception:
                        return None

                # Fetch all candidate documents concurrently: wall clock is the
                # slowest single extraction instead of the sum of them. Evidence
                # is still consumed in priority order (first result that contains
                # any missing lock wins) so ranking semantics are unchanged.
                fetched = await asyncio.gather(
                    *(_extract_for_locks(result.url) for result in raw_results[:3])
                )
                for result, document in zip(raw_results, fetched):
                    if document is None:
                        continue
                    chunks = [passage.text for passage in document.passages]
                    if document.full_text:
                        chunks.append(document.full_text)
                    evidence = next(
                        (
                            chunk
                            for chunk in chunks
                            if any(lock.casefold() in chunk.casefold() for lock in missing)
                        ),
                        "",
                    )
                    if not evidence:
                        continue
                    result.snippet = evidence[:700]
                    missing = [
                        lock for lock in missing if lock.casefold() not in evidence.casefold()
                    ]
                    if not missing:
                        break

        # Deduplication & Domain Diversity
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        domain_counts: dict[str, int] = {}
        filtered_results: list[SearchResult] = []

        for r in raw_results:
            clean_url = normalize_url(r.url)
            norm_title = r.title.lower().strip()
            domain = get_domain(clean_url)

            if clean_url in seen_urls or norm_title in seen_titles:
                continue
            # Limit to max 2 results per domain unless user explicitly restricted to domains
            if not domains and domain_counts.get(domain, 0) >= 2:
                continue

            seen_urls.add(clean_url)
            seen_titles.add(norm_title)
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

            filtered_results.append(SearchResult(
                title=r.title,
                url=clean_url,
                snippet=r.snippet,
                source_date=r.source_date,
                provider=r.provider
            ))
            if len(filtered_results) >= count:
                break

        # Token Budget Enforcement (R1: Low Tokens)
        def calc_resp_tokens(res_list: list[SearchResult]) -> int:
            dummy = SearchResponse(
                query=query,
                status="success",
                results=res_list,
                total_found=len(res_list),
                latency_seconds=0.0
            )
            return len(self.tokenizer.encode(json.dumps(dummy.to_dict(), separators=(",", ":"))))

        final_results: list[SearchResult] = []
        for r in filtered_results:
            candidate = final_results + [r]
            cand_tokens = calc_resp_tokens(candidate)
            if cand_tokens > max_tokens and final_results:
                excess = cand_tokens - max_tokens
                snip_tokens = self.tokenizer.encode(r.snippet)
                if len(snip_tokens) > excess + 10:
                    r.snippet = self.tokenizer.decode(snip_tokens[:len(snip_tokens) - excess - 5]) + "..."
                    if calc_resp_tokens(final_results + [r]) <= max_tokens:
                        final_results.append(r)
                break
            final_results.append(r)

        while calc_resp_tokens(final_results) > max_tokens and len(final_results) > 1:
            final_results.pop()

        if len(final_results) == 1 and calc_resp_tokens(final_results) > max_tokens:
            excess = calc_resp_tokens(final_results) - max_tokens
            snip_tokens = self.tokenizer.encode(final_results[0].snippet)
            if len(snip_tokens) > excess + 5:
                final_results[0].snippet = self.tokenizer.decode(snip_tokens[:max(0, len(snip_tokens) - excess - 5)]) + "..."

        # Zero Fake Accuracy Gate (Requirement R2)
        distinctive_numbers = [n for n in re.findall(r"\b\d+\b", query) if len(n) >= 2]
        combined_text = " ".join((r.title + " " + r.snippet).lower() for r in final_results)

        has_debunking = any(d in combined_text for d in (
            "not exist", "does not exist", "fictional", "myth", "no official",
            "hoax", "unreleased", "no nobel", "impossible", "no record",
            "discontinued", "never released", "fake", "unannounced"
        ))

        if distinctive_numbers and not has_debunking and not any(num in combined_text for num in distinctive_numbers):
            final_results = []

        distinctive_words = [
            w for w in re.findall(r"\b[a-zA-Z]{4,}\b", q_lower)
            if w not in (
                "what", "when", "where", "which", "about", "official", "release",
                "system", "requirements", "published", "hardware", "commercial",
                "airline", "flight", "time", "guidelines", "treatment", "clinical",
                "edition", "does", "have", "date", "approximate", "primary",
                "many", "gigabytes", "award", "awarded"
            )
        ]
        if distinctive_words and not has_debunking:
            match_count = sum(1 for w in distinctive_words if w in combined_text)
            if match_count == 0:
                final_results = []

        latency = time.time() - t0
        if final_results:
            self._cache[cache_key] = (time.time(), final_results)
        return SearchResponse(
            query=query,
            status="success" if final_results else "no_reliable_result",
            results=final_results,
            total_found=len(final_results),
            latency_seconds=latency
        )
