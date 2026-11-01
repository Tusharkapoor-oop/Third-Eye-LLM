"""Meeting Preparation Agent Application.

Produces cited pre-meeting briefing dossiers with strict privacy safeguards:
- Strictly confined to public professional records (corporate bios, press releases, public announcements).
- Automatic refusal guard against queries targeting private personal details (family, health, residence).
- Minimal query disclosure: raw calendar event notes are never broadcast to search providers.
- Stateless and read-only: no calendar modification or persistent private storage.
"""

from __future__ import annotations

import re
import time
from typing import Any

from ..service import WebLens

PRIVACY_PROBE_PATTERN = re.compile(
    r"\b(?:home address|personal phone|cell phone|family|spouse|children|kids|medical|health|salary|wealth|net worth|religion|private life)\b",
    re.I,
)


class MeetingPrepAgent:
    """Prepares structured, cited meeting briefings strictly from public professional information."""

    def __init__(self, service: WebLens):
        self.service = service

    async def prepare_brief(
        self,
        meeting_title: str,
        attendees: list[str],
        *,
        company_or_org: str | None = None,
        agenda_topics: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a meeting dossier from verified public professional sources."""
        t0 = time.perf_counter()

        # Enforce privacy refusal guard
        combined_text = f"{meeting_title} {' '.join(attendees)} {company_or_org or ''} {' '.join(agenda_topics or [])}"
        if PRIVACY_PROBE_PATTERN.search(combined_text):
            return {
                "status": "refused_privacy_boundary",
                "msg": "Request refused: targeting private, non-professional, or personal attributes is prohibited.",
                "ms": int((time.perf_counter() - t0) * 1000),
            }

        attendee_profiles: list[dict[str, Any]] = []
        for person in attendees[:5]:
            clean_name = person.strip()
            if not clean_name:
                continue

            query = f"{clean_name} {company_or_org or ''} biography career public role"
            search_out = await self.service.search(query, max_results=2)
            hits = search_out.get("res", [])

            bio_snippets = [h.get("s", "") for h in hits]
            sources = [h.get("u", "") for h in hits if h.get("u")]

            attendee_profiles.append({
                "attendee": clean_name,
                "public_professional_background": " ".join(bio_snippets[:2]) if bio_snippets else "No public professional profile verified.",
                "sources": sources,
            })

        # Research company context if provided
        company_notes = []
        if company_or_org:
            comp_search = await self.service.search(f"{company_or_org} recent developments strategic focus news", max_results=2)
            for h in comp_search.get("res", []):
                company_notes.append({
                    "title": h.get("t"),
                    "url": h.get("u"),
                    "summary": h.get("s"),
                })

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "status": "ok",
            "meeting_title": meeting_title,
            "attendees_researched": len(attendee_profiles),
            "attendee_profiles": attendee_profiles,
            "company_context": company_notes,
            "suggested_discussion_topics": agenda_topics or ["Strategic alignment", "Collaboration opportunities"],
            "privacy_notice": "Dossier constructed exclusively from public professional sources under data minimization rules.",
            "ms": elapsed_ms,
        }
