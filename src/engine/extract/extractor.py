"""
Unified Content Extraction Pipeline
Supports HTML articles, technical documentation, PDFs, and headless browser DOM rendering.
Enforces token limits and extracts exact text span attributions.
"""

from __future__ import annotations

import asyncio
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
from src.engine.security import (
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

class DocumentExtractor:
    def __init__(self):
        self.chunker = DocumentChunker(target_tokens=180, overlap_tokens=30)
        self.scorer = BM25PassageScorer()
        self.tokenizer = tiktoken.get_encoding("o200k_base")

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

        if status_code >= 400:
            return ExtractedDocument(
                url=url,
                status="fetch_failed",
                fetch_timestamp=fetch_time,
                metadata={"http_status": str(status_code)},
                latency_seconds=time.time() - t0
            )

        content_type = headers.get("content-type", "").lower()
        extracted_text = ""
        doc_title = ""
        meta_dict: dict[str, str] = {"content_type": content_type}

        # 3. PDF Extraction
        if "application/pdf" in content_type or url.lower().endswith(".pdf"):
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
        else:
            try:
                html_text = raw_bytes.decode("utf-8", errors="replace")
            except Exception:
                html_text = ""

            # Extract metadata (title, author, date)
            traf_metadata = trafilatura.extract_metadata(html_text)
            if traf_metadata:
                doc_title = traf_metadata.title or ""
                if traf_metadata.author:
                    meta_dict["author"] = traf_metadata.author
                if traf_metadata.date:
                    meta_dict["published_date"] = traf_metadata.date

            # Primary extraction: Trafilatura
            extracted_text = trafilatura.extract(
                html_text,
                include_links=True,
                include_tables=True,
                output_format="markdown"
            ) or ""

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
                ok_dom, rendered_html = await fetch_rendered_dom(url)
                if ok_dom and rendered_html:
                    rendered_text = trafilatura.extract(rendered_html, include_links=True, output_format="markdown")
                    if rendered_text and len(rendered_text.strip()) > len(extracted_text.strip()):
                        extracted_text = rendered_text
                        meta_dict["rendered_via"] = "headless_browser"

        # Sanitize untrusted content
        clean_text, has_inj = sanitize_untrusted_content(extracted_text)
        if has_inj:
            meta_dict["security_note"] = "Potential prompt injection keywords neutralized in source"

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
        passages = self.scorer.score_and_rank_passages(
            chunks,
            query=query,
            max_tokens=max_tokens,
            max_passages=5
        )

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
