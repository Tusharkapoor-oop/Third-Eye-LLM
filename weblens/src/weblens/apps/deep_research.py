"""Advanced Deep Research Application.

Autonomous iterative research loop providing:
1. Multi-hop query planning and decomposition.
2. Evidence retrieval with claim-level citations to verbatim source spans.
3. Contradiction and conflict detection across independent domains.
4. Source diversity metrics (primary vs. secondary, distinct domains).
5. Grounded abstention when evidence is insufficient or contradictory.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlsplit

from ..service import WebLens
from ..urls import registrable_domain

PRIMARY_TLDS = {".gov", ".edu", ".mil"}
PRIMARY_INDICATORS = {"docs.", "documentation.", "github.com", "developer.", "api.", "rfc-editor.org"}


class AdvancedDeepResearch:
    """Multi-hop deep research engine with claim-level evidence spans and diversity analysis."""

    def __init__(self, service: WebLens):
        self.service = service

    async def execute_research(
        self,
        question: str,
        *,
        max_tokens: int = 4000,
        max_searches: int = 4,
        max_pages: int = 6,
    ) -> dict[str, Any]:
        """Execute autonomous research workflow and emit structured evidence dossier."""
        t0 = time.perf_counter()

        # Execute underlying deterministic research engine
        outcome = await self.service.research.research(
            question,
            max_tokens=max_tokens,
            max_searches=max_searches,
            max_pages=max_pages,
        )

        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        # Compute source diversity metrics
        domains: set[str] = set()
        primary_sources: list[str] = []
        secondary_sources: list[str] = []

        for f in outcome.findings:
            dom = registrable_domain(f.url)
            domains.add(dom)
            netloc = urlsplit(f.url).netloc.lower()
            if any(netloc.endswith(tld) for tld in PRIMARY_TLDS) or any(ind in netloc for ind in PRIMARY_INDICATORS):
                primary_sources.append(f.url)
            else:
                secondary_sources.append(f.url)

        primary_sources = list(dict.fromkeys(primary_sources))
        secondary_sources = list(dict.fromkeys(secondary_sources))
        total_sources = len(primary_sources) + len(secondary_sources)
        diversity_ratio = round(len(domains) / max(1, total_sources), 3)

        # Synthesize executive summary from top verified findings
        summary_sentences = [f.claim for f in outcome.findings[:3]]
        executive_summary = " ".join(summary_sentences) if summary_sentences else "No reliable evidence discovered."

        # Compile bibliography
        bibliography = [
            {"domain": dom, "sample_url": next(f.url for f in outcome.findings if registrable_domain(f.url) == dom)}
            for dom in sorted(domains)
        ]

        return {
            "status": outcome.status,
            "objective": question,
            "executive_summary": executive_summary,
            "methodology": {
                "subqueries_searched": outcome.searched,
                "pages_examined": len(outcome.findings),
                "elapsed_ms": elapsed_ms,
                "tokens_returned": outcome.tokens,
            },
            "key_findings": [
                {
                    "claim": f.claim,
                    "url": f.url,
                    "fetched_at": f.fetched_at,
                    "span": f.span,
                    "heading": f.heading,
                }
                for f in outcome.findings
            ],
            "contradictions": outcome.conflicts,
            "diversity_metrics": {
                "distinct_domains_count": len(domains),
                "distinct_domains": sorted(domains),
                "primary_sources_count": len(primary_sources),
                "secondary_sources_count": len(secondary_sources),
                "diversity_ratio": diversity_ratio,
            },
            "unresolved_gaps": outcome.gaps,
            "warnings": outcome.warnings,
            "bibliography": bibliography,
        }


# Export alias for compatibility
DeepResearchAgent = AdvancedDeepResearch
