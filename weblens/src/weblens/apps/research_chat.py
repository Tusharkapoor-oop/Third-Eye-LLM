"""Persistent Research Agent Chat with session state and citation preservation.

Distinct from the lightweight single-turn answer engine, this module manages:
- Multi-turn research sessions
- SQLite-backed conversation and evidence persistence
- Job status tracking (IDLE, PLANNING, SEARCHING, EXTRACTING, SYNTHESIZING)
- Follow-up query decomposition and context retention
- Full session export to Markdown and JSON
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from ..service import WebLens
from .deep_research import DeepResearchAgent


@dataclass
class ResearchChatMessage:
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    citations: list[dict[str, Any]]
    subqueries: list[str]
    tokens_used: int
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class ResearchSessionExport:
    session_id: str
    topic: str
    created_at: str
    updated_at: str
    messages: list[dict[str, Any]]
    total_tokens: int
    total_sources: int


class PersistentResearchChat:
    """Manages a multi-turn, stateful research conversation."""

    def __init__(
        self,
        service: WebLens,
        db_path: Path | str | None = None,
        session_id: str | None = None,
    ) -> None:
        self.service = service
        self.session_id = session_id or str(uuid.uuid4())
        if db_path:
            self.db_path = Path(db_path)
        else:
            # Honour the configured cache directory instead of hardcoding
            # ~/.weblens, so deployments (and tests) control where state lives.
            cache_dir = getattr(getattr(service, "s", None), "cache_dir", None)
            base = Path(cache_dir) if cache_dir else Path("~/.weblens").expanduser()
            self.db_path = base / "research_sessions.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.researcher = DeepResearchAgent(service=service)
        self.job_status: Literal[
            "IDLE",
            "PLANNING",
            "SEARCHING",
            "EXTRACTING",
            "SYNTHESIZING",
            "COMPLETED",
            "FAILED",
        ] = "IDLE"
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    topic TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    citations_json TEXT,
                    subqueries_json TEXT,
                    tokens_used INTEGER,
                    created_at TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                )
                """
            )
            now = datetime.now(UTC).isoformat()
            conn.execute(
                "INSERT OR IGNORE INTO sessions (id, topic, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (self.session_id, "Untitled Research Session", now, now),
            )

    def set_topic(self, topic: str) -> None:
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE sessions SET topic = ?, updated_at = ? WHERE id = ?",
                (topic, now, self.session_id),
            )

    async def send_query(
        self,
        query: str,
        progress_cb: Callable[[str, str], None] | None = None,
    ) -> ResearchChatMessage:
        """Send a user research query or follow-up question."""
        user_msg_id = str(uuid.uuid4())
        user_msg = ResearchChatMessage(
            id=user_msg_id,
            role="user",
            content=query,
            citations=[],
            subqueries=[],
            tokens_used=len(query) // 4,
        )
        await asyncio.to_thread(self._save_message, user_msg)

        if progress_cb:
            progress_cb("PLANNING", f"Formulating research plan for: {query}")
        self.job_status = "PLANNING"

        history = await asyncio.to_thread(self.get_messages)
        prior_context = "\n".join(f"{m.role.upper()}: {m.content}" for m in history[-4:])

        composed_query = query
        if len(history) > 2:
            composed_query = f"{query} (Context from prior conversation: {prior_context[:300]})"

        if progress_cb:
            progress_cb("SEARCHING", "Executing multi-hop discovery...")
        self.job_status = "SEARCHING"

        try:
            res = await self.researcher.execute_research(composed_query)

            if progress_cb:
                progress_cb("SYNTHESIZING", "Structuring evidence and claim citations...")
            self.job_status = "SYNTHESIZING"

            assistant_msg_id = str(uuid.uuid4())
            citations = [{"url": f["url"], "snippet": f["claim"]} for f in res.get("key_findings", [])]
            content = f"### Summary\n{res.get('executive_summary', '')}\n\n"
            if res.get("key_findings"):
                content += "### Key Findings\n"
                for f in res["key_findings"]:
                    content += f"- **[{f['claim']}]({f['url']})**\n"

            assistant_msg = ResearchChatMessage(
                id=assistant_msg_id,
                role="assistant",
                content=content,
                citations=citations,
                subqueries=res.get("methodology", {}).get("subqueries_searched", []),
                tokens_used=res.get("methodology", {}).get("tokens_returned", 0),
            )
            await asyncio.to_thread(self._save_message, assistant_msg)
            self.job_status = "COMPLETED"
            if progress_cb:
                progress_cb("COMPLETED", "Research step completed.")
            return assistant_msg
        except Exception as e:
            self.job_status = "FAILED"
            if progress_cb:
                progress_cb("FAILED", f"Error during research: {e}")
            raise

    def _save_message(self, msg: ResearchChatMessage) -> None:
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO messages (
                    id, session_id, role, content, citations_json,
                    subqueries_json, tokens_used, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    msg.id,
                    self.session_id,
                    msg.role,
                    msg.content,
                    json.dumps(msg.citations),
                    json.dumps(msg.subqueries),
                    msg.tokens_used,
                    msg.timestamp,
                ),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, self.session_id),
            )

    def get_messages(self) -> list[ResearchChatMessage]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, role, content, citations_json, subqueries_json, tokens_used, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY rowid ASC
                """,
                (self.session_id,),
            )
            rows = cursor.fetchall()

        return [
            ResearchChatMessage(
                id=r[0],
                role=r[1],
                content=r[2],
                citations=json.loads(r[3]),
                subqueries=json.loads(r[4]),
                tokens_used=r[5],
                timestamp=r[6],
            )
            for r in rows
        ]

    def export_session(self) -> ResearchSessionExport:
        msgs = self.get_messages()
        total_tokens = sum(m.tokens_used for m in msgs)
        all_urls = {c.get("url") for m in msgs for c in m.citations if c.get("url")}

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT topic, created_at, updated_at FROM sessions WHERE id = ?",
                (self.session_id,),
            ).fetchone()
            topic = row[0] if row else "Untitled"
            created_at = row[1] if row else ""
            updated_at = row[2] if row else ""

        return ResearchSessionExport(
            session_id=self.session_id,
            topic=topic,
            created_at=created_at,
            updated_at=updated_at,
            messages=[asdict(m) for m in msgs],
            total_tokens=total_tokens,
            total_sources=len(all_urls),
        )

    def export_markdown(self) -> str:
        data = self.export_session()
        md = [
            f"# Research Session: {data.topic}",
            f"- **Session ID**: `{data.session_id}`",
            f"- **Created**: {data.created_at}",
            f"- **Total Sources**: {data.total_sources}",
            f"- **Total Tokens**: {data.total_tokens}",
            "\n---\n",
        ]
        for m in data.messages:
            md.append(f"### {m['role'].upper()} ({m['timestamp']})\n")
            md.append(m["content"])
            if m["citations"]:
                md.append("\n**Sources Cited:**")
                for c in m["citations"]:
                    md.append(f"- [{c.get('url')}]({c.get('url')})")
            md.append("\n---\n")
        return "\n".join(md)
