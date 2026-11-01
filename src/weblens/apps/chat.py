"""Research Agent Chat Application.

Multi-turn conversational research session with:
1. Context-aware follow-up resolution.
2. Conversation history bounded within a strict token budget.
3. Strict prompt-injection scanning on retrieved web passages.
4. Verbatim citation preservation for all evidence claims.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from ..security.injection import scan_injection
from ..service import WebLens
from ..tokens import count_tokens


class ResearchChatSession:
    """Manages an interactive, multi-turn, cited research conversation."""

    def __init__(self, service: WebLens, session_id: str | None = None, max_history_tokens: int = 4000):
        self.service = service
        self.session_id = session_id or str(uuid.uuid4())
        self.max_history_tokens = max_history_tokens
        self.history: list[dict[str, Any]] = []

    def _resolve_contextual_query(self, user_message: str) -> str:
        """Resolve pronouns or follow-up references using the previous conversation turn."""
        if not self.history:
            return user_message
        last_turn = self.history[-1]
        last_user = last_turn.get("user", "")
        # If message is a short follow-up (e.g. "what about pricing?", "how much does it cost?"), enrich with prior topic
        words = user_message.strip().split()
        if len(words) < 6 and any(p in user_message.lower() for p in ("it", "they", "pricing", "cost", "features", "why")):
            return f"{last_user} {user_message}"
        return user_message

    def _prune_history(self) -> None:
        """Ensure total conversation history remains within the token limit."""
        while len(self.history) > 1:
            total_text = " ".join(t.get("user", "") + " " + t.get("answer", "") for t in self.history)
            if count_tokens(total_text) <= self.max_history_tokens:
                break
            self.history.pop(0)

    async def send_message(self, user_message: str) -> dict[str, Any]:
        """Send a message to the conversational research agent and receive a cited response."""
        t0 = time.perf_counter()
        clean_msg = user_message.strip()
        if not clean_msg:
            return {"status": "error", "msg": "Message must not be empty"}

        # Resolve query context
        search_query = self._resolve_contextual_query(clean_msg)

        # Execute web search
        search_out = await self.service.search(search_query, max_results=3)
        hits = search_out.get("res", [])

        citations: list[dict[str, Any]] = []
        answer_parts: list[str] = []

        for h in hits[:2]:
            url = h.get("u")
            if not url:
                continue
            # Extract query-relevant passages
            extract_out = await self.service.extract(url, query=clean_msg, max_tokens=600)
            passages = extract_out.get("passages", [])
            for p in passages:
                text = p.get("p", "")
                # Scan untrusted web text for prompt injection
                injection_hits = scan_injection(text)
                if injection_hits:
                    continue  # Quarantine dangerous passages

                citations.append({
                    "url": url,
                    "title": h.get("t", ""),
                    "span": p.get("s", [0, len(text)]),
                    "text": text,
                })
                answer_parts.append(text)
                if len(citations) >= 3:
                    break
            if len(citations) >= 3:
                break

        if not citations:
            answer = "I could not find reliable, uncompromised web evidence to answer your question."
            status = "no_reliable_result"
        else:
            answer = " ".join(answer_parts[:3])
            status = "ok"

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        turn_record = {
            "user": clean_msg,
            "answer": answer,
            "citations": citations,
            "timestamp": time.time(),
        }
        self.history.append(turn_record)
        self._prune_history()

        return {
            "status": status,
            "session_id": self.session_id,
            "query_used": search_query,
            "answer": answer,
            "citations": citations,
            "turn_history_count": len(self.history),
            "ms": elapsed_ms,
        }

    def clear_history(self) -> None:
        """Reset the conversation memory."""
        self.history.clear()
