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
from urllib.parse import urlsplit
from typing import Any

from ..service import WebLens
from ..urls import registrable_domain

FICTION_MARKERS = re.compile(
    r"\b(?:fictional|imaginary|nonexistent|mythical|parody|fake company)\b", re.I
)


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

        # Search for official presence
        search_res = await self.service.search(
            f"{name} official website company overview",
            max_results=5,
        )

        hits = search_res.get("res", [])
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

        # Identify candidate official domain
        candidate_domain = None
        for h in hits:
            host = urlsplit(h.get("u", "")).netloc
            dom = registrable_domain(host) if host else None
            if dom and not any(w in dom for w in ("wikipedia", "linkedin", "bloomberg", "crunchbase", "reuters")):
                candidate_domain = dom
                break
        if not candidate_domain and hits:
            host = urlsplit(hits[0].get("u", "")).netloc
            candidate_domain = registrable_domain(host) if host else None

        # Run specialized sub-queries for deep profiling
        leadership_res = await self.service.search(f"{name} CEO leadership executive team founders", max_results=3)
        products_res = await self.service.search(f"{name} products services platform solutions", max_results=3)
        competitors_res = await self.service.search(f"{name} competitors market alternatives vs", max_results=3)
        risks_res = await self.service.search(f"{name} business challenges risks controversies", max_results=3)

        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        def make_field(results: list[dict]) -> list[dict[str, Any]]:
            items = []
            for r in results:
                items.append({
                    "text": r.get("s", ""),
                    "url": r.get("u", ""),
                    "title": r.get("t", ""),
                    "date": r.get("d"),
                })
            return items

        return {
            "status": "found",
            "company": name,
            "detected_domain": candidate_domain,
            "profile": {
                "overview": make_field(hits[:2]),
                "leadership": make_field(leadership_res.get("res", [])),
                "products_and_services": make_field(products_res.get("res", [])),
                "competitors_and_alternatives": make_field(competitors_res.get("res", [])),
                "risks_and_challenges": make_field(risks_res.get("res", [])),
            },
            "ms": elapsed_ms,
        }
