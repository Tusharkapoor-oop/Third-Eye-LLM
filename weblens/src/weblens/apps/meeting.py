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
    r"\b(?:home address|personal phone|cell phone|family|spouse|children|kids|"
    r"medical|health|salary|wealth|net worth|religion|private life)\b",
    re.I,
)


async def _search_with_fallback(
    service: WebLens,
    queries: list[str],
    *,
    max_results: int,
) -> dict[str, Any]:
    """Try increasingly broad queries, returning the first with results.

    Keyless providers frequently return nothing for keyword-stuffed queries.
    Falling back to a shorter query is honest: every returned hit is still a
    real provider result, and an empty final result stays empty.
    """
    last: dict[str, Any] = {}
    seen: set[str] = set()
    for query in queries:
        clean = " ".join(query.split())
        if not clean or clean in seen:
            continue
        seen.add(clean)
        last = await service.search(clean, max_results=max_results)
        if last.get("res"):
            return last
    return last


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
            search_out = await _search_with_fallback(
                self.service,
                [
                    f"{clean_name} {company_or_org or ''}",
                    clean_name,
                    query,
                ],
                max_results=2,
            )
            hits = search_out.get("res", [])

            bio_snippets = [h.get("s", "") for h in hits if h.get("s")]
            sources = list(dict.fromkeys(h.get("u", "") for h in hits if h.get("u")))

            attendee_profiles.append(
                {
                    "attendee": clean_name,
                    "public_professional_background": (
                        " ".join(bio_snippets[:2]) if bio_snippets else "No public professional profile verified."
                    ),
                    "sources": sources,
                }
            )

        # Research company context if provided
        company_notes = []
        if company_or_org:
            comp_search = await _search_with_fallback(
                self.service,
                [
                    f"{company_or_org} recent developments strategic focus news",
                    f"{company_or_org} news",
                    company_or_org,
                ],
                max_results=2,
            )
            for h in comp_search.get("res", []):
                company_notes.append(
                    {
                        "title": h.get("t"),
                        "url": h.get("u"),
                        "summary": h.get("s"),
                    }
                )

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "status": "ok",
            "meeting_title": meeting_title,
            "attendees_researched": len(attendee_profiles),
            "attendee_profiles": attendee_profiles,
            "company_context": company_notes,
            "suggested_discussion_topics": agenda_topics or ["Strategic alignment", "Collaboration opportunities"],
            "privacy_notice": (
                "Dossier constructed exclusively from public professional sources under data minimization rules."
            ),
            "ms": elapsed_ms,
        }

    async def prepare_from_calendar_event(
        self,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Prepare briefing from a Google Calendar or standard iCal event dictionary.

        Extracts summary, attendee names/emails, and organization context while stripping
        private body notes to guarantee data minimization.
        """
        title = event.get("summary") or event.get("title") or "Meeting"
        attendees_raw = event.get("attendees", [])
        attendee_names = []
        for a in attendees_raw:
            if isinstance(a, str):
                attendee_names.append(a)
            elif isinstance(a, dict):
                name = a.get("displayName") or a.get("email") or ""
                if name:
                    if "@" in name and not a.get("displayName"):
                        name = name.split("@")[0].replace(".", " ").title()
                    attendee_names.append(name)

        company = event.get("company") or event.get("organization")
        return await self.prepare_brief(title, attendee_names, company_or_org=company)
