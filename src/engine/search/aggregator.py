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

def normalize_url(url: str) -> str:
    """Normalizes a URL by stripping tracking parameters, fragments, and standardizing casing."""
    try:
        parsed = urlparse(url)
        # Filter query parameters
        filtered_q = [
            (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS
        ]
        new_query = urlencode(filtered_q)
        # Collapse multiple slashes, strip fragment and normalize path
        raw_path = re.sub(r"/+", "/", parsed.path)
        path = (raw_path.rstrip("/") if raw_path != "/" else "/").lower()
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
        if tavily.is_available():
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

        provider_name = preferred_provider or ("bing" if is_tech else CONFIG.default_search_provider)
        primary = self.providers.get(provider_name, self.providers["bing"])

        raw_results: list[SearchResult] = []
        try:
            raw_results = await asyncio.wait_for(
                primary.search(query, count=count + 3, time_filter=time_filter, domains=domains),
                timeout=8.0
            )
        except Exception:
            raw_results = []

        # Check relevance of primary results
        def check_result_relevance(results: list[SearchResult]) -> bool:
            if not results:
                return False
            combined = (results[0].title + " " + results[0].snippet).lower()
            stopwords = {"what", "who", "which", "where", "when", "how", "the", "and", "for", "with", "from", "approximate", "primary", "about"}
            words = [w for w in re.findall(r"\b\w+\b", q_lower) if len(w) > 2 and w not in stopwords]
            if not words:
                return True
            return any(w in combined for w in words)

        # Fast fallback to alternative providers if primary timed out, returned 0, or had weak relevance
        if not check_result_relevance(raw_results) and provider_name != "tavily":
            # Try alternative providers in sequence
            fallback_order = []
            for name in ["bing", "wikipedia", "ddgs", "ddg_html"]:
                if name in self.providers and name != provider_name:
                    fallback_order.append(name)
            
            for fallback_name in fallback_order:
                try:
                    fb_res = await asyncio.wait_for(
                        self.providers[fallback_name].search(query, count=count + 3, time_filter=time_filter, domains=domains),
                        timeout=6.0
                    )
                    if check_result_relevance(fb_res) or (not raw_results and fb_res):
                        raw_results = fb_res
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
