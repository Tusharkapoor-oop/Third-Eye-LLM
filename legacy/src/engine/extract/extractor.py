"""
Unified Content Extraction Pipeline
Supports HTML articles, technical documentation, PDFs, and headless browser DOM rendering.
Enforces token limits and extracts exact text span attributions.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import tiktoken
import trafilatura
from bs4 import BeautifulSoup

from src.engine.config import CONFIG
from src.engine.extract.browser_fallback import fetch_rendered_dom
from src.engine.extract.chunker import DocumentChunker
from src.engine.extract.passage_scorer import BM25PassageScorer, ScoredPassage
from src.engine.reranker import rank_chunks
from src.engine.security import (
    is_blocked_response,
    safe_fetch_url,
    sanitize_untrusted_content,
    validate_url_security,
)


@dataclass
class ExtractedDocument:
    url: str
    status: str  # "success" | "fetch_failed" | "blocked" | "empty_content"
    title: str = ""
    fetch_timestamp: str = ""
    passages: list[ScoredPassage] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    tokens_used: int = 0
    full_text: str | None = None
    latency_seconds: float = 0.0

    def to_dict(self) -> dict:
        d = {
            "url": self.url,
            "status": self.status,
            "title": self.title,
            "fetch_timestamp": self.fetch_timestamp,
            "passages": [p.to_dict() for p in self.passages],
            "metadata": self.metadata,
            "tokens_used": self.tokens_used,
            "latency_seconds": round(self.latency_seconds, 3)
        }
        if self.full_text is not None:
            d["full_text"] = self.full_text
        return d


_NAV_MARKERS = (
    "join stack overflow",
    "stack internal",
    "stack exchange",
    "site logo",
    "sign up",
    "log in",
    "terms of service",
    "privacy policy",
    "cookie",
    "newsletter",
    "advertisement",
    "all communities",
)


def _clean_rescued_markdown(text: str) -> str:
    """Remove navigation and link-farm rows from third-party rescue output.

    Tavily's raw Markdown starts with the page chrome, and chunk ranking will
    happily select that chrome when the question terms appear in menu labels.
    Fenced code and table rows are preserved verbatim.
    """
    kept: list[str] = []
    in_fence = False
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            kept.append(line.rstrip())
            continue
        if in_fence:
            kept.append(line)
            continue
        if not stripped:
            if kept and kept[-1] != "":
                kept.append("")
            continue
        if stripped.startswith("!["):
            continue
        if stripped.startswith("|"):
            kept.append(stripped)
            continue
        words = re.findall(r"[A-Za-z0-9]+", stripped)
        links = re.findall(r"\[[^\]]*\]\([^)]*\)", stripped)
        if len(words) < 3:
            continue
        if len(links) >= 2 and len(words) < 14:
            continue
        low = stripped.casefold()
        if any(marker in low for marker in _NAV_MARKERS) and len(words) < 16:
            continue
        kept.append(stripped)
    return "\n".join(kept).strip()


class DocumentExtractor:
    def __init__(self):
        self.chunker = DocumentChunker(target_tokens=180, overlap_tokens=30)
        self.scorer = BM25PassageScorer()
        self.tokenizer = tiktoken.get_encoding("o200k_base")

    async def _tavily_extract_rescue(self, url: str) -> str | None:
        """Tier-3 (A5) last-resort rescue for WAF/CAPTCHA-blocked URLs."""
        key = (CONFIG.tavily_api_key or os.getenv("TAVILY_API_KEY", "")).strip()
        if not CONFIG.tavily_extract_fallback or not key:
            return None
        max_body = CONFIG.max_response_bytes or 2_000_000
        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=key)
            payload = await asyncio.to_thread(
                client.extract,
                urls=[url],
                extract_depth="advanced",
            )
            results = (payload or {}).get("results") or []
            for item in results:
                raw = (item.get("raw_content") or item.get("content") or "").strip()
                if raw:
                    return raw[:max_body]
            return None
        except Exception:
            return None

    @staticmethod
    def _structured_markdown(html: str) -> str:
        """Preserve code and table subtrees as atomic Markdown evidence."""
        if not html:
            return ""
        try:
            soup = BeautifulSoup(html, "html.parser")
            blocks: list[str] = []
            for pre in soup.find_all("pre"):
                code = pre.get_text("\n", strip=False).strip()
                if code:
                    language = ""
                    code_node = pre.find("code")
                    if code_node:
                        classes = code_node.get("class", [])
                        language = next((str(c).removeprefix("language-") for c in classes if str(c).startswith("language-")), "")
                    blocks.append(f"```{language}\n{code}\n```")
            for table in soup.find_all("table"):
                rows: list[list[str]] = []
                for row in table.find_all("tr"):
                    cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
                    if cells:
                        rows.append(cells)
                if rows:
                    width = max(len(row) for row in rows)
                    normalized = [row + [""] * (width - len(row)) for row in rows]
                    blocks.append("| " + " | ".join(normalized[0]) + " |\n| " + " | ".join("---" for _ in range(width)) + " |")
                    blocks.extend("| " + " | ".join(row) + " |" for row in normalized[1:])
            return "\n\n".join(blocks)
        except Exception:
            return ""

    @staticmethod
    def _normalize_code_blocks(markdown: str) -> str:
        """Repair whitespace inserted between code tokens by HTML converters."""
        def repair(match: re.Match[str]) -> str:
            block = match.group(0)
            block = re.sub(r"import\s+(?:\n\s*)+asyncio", "import asyncio", block, flags=re.IGNORECASE)
            block = re.sub(r"async\s+(?:\n\s*)+def", "async def", block, flags=re.IGNORECASE)
            block = re.sub(r"asyncio\s*(?:\n\s*)*\.\s*(?:\n\s*)*run", "asyncio.run", block, flags=re.IGNORECASE)
            return block

        return re.sub(r"```[^\n]*\n.*?\n```", repair, markdown, flags=re.DOTALL)

    @staticmethod
    def _normalize_prose(markdown: str) -> str:
        """Strip permalink artifacts and inline link markup outside code fences."""
        lines: list[str] = []
        in_fence = False
        for line in (markdown or "").split("\n"):
            if line.lstrip().startswith(("```", "~~~")):
                in_fence = not in_fence
                lines.append(line.rstrip())
                continue
            if in_fence:
                lines.append(line)
                continue
            cleaned = line.replace("\u00b6", "")
            cleaned = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", cleaned)
            cleaned = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", cleaned)
            cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).rstrip()
            lines.append(cleaned)
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()

    @classmethod
    def _extract_markdown(cls, html: str, url: str) -> tuple[str, dict[str, str]]:
        """Extract readable content and append structured blocks not retained by the parser."""
        extracted = trafilatura.extract(
            html or "", url=url, include_links=True, include_tables=True,
            include_images=False, include_comments=False, output_format="markdown",
        ) or ""
        structured = cls._structured_markdown(html)
        if structured:
            existing = extracted.casefold()
            additions = [block for block in structured.split("\n\n") if block.casefold() not in existing]
            if additions:
                extracted = "\n\n".join(part for part in (extracted, "\n\n".join(additions)) if part)
        return cls._normalize_code_blocks(cls._normalize_prose(extracted)).strip(), {}

    async def extract_url(
        self,
        url: str,
        query: str | None = None,
        mode: str = "passages",  # "passages" | "full"
        max_tokens: int = CONFIG.default_extract_tokens,
        render_js: bool = False
    ) -> ExtractedDocument:
        t0 = time.time()
        fetch_time = datetime.now(UTC).isoformat()

        # 1. Security Check
        is_safe, sec_reason, _ = validate_url_security(url)
        if not is_safe:
            return ExtractedDocument(
                url=url,
                status="blocked",
                fetch_timestamp=fetch_time,
                metadata={"error": f"Security block: {sec_reason}"},
                latency_seconds=time.time() - t0
            )

        # 2. HTTP Fetch
        status_code = 0
        raw_bytes = b""
        headers: dict[str, str] = {}
        final_url = url

        try:
            status_code, raw_bytes, headers, final_url = await asyncio.wait_for(
                safe_fetch_url(url, timeout=CONFIG.read_timeout),
                timeout=CONFIG.read_timeout
            )
        except PermissionError as pe:
            return ExtractedDocument(
                url=url,
                status="blocked",
                fetch_timestamp=fetch_time,
                metadata={"error": str(pe)},
                latency_seconds=time.time() - t0
            )
        except Exception as e:
            return ExtractedDocument(
                url=url,
                status="fetch_failed",
                fetch_timestamp=fetch_time,
                metadata={"error": str(e)},
                latency_seconds=time.time() - t0
            )

        if status_code >= 400 and status_code not in (403, 429, 503):
            return ExtractedDocument(
                url=url,
                status="fetch_failed",
                fetch_timestamp=fetch_time,
                metadata={"http_status": str(status_code)},
                latency_seconds=time.time() - t0
            )

        content_type = headers.get("content-type", "").lower()
        html = raw_bytes.decode("utf-8", errors="replace")
        blocked_shell = is_blocked_response(html, status_code)
        _rescued_text = None
        if blocked_shell:
            # Tier-3 rescue first when key is present: avoids slow browser timeouts on hard WAFs
            try:
                _rescued_text = await asyncio.wait_for(
                    self._tavily_extract_rescue(url), timeout=10.0
                )
            except TimeoutError:
                _rescued_text = None
            if _rescued_text is None and (render_js or CONFIG.enable_browser_fallback):
                try:
                    ok_dom, rendered_html = await asyncio.wait_for(
                        fetch_rendered_dom(url, timeout_sec=CONFIG.browser_timeout),
                        timeout=CONFIG.browser_timeout + 5.0,
                    )
                    if ok_dom and rendered_html and not is_blocked_response(rendered_html, 200):
                        html = rendered_html
                        status_code = 200
                        meta_rendered = "headless_browser"
                    else:
                        meta_rendered = "browser_failed"
                except Exception as browser_error:
                    meta_rendered = f"browser_error:{type(browser_error).__name__}"
            else:
                meta_rendered = "rescued_via_tavily" if _rescued_text else ""
        else:
            meta_rendered = ""

        if _rescued_text is None and is_blocked_response(html, status_code):
            return ExtractedDocument(
                url=url,
                status="blocked",
                fetch_timestamp=fetch_time,
                metadata={"http_status": str(status_code), "error": "WAF or bot-challenge response", "render_attempt": meta_rendered},
                latency_seconds=time.time() - t0,
            )
        extracted_text = _clean_rescued_markdown(_rescued_text) if _rescued_text else ""
        doc_title = ""
        meta_dict: dict[str, str] = {"content_type": content_type}
        if _rescued_text is not None:
            meta_dict["rescued_via"] = "tavily_extract:advanced"
            heading = next(
                (
                    line.lstrip("# ").strip()
                    for line in extracted_text.splitlines()
                    if line.startswith("# ")
                ),
                "",
            )
            if heading:
                doc_title = heading[:200]

        # 3. PDF Extraction
        if _rescued_text is None and ("application/pdf" in content_type or url.lower().endswith(".pdf")):
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(stream=raw_bytes, filetype="pdf")
                pages_text = []
                for p_idx in range(len(doc)):
                    page_t = doc[p_idx].get_text()
                    if page_t.strip():
                        pages_text.append(f"--- Page {p_idx+1} ---\n{page_t}")
                extracted_text = "\n\n".join(pages_text)
                doc_title = doc.metadata.get("title") or url.split("/")[-1]
                meta_dict["pages"] = str(len(doc))
            except Exception as e:
                meta_dict["pdf_error"] = str(e)

        # 4. HTML Extraction via Trafilatura + BeautifulSoup
        elif _rescued_text is None:
            html_text = html

            # Extract metadata (title, author, date)
            traf_metadata = trafilatura.extract_metadata(html_text)
            if traf_metadata:
                doc_title = traf_metadata.title or ""
                if traf_metadata.author:
                    meta_dict["author"] = traf_metadata.author
                if traf_metadata.date:
                    meta_dict["published_date"] = traf_metadata.date

            # Primary extraction: Trafilatura
            extracted_text, protected_meta = self._extract_markdown(html_text, final_url)
            meta_dict.update(protected_meta)
            if meta_rendered:
                meta_dict["rendered_via"] = meta_rendered

            # Fallback 1: BeautifulSoup article extraction if trafilatura failed
            if not extracted_text or len(extracted_text.strip()) < 100:
                soup = BeautifulSoup(html_text, "html.parser")
                if not doc_title and soup.title:
                    doc_title = soup.title.get_text(strip=True)
                main_elem = soup.find("article") or soup.find("main") or soup.find("body")
                if main_elem:
                    # Strip non-content tags
                    for t in main_elem(["script", "style", "nav", "footer", "aside", "header"]):
                        t.decompose()
                    extracted_text = main_elem.get_text(separator="\n\n", strip=True)

            # Fallback 2: Headless Browser if JavaScript rendered SPA and content is empty
            spa_markers = ('id="root"', 'id="app"', 'id="__next"', '<noscript>', 'react', 'vue', 'docusaurus')
            has_spa = any(m in html_text.lower() for m in spa_markers) if html_text else False
            if (not extracted_text or len(extracted_text.strip()) < 80) and (render_js or (CONFIG.enable_browser_fallback and has_spa)):
                try:
                    ok_dom, rendered_html = await asyncio.wait_for(
                        fetch_rendered_dom(url),
                        timeout=CONFIG.browser_timeout + 5.0,
                    )
                except Exception:
                    ok_dom, rendered_html = False, ""
                if ok_dom and rendered_html:
                    rendered_text = self._extract_markdown(rendered_html, final_url)[0]
                    if rendered_text and len(rendered_text.strip()) > len(extracted_text.strip()):
                        extracted_text = rendered_text
                        meta_dict["rendered_via"] = "headless_browser"

        # Sanitize untrusted content
        clean_text, has_inj = sanitize_untrusted_content(extracted_text)
        if has_inj:
            meta_dict["security_note"] = "Potential prompt injection keywords neutralized in source"

        low_quality_markers = (
            "javascript is disabled in your browser",
            "a required part of this site couldn’t load",
            "a required part of this site couldn't load",
            "please enable javascript to proceed",
        )
        if any(marker in clean_text.casefold() for marker in low_quality_markers):
            return ExtractedDocument(
                url=final_url,
                status="thin_content_js",
                title=doc_title,
                fetch_timestamp=fetch_time,
                metadata={**meta_dict, "error": "challenge or incomplete client-rendered content"},
                latency_seconds=time.time() - t0,
            )

        if not clean_text or not clean_text.strip():
            return ExtractedDocument(
                url=final_url,
                status="empty_content",
                title=doc_title,
                fetch_timestamp=fetch_time,
                metadata=meta_dict,
                latency_seconds=time.time() - t0
            )

        # 5. Chunking & BM25 Passage Ranking (Two-Stage Retrieval)
        chunks = self.chunker.chunk_document(clean_text)
        if query:
            ranking_query = query
            try:
                from src.engine.query_engine import optimize_query

                plan = optimize_query(query)
                ranking_query = " ".join(plan.get("sub_queries", [])) or query
            except (ImportError, TypeError, ValueError):
                ranking_query = query
            ranked = rank_chunks(clean_text, ranking_query, chunks_per_source=5)
            passages = []
            used_tokens = 0
            for rank, selected in enumerate(ranked, start=1):
                source_text = clean_text[selected.char_start:selected.char_end].strip()
                if not source_text:
                    continue
                passage_tokens = len(self.tokenizer.encode(source_text))
                if passages and used_tokens + passage_tokens > max_tokens:
                    continue
                if passage_tokens > max_tokens:
                    source_text = self.tokenizer.decode(
                        self.tokenizer.encode(source_text)[:max_tokens]
                    )
                    passage_tokens = len(self.tokenizer.encode(source_text))
                passages.append(ScoredPassage(
                    text=source_text,
                    char_start=selected.char_start,
                    char_end=selected.char_end,
                    token_count=passage_tokens,
                    rank=rank,
                ))
                used_tokens += passage_tokens
                if used_tokens >= max_tokens:
                    break
            if not passages:
                passages = self.scorer.score_and_rank_passages(chunks, query=ranking_query, max_tokens=max_tokens, max_passages=5)
        else:
            passages = self.scorer.score_and_rank_passages(chunks, query=None, max_tokens=max_tokens, max_passages=5)

        tokens_used = sum(p.token_count for p in passages)

        # Full-text mode handling if explicitly requested
        full_text_out = None
        if mode == "full":
            # Cap full text to 2 * max_tokens to prevent context window blowout
            full_tokens = self.tokenizer.encode(clean_text)
            if len(full_tokens) > max_tokens * 2:
                full_text_out = self.tokenizer.decode(full_tokens[:max_tokens * 2]) + "\n[Content truncated at max_tokens]"
                tokens_used = max_tokens * 2
            else:
                full_text_out = clean_text
                tokens_used = len(full_tokens)

        return ExtractedDocument(
            url=final_url,
            status="success",
            title=doc_title or url,
            fetch_timestamp=fetch_time,
            passages=passages,
            metadata=meta_dict,
            tokens_used=tokens_used,
            full_text=full_text_out,
            latency_seconds=time.time() - t0
        )
