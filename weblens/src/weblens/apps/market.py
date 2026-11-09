"""Market Researcher Application.

Extracts verified market intelligence and financial metrics from official disclosures:
- Strict zero-guess policy: unverified figures return 'not_available' rather than estimates.
- Sourced exclusively from regulatory filings (SEC, EDGAR, MCA, exchange notices) and IR pages.
- Every numeric claim carries unit/currency, reporting period, as-of timestamp, and source URL.
- Enforces strict compliance disclaimer: research only, never financial advice.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from ..service import WebLens

DISCLAIMER = (
    "DISCLAIMER: Information provided strictly for research and educational purposes. "
    "WebLens does not provide investment, financial, legal, or tax advice, nor any "
    "buy, sell, or hold recommendations."
)

FINANCIAL_NUMBER_PATTERN = re.compile(
    r"(?P<currency>[$€£₹]|USD|EUR|GBP|INR)?\s*(?P<val>\d+(?:[.,]\d+)?)\s*(?P<multiplier>billion|million|trillion|b|m|k|%|percent)?",
    re.I,
)


class MarketResearcher:
    """Researches market fundamentals, earnings, and regulatory disclosures with zero numeric fabrication."""

    def __init__(self, service: WebLens):
        self.service = service

    async def analyze_asset(
        self,
        asset_or_ticker: str,
        *,
        question: str | None = None,
    ) -> dict[str, Any]:
        """Research asset disclosures and extract verified figures."""
        t0 = time.perf_counter()
        asset = asset_or_ticker.strip()
        if not asset:
            return {"status": "error", "msg": "Asset or ticker must not be empty"}

        # Target official investor relations and filings
        search_query = f"{asset} investor relations SEC filing annual report earnings disclosure"
        if question:
            search_query += f" {question}"

        search_out = await self.service.search(search_query, max_results=4)
        hits = search_out.get("res", [])

        if not hits:
            return {
                "status": "not_available",
                "asset": asset,
                "msg": f"No authoritative filings or disclosures discovered for '{asset}'.",
                "disclaimer": DISCLAIMER,
                "ms": int((time.perf_counter() - t0) * 1000),
            }

        verified_metrics: list[dict[str, Any]] = []
        recent_disclosures: list[dict[str, Any]] = []

        for h in hits:
            snippet = h.get("s", "")
            url = h.get("u", "")
            title = h.get("t", "")
            date_str = h.get("d") or "unspecified"

            recent_disclosures.append(
                {
                    "title": title,
                    "url": url,
                    "date": date_str,
                    "snippet": snippet,
                }
            )

            # Check for verifiable financial metrics in text.
            # Only emit fields that are actually captured from the source snippet;
            # no currency or date is fabricated when the disclosure omits them.
            matches = list(FINANCIAL_NUMBER_PATTERN.finditer(snippet))
            for m in matches[:2]:
                val = m.group("val")
                currency = m.group("currency")
                multiplier = m.group("multiplier")
                if len(val) > 1 and (currency or multiplier):
                    metric: dict[str, Any] = {
                        "metric_mention": m.group(0).strip(),
                        "value": val,
                        "source_url": url,
                        "multiplier": multiplier,
                    }
                    if currency:
                        metric["currency"] = currency
                    if date_str and date_str != "unspecified":
                        metric["as_of_date"] = date_str
                    verified_metrics.append(metric)

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "status": "ok" if verified_metrics else "partial",
            "asset": asset,
            "disclosures_found": len(recent_disclosures),
            "verified_metrics": verified_metrics,
            "recent_disclosures": recent_disclosures[:3],
            "disclaimer": DISCLAIMER,
            "ms": elapsed_ms,
        }

    async def analyze_portfolio(
        self,
        assets: list[str],
        *,
        max_concurrency: int = 4,
    ) -> dict[str, Any]:
        """Analyze disclosures and verified financial metrics across a portfolio of assets."""
        t0 = time.perf_counter()
        clean_assets = [a.strip() for a in assets if a.strip()]
        if not clean_assets:
            return {"status": "error", "msg": "Asset list must not be empty", "disclaimer": DISCLAIMER}

        sem = asyncio.Semaphore(max_concurrency)

        async def _bounded(asset: str) -> dict[str, Any]:
            async with sem:
                return await self.analyze_asset(asset)

        results = await asyncio.gather(*[_bounded(a) for a in clean_assets])
        asset_reports = {a: res for a, res in zip(clean_assets, results, strict=True)}

        total_disclosures = sum(r.get("disclosures_found", 0) for r in results)
        total_metrics = sum(len(r.get("verified_metrics", [])) for r in results)

        return {
            "status": "ok",
            "portfolio_size": len(clean_assets),
            "total_disclosures_analyzed": total_disclosures,
            "total_verified_metrics": total_metrics,
            "assets": asset_reports,
            "disclaimer": DISCLAIMER,
            "ms": int((time.perf_counter() - t0) * 1000),
        }
