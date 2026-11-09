"""Extraction orchestration and compact, budgeted output."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from ..cache import Cache
from ..config import Settings
from ..errors import ErrCode, WebLensError, resolve_budget
from ..extract.browser import BrowserRenderer
from ..net import FetchResponse, SafeFetcher
from ..security.injection import has_instruction_smuggling
from ..tokens import count_json_tokens, count_tokens, truncate_tokens
from ..urls import normalize_url
from .html import ExtractedDoc, extract_html, extract_pdf, extract_plain
from .passages import Passage, select_passages

FRESH_QUERY = ("latest", "current", "today", "now", "2026", "2025", "price", "release", "news")

# A short page is often a complete answer on its own (for example,
# example.com's "documentation examples" stub). Returning zero passages from
# such a page loses evidence that the caller can verify verbatim. Long pages
# with no query match remain "no_reliable_result" so unrelated content is not
# mistaken for an answer.
SHORT_PAGE_FALLBACK_CHARS = 600


@dataclass
class ExtractOutcome:
    status: str
    url: str
    final_url: str
    title: str
    fetched_at: str
    sha: str
    kind: str
    passages: list[Passage] = field(default_factory=list)
    full_text: str | None = None
    published: str | None = None
    warnings: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    tokens: int = 0
    cut: bool = False
    budget: int = 1500


class ExtractionService:
    def __init__(self, settings: Settings, fetcher: SafeFetcher, cache: Cache):
        self.s = settings
        self.fetcher = fetcher
        self.cache = cache
        self._renderer: BrowserRenderer | None = None

    async def _renderer_get(self):
        if self._renderer is None:
            from .browser import BrowserRenderer

            self._renderer = BrowserRenderer(self.s)
        return self._renderer

    async def close(self) -> None:
        if self._renderer is not None:
            await self._renderer.close()
            self._renderer = None

    async def fetch_doc(
        self,
        url: str,
        *,
        allow_browser: bool = True,
        include_links: bool = False,
        timeout_s: float | None = None,
    ) -> ExtractedDoc:
        canon = normalize_url(url)
        if not canon:
            raise WebLensError("invalid URL", code=ErrCode.BAD_INPUT)
        budget = self.s.total_timeout_s if timeout_s is None else timeout_s
        if budget > 0:
            # A small margin lets the fetcher raise its own typed timeout and
            # serve a stale copy before this outer guard cancels the task.
            async with asyncio.timeout(budget + 2):
                return await self._fetch_doc_inner(
                    canon,
                    allow_browser=allow_browser,
                    include_links=include_links,
                    timeout_s=timeout_s,
                )
        return await self._fetch_doc_inner(
            canon,
            allow_browser=allow_browser,
            include_links=include_links,
            timeout_s=timeout_s,
        )

    async def _fetch_doc_inner(
        self,
        canon: str,
        *,
        allow_browser: bool,
        include_links: bool,
        timeout_s: float | None,
    ) -> ExtractedDoc:
        resp: FetchResponse = await self.fetcher.fetch(
            canon,
            headers={"Accept": "text/html,application/xhtml+xml,application/pdf,text/plain;q=0.9,*/*;q=0.4"},
            cache_ttl=self.s.page_cache_ttl_s,
            timeout_s=timeout_s,
            stale_ok=True,
        )
        kind = resp.media_kind
        warnings: list[str] = []
        if resp.stale:
            warnings.append("stale_cache_used")
        # CPU-heavy extraction libraries (trafilatura, PyMuPDF) block the event loop;
        # run them on the default executor.
        if kind == "pdf":
            doc = await asyncio.to_thread(extract_pdf, resp.body, canon)
        elif kind == "html":
            doc = await asyncio.to_thread(extract_html, resp.text, canon, include_links=include_links)
            if has_instruction_smuggling(resp.text):
                warnings.append("html_comment_instructions")
        elif kind in {"text", "data"}:
            doc = extract_plain(resp.text, canon)
        else:
            raise WebLensError(
                f"unsupported content type: {resp.content_type or 'unknown'}",
                code=ErrCode.UNSUPPORTED,
            )

        doc.fetched_at = resp.fetched_at
        doc.final_url = resp.final_url
        doc.truncated = resp.truncated
        doc.warnings.extend(warnings)
        if resp.truncated:
            doc.warnings.append("response_truncated")

        if doc.needs_browser and allow_browser and self.s.allow_browser:
            try:
                renderer = await self._renderer_get()
                rendered, final = await renderer.render(canon)
                rendered_doc = extract_html(rendered, final, include_links=include_links)
                if len(rendered_doc.text) > len(doc.text) + 100:
                    rendered_doc.fetched_at = resp.fetched_at
                    rendered_doc.final_url = final
                    rendered_doc.warnings.append("browser_rendered")
                    doc = rendered_doc
                else:
                    doc.warnings.append("browser_no_improvement")
            except Exception as e:
                doc.warnings.append(f"browser_failed:{type(e).__name__}")
        return doc

    async def extract(
        self,
        url: str,
        *,
        query: str | None = None,
        max_tokens: int | None = None,
        full: bool = False,
        allow_browser: bool = True,
    ) -> ExtractOutcome:
        started = time.perf_counter()
        budget = resolve_budget(max_tokens, self.s.max_extract_tokens, minimum=200, maximum=8000)
        doc = await self.fetch_doc(url, allow_browser=allow_browser, include_links=full)
        out = ExtractOutcome(
            status="ok",
            url=url,
            final_url=doc.final_url or url,
            title=doc.title,
            fetched_at=doc.fetched_at,
            sha=doc.sha256,
            kind=doc.kind,
            published=doc.date_iso(),
            warnings=list(dict.fromkeys(doc.warnings)),
            budget=budget,
        )
        if not doc.text.strip():
            out.status = "error"
            out.warnings.append(ErrCode.EXTRACT.value)
            out.elapsed_ms = int((time.perf_counter() - started) * 1000)
            return out

        if full:
            # Reserve room for the envelope and provenance fields.
            overhead = 90
            text, cut = truncate_tokens(doc.text, max(50, budget - overhead))
            out.full_text = text
            out.cut = cut
            payload = self._full_payload(out)
            out.tokens = count_json_tokens(payload)
            return self._finish(out, started)

        passages, coverage = select_passages(
            doc.text,
            query,
            title=doc.title,
            max_passages=4,
            max_chars=9000,
        )
        q = (query or "").strip()
        if q:
            if not passages or coverage == 0:
                # A short page is complete evidence even when the query does
                # not share its vocabulary. Fall back to the whole page rather
                # than returning an empty successful-looking extraction.
                if len(doc.text.strip()) <= SHORT_PAGE_FALLBACK_CHARS:
                    passages, _ = select_passages(
                        doc.text,
                        None,
                        title=doc.title,
                        max_passages=4,
                        max_chars=9000,
                    )
                if not passages:
                    out.status = "no_reliable_result"
                    out.warnings.append("no_query_match")
                    out.passages = []
                    return self._finish(out, started)
                out.status = "partial"
                out.warnings.extend(["low_query_match", "short_page_fallback"])
            elif coverage < 0.34:
                out.status = "partial"
                out.warnings.append("low_query_match")
            if doc.published and any(w in q.lower() for w in FRESH_QUERY):
                from .html import age_days

                age = age_days(doc.published)
                if age is not None and age > 365:
                    out.status = "possibly_outdated"
                    out.warnings.append("source_older_than_1y")
                elif age is None:
                    out.warnings.append("date_unknown")
        else:
            out.warnings.append("unranked_page_passages")

        out.passages = passages
        return self._finish(out, started)

    @staticmethod
    def _passage_payload(out: ExtractOutcome, passages: list[Passage] | None = None) -> dict:
        ps = []
        for p in passages if passages is not None else out.passages:
            item: dict[str, object] = {
                "u": out.final_url,
                "at": out.fetched_at,
                "x": p.text,
                "s": [p.start, p.end],
            }
            if p.heading:
                item["h"] = p.heading
            if p.injection:
                item["inj"] = p.injection
            ps.append(item)
        body: dict[str, object] = {
            "status": out.status,
            "u": out.final_url,
            "t": out.title,
            "at": out.fetched_at,
            "sha": out.sha[:16],
            "src": out.kind,
            "ps": ps,
            "tok": 0,
        }
        if out.published:
            body["d"] = out.published
        if out.cut:
            body["cut"] = True
        if out.warnings:
            body["warn"] = list(dict.fromkeys(out.warnings))
        return body

    @staticmethod
    def _full_payload(out: ExtractOutcome) -> dict:
        body: dict[str, object] = {
            "status": out.status,
            "u": out.final_url,
            "t": out.title,
            "at": out.fetched_at,
            "sha": out.sha[:16],
            "src": out.kind,
            "full": True,
            "x": out.full_text or "",
            "s": [0, len(out.full_text or "")],
            "tok": 0,
        }
        if out.published:
            body["d"] = out.published
        if out.cut:
            body["cut"] = True
        if out.warnings:
            body["warn"] = list(dict.fromkeys(out.warnings))
        return body

    def _finish(self, out: ExtractOutcome, started: float) -> ExtractOutcome:
        out.elapsed_ms = int((time.perf_counter() - started) * 1000)
        body = self.payload(out)
        out.tokens = body["tok"]  # type: ignore[assignment]
        return out

    @classmethod
    def payload(cls, out: ExtractOutcome) -> dict:
        """Build the compact payload and enforce the token budget exactly.

        The budget includes the envelope, provenance, ``ms`` and ``tok``. A
        passage is first truncated, then dropped; if even the envelope cannot
        fit, the result is marked ``budget_exhausted``.
        """
        budget = max(120, out.budget)
        target = max(80, budget - 6)
        if out.full_text is not None:
            for _ in range(60):
                body = cls._full_payload(out)
                body["ms"] = out.elapsed_ms
                body["tok"] = 0
                n = count_json_tokens(body)
                if n <= target:
                    break
                text = out.full_text or ""
                over = n - target
                keep = count_tokens(text) - over - 4
                if keep < 20:
                    out.full_text = ""
                    out.cut = True
                    break
                short, _ = truncate_tokens(text, keep)
                if not short or len(short) >= len(text):
                    out.full_text = ""
                    out.cut = True
                    break
                out.full_text = short
                out.cut = True
            body = cls._full_payload(out)
        else:
            for _ in range(80):
                body = cls._passage_payload(out)
                body["ms"] = out.elapsed_ms
                body["tok"] = 0
                n = count_json_tokens(body)
                if n <= target:
                    break
                if not out.passages:
                    break
                p = out.passages[-1]
                over = n - target
                keep = count_tokens(p.text) - over - 4
                if keep >= 40:
                    short, _ = truncate_tokens(p.text, keep)
                    if short and len(short) < len(p.text):
                        p.text = short
                        p.end = p.start + len(short)
                        out.cut = True
                        continue
                out.passages.pop()
                out.cut = True
            body = cls._passage_payload(out)
        body["ms"] = out.elapsed_ms
        body["tok"] = count_json_tokens({**body, "tok": 0})
        if count_json_tokens(body) > budget:
            warn = list(dict.fromkeys([*(body.get("warn") or []), "budget_exhausted"]))
            body["warn"] = warn
            body["tok"] = count_json_tokens({**body, "tok": 0})
        out.tokens = body["tok"]  # type: ignore[assignment]
        return body
