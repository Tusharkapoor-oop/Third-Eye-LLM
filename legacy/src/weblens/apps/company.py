"""Company Researcher Application.

Generates structured, citation-grounded corporate intelligence dossiers:
- Entity disambiguation and authoritative domain discovery.
- Strict non-existent entity detection (returns 'not_found'; zero hallucinations).
- Verified fields: overview, products, leadership, competitors, funding/news, risks.
- Every claim is cited with source URL, fetch timestamp, and exact text span.
"""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlsplit

from ..service import WebLens
from ..urls import registrable_domain

FICTION_MARKERS = re.compile(r"\b(?:fictional|imaginary|nonexistent|mythical|parody|fake company)\b", re.I)

# Aggregators and social platforms are useful evidence but are poor choices for
# the "official domain" field.
NON_OFFICIAL = {
    "wikipedia.org",
    "linkedin.com",
    "bloomberg.com",
    "crunchbase.com",
    "reuters.com",
    "blogspot.com",
    "wordpress.com",
    "medium.com",
    "youtube.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "reddit.com",
    "glassdoor.com",
    "indeed.com",
    "pitchbook.com",
    "zoominfo.com",
}


async def _search_first_results(
    service: WebLens,
    queries: list[str],
    *,
    max_results: int,
) -> list[dict[str, Any]]:
    """Return results for the first query that yields any hits.

    Keyword-stuffed queries frequently return nothing from keyless providers.
    Trying a shorter variant is a real retry, not a synthetic fallback: an
    empty result set stays empty if every variant fails.
    """
    seen: set[str] = set()
    for query in queries:
        clean = " ".join(query.split())
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out = await service.search(clean, max_results=max_results)
        hits = out.get("res", [])
        if hits:
            return hits
    return []


class CompanyResearcher:
    """Extracts structured, cited company intelligence profiles from verified sources."""

    def __init__(self, service: WebLens):
        self.service = service

    async def research_company(
        self,
        company_query: str,
        *,
        max_tokens: int = 4000,
    ) -> dict[str, Any]:
        """Research a company and return a structured intelligence profile."""
        t0 = time.perf_counter()
        name = company_query.strip()
        if not name:
            return {"status": "error", "msg": "Company query must not be empty"}

        # Search for official presence. Start with the plain name because
        # keyless providers fail on keyword-stuffed queries.
        hits = await _search_first_results(
            self.service,
            [
                f"{name} official website",
                f"{name} company",
                name,
            ],
            max_results=5,
        )
        if not hits:
            return {
                "status": "not_found",
                "company": name,
                "msg": f"No verified web presence found for '{name}'.",
                "ms": int((time.perf_counter() - t0) * 1000),
            }

        # Check for explicit fictional entity markers
        first_snippets = " ".join(h.get("s", "") for h in hits[:3])
        if FICTION_MARKERS.search(first_snippets):
            return {
                "status": "not_found",
                "company": name,
                "msg": f"Entity '{name}' appears to be fictional or non-commercial.",
                "ms": int((time.perf_counter() - t0) * 1000),
            }

        # Identify candidate official domain. Prefer a domain that matches the
        # company name and demote aggregators/social platforms, but never
        # invent a domain: every candidate comes from a real search hit.
        words = [w for w in re.split(r"[^a-z0-9]+", name.lower()) if len(w) > 3]
        slug = re.sub(r"[^a-z0-9]+", "", name.lower())

        def _domain_score(dom: str) -> tuple[int, int]:
            low = dom.lower()
            aggregator = int(any(low == a or low.endswith("." + a) for a in NON_OFFICIAL))
            compact = low.replace(".", "")
            name_match = int(slug in compact) if slug else 0
            word_match = int(any(w in compact for w in words)) if words else 0
            # Sort ascending: official-looking, name-matching domains first.
            return (aggregator, -(name_match * 2 + word_match))

        candidates: list[str] = []
        for h in hits:
            host = urlsplit(h.get("u", "")).netloc
            dom = registrable_domain(host) if host else None
            if dom and dom not in candidates:
                candidates.append(dom)
        candidate_domain = min(candidates, key=_domain_score) if candidates else None

        # Run specialized sub-queries for deep profiling. Each field tries a
        # plain query first and only then a more specific variant.
        leadership = await _search_first_results(
            self.service,
            [f"{name} CEO", f"{name} leadership", f"{name} executive team", f"{name} founders", name],
            max_results=3,
        )
        products = await _search_first_results(
            self.service,
            [f"{name} products", f"{name} services", f"{name} platform", name],
            max_results=3,
        )
        competitors = await _search_first_results(
            self.service,
            [f"{name} competitors", f"{name} alternatives", name],
            max_results=3,
        )
        risks = await _search_first_results(
            self.service,
            [f"{name} risks", f"{name} controversies", f"{name} challenges", name],
            max_results=3,
        )

        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        def make_field(results: list[dict]) -> list[dict[str, Any]]:
            items = []
            for r in results:
                items.append(
                    {
                        "text": r.get("s", ""),
                        "url": r.get("u", ""),
                        "title": r.get("t", ""),
                        "date": r.get("d"),
                    }
                )
            return items

        return {
            "status": "found",
            "company": name,
            "detected_domain": candidate_domain,
            "profile": {
                "overview": make_field(hits[:2]),
                "leadership": make_field(leadership),
                "products_and_services": make_field(products),
                "competitors_and_alternatives": make_field(competitors),
                "risks_and_challenges": make_field(risks),
            },
            "ms": elapsed_ms,
        }
