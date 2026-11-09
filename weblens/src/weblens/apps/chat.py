"""Research Agent Chat Application.

Multi-turn conversational research session with:
1. Context-aware follow-up resolution.
2. Conversation history bounded within a strict token budget.
3. Strict prompt-injection scanning on retrieved web passages.
4. Verbatim citation preservation for all evidence claims.
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

from ..extract.passages import query_terms, tokenize
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
        # If the message is a short follow-up (for example, "what about
        # pricing?"), enrich it with the prior topic.
        words = user_message.strip().split()
        follow_up_markers = (
            "it",
            "they",
            "pricing",
            "cost",
            "features",
            "why",
        )
        if len(words) < 6 and any(marker in user_message.lower() for marker in follow_up_markers):
            return f"{last_user} {user_message}"
        return user_message

    def _prune_history(self) -> None:
        """Ensure total conversation history remains within the token limit."""
        while len(self.history) > 1:
            total_text = " ".join(t.get("user", "") + " " + t.get("answer", "") for t in self.history)
            if count_tokens(total_text) <= self.max_history_tokens:
                break
            self.history.pop(0)

    @staticmethod
    def _evidence_sentences(text: str, query: str, *, limit: int = 3) -> list[tuple[float, str, list[int]]]:
        """Select concise answer-bearing sentences while preserving local spans.

        Search/extraction passages are evidence, not answers. Returning whole
        passages caused chat to echo navigation, boilerplate and unrelated
        paragraphs. This selector only returns sentences with query coverage;
        every returned span is relative to the supplied passage text.
        """
        terms, phrases = query_terms(query)
        if not text.strip():
            return []
        boundaries = list(
            re.finditer(
                r"(?<=[.!?])(?:\s|\n)+(?=[A-Za-z0-9`#*])|\n{2,}|\n(?=\s*[-*+]\s+)",
                text,
            )
        )
        ranges: list[tuple[int, int]] = []
        start = 0
        for boundary in boundaries:
            ranges.append((start, boundary.start()))
            start = boundary.end()
        ranges.append((start, len(text)))

        candidates: list[tuple[float, str, list[int]]] = []
        for begin, end in ranges:
            raw = text[begin:end].strip()
            if not raw:
                continue
            left_trim = len(text[begin:end]) - len(text[begin:end].lstrip())
            absolute_begin = begin + left_trim
            heading = re.match(r"(?:#{1,6}[^\n]*\n\s*)+", raw)
            if heading:
                absolute_begin += heading.end()
                raw = raw[heading.end() :].lstrip()
                if not raw:
                    continue
            bullet = re.match(r"[-*+]\s+", raw)
            if bullet:
                absolute_begin += bullet.end()
                raw = raw[bullet.end() :].lstrip()
                if not raw:
                    continue
            absolute_end = absolute_begin + len(raw)
            if len(raw) < 25 or len(raw) > 500:
                continue
            low = raw.casefold()
            if low.startswith(("advertisement", "sign in", "subscribe", "cookie", "skip to")):
                continue
            tokens = set(tokenize(raw))
            covered = sum(1 for term in terms if term in tokens)
            if terms and covered == 0:
                continue
            score = covered / max(1, len(terms))
            if any(phrase.casefold() in low for phrase in phrases):
                score += 0.4
            if re.search(r"\b(?:is|are|means|refers to|provides|allows|returns|was|were)\b", low):
                score += 0.15
            if re.search(r"\bused\s+(?:as|for)\b", low):
                score += 0.4
            if re.search(r"\b(?:repl|webassembly|see also|copy path|sign in)\b", low):
                score -= 0.5
            if re.search(r"\b(?:asyncio\.run|await)\b", low):
                score -= 0.45
            if raw.endswith(":"):
                score -= 0.5
            score -= min(0.2, len(raw) / 3000)
            candidates.append((score, raw, [absolute_begin, absolute_end]))
        candidates.sort(key=lambda item: (-item[0], item[2][0]))
        selected: list[tuple[float, str, list[int]]] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = re.sub(r"\W+", " ", candidate[1].casefold()).strip()
            if key in seen:
                continue
            seen.add(key)
            selected.append(candidate)
            if len(selected) >= limit:
                break
        return selected

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
            passages = extract_out.get("ps") or extract_out.get("passages", [])
            if not passages and h.get("s"):
                passages = [{"p": h["s"], "s": [0, len(h["s"])], "source_type": "search_snippet"}]
            for p in passages:
                # MCP/service extraction uses compact ``x`` for passage text;
                # older app fixtures use ``p``. Accept both so live chat does
                # not silently discard every real extracted passage.
                text = p.get("p") or p.get("x", "")
                # Scan untrusted web text for prompt injection
                injection_hits = scan_injection(text)
                if injection_hits:
                    continue  # Quarantine dangerous passages

                base_span = p.get("s", [0, len(text)])
                if not isinstance(base_span, list) or len(base_span) != 2:
                    base_span = [0, len(text)]
                evidence = self._evidence_sentences(text, clean_msg, limit=2)
                for _, sentence, local_span in evidence:
                    citation_span = [int(base_span[0]) + local_span[0], int(base_span[0]) + local_span[1]]
                    citations.append(
                        {
                            "id": len(citations) + 1,
                            "url": url,
                            "title": h.get("t", ""),
                            "fetched_at": extract_out.get("at") or p.get("at"),
                            "span": citation_span,
                            "text": sentence,
                            "source_type": p.get("source_type", "extracted_page"),
                        }
                    )
                    answer_parts.append(sentence)
                    if len(citations) >= 2:
                        break
                if len(citations) >= 2:
                    break
            if len(citations) >= 2:
                break

        if not citations:
            answer = "I could not find reliable, uncompromised web evidence to answer your question."
            status = "no_reliable_result"
        else:
            answer = "Based on the retrieved evidence:\n" + "\n".join(
                f"- {part} [{index}]" for index, part in enumerate(answer_parts[:2], start=1)
            )
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
