"""Tiered Fast-to-Stealth Web Extraction Engine.

Implements:
- Tier 1: Fast HTTP + Custom DOM Pre-Protection for <pre>, <code>, and <table> (<300ms)
- Automatic WAF & SPA Skeleton Detection
- Tier 2: Persistent Warm Playwright Stealth Browser for dynamic SPAs & JS challenges
- Tier 3: Tavily API Rescue Fallback for hard enterprise WAFs
"""

from __future__ import annotations

import asyncio
import re

import trafilatura
from bs4 import BeautifulSoup, Tag

from config import CONFIG
from reranker import TwoStageReranker
from schemas import FailedItem, SourceItem
from security import (
    SecurityValidationError,
    resolve_and_verify_host,
    safe_fetch_url,
    sanitize_untrusted_content,
    validate_url_security,
)


def html_table_to_markdown(table: Tag) -> str:
    """Convert an HTML <table> element into clean GitHub-flavored Markdown table text."""
    rows = table.find_all("tr")
    if not rows:
        return ""

    table_data: list[list[str]] = []
    for row in rows:
        cells = row.find_all(["th", "td"])
        row_data = [" ".join(cell.get_text().split()).replace("|", "\\|") for cell in cells]
        if row_data:
            table_data.append(row_data)

    if not table_data:
        return ""

    col_count = max(len(r) for r in table_data)
    normalized_rows = [r + [""] * (col_count - len(r)) for r in table_data]

    md_lines: list[str] = []
    # Header row
    headers = normalized_rows[0]
    md_lines.append("| " + " | ".join(h if h else " " for h in headers) + " |")
    md_lines.append("| " + " | ".join("---" for _ in range(col_count)) + " |")

    # Data rows
    for r in normalized_rows[1:]:
        md_lines.append("| " + " | ".join(c if c else " " for c in r) + " |")

    return "\n" + "\n".join(md_lines) + "\n"


def strip_hidden_dom_elements(soup: BeautifulSoup) -> None:
    """Strip hidden DOM elements and comments used for indirect prompt injection."""
    from bs4 import Comment

    # Strip HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Strip tags with hidden styling or hidden attributes
    for el in soup.find_all(True):
        if el.has_attr("hidden") or el.get("aria-hidden") == "true":
            el.decompose()
            continue
        style = (el.get("style") or "").lower().replace(" ", "")
        if (
            "display:none" in style
            or "visibility:hidden" in style
            or "opacity:0" in style
            or "font-size:0" in style
        ):
            el.decompose()
            continue


def wrap_untrusted_provenance(text: str, url: str) -> str:
    """Wrap untrusted web text in provenance boundaries."""
    return f'<untrusted_source_content url="{url}">\n{text.strip()}\n</untrusted_source_content>'


def protect_code_and_tables(html_content: str) -> str:
    """Pre-protect <pre>, <code>, and <table> elements before feeding to readability extractors.

    Replaces elements with formatted Markdown placeholders so they are never stripped.
    """
    try:
        soup = BeautifulSoup(html_content, "html.parser")

        # Strip hidden injection vectors before processing
        strip_hidden_dom_elements(soup)

        # Protect <table> elements
        for table in soup.find_all("table"):
            md_table = html_table_to_markdown(table)
            if md_table.strip():
                table.replace_with(soup.new_string(f"\n\n{md_table}\n\n"))

        # Protect <pre> and <code> blocks
        for pre in soup.find_all("pre"):
            code_el = pre.find("code")
            code_text = code_el.get_text() if code_el else pre.get_text()
            lang = ""
            if code_el and code_el.get("class"):
                classes = " ".join(code_el.get("class"))
                lang_match = re.search(r"\blanguage-([a-zA-Z0-9_-]+)\b", classes)
                if lang_match:
                    lang = lang_match.group(1)

            clean_code = code_text.strip()
            if clean_code:
                fenced = f"\n\n```{lang}\n{clean_code}\n```\n\n"
                pre.replace_with(soup.new_string(fenced))

        return str(soup)
    except Exception:
        return html_content


def extract_markdown(html_content: str) -> str:
    """Extract clean Markdown from HTML with code fence and identifier restoration."""
    protected_html = protect_code_and_tables(html_content)
    extracted = trafilatura.extract(
        protected_html,
        output_format="markdown",
        include_tables=True,
        include_formatting=True,
        include_links=True,
    ) or ""
    # Restore code fences escaped by trafilatura: \`\`\` -> ```
    extracted = re.sub(r"\\`\\`\\`", "```", extracted)
    # Restore escaped underscores in identifiers: foo\_bar -> foo_bar
    extracted = re.sub(r"\\_", "_", extracted)
    return extracted


def is_blocked_or_spa(html_content: str, text_content: str, status_code: int) -> tuple[bool, str]:
    """Detect if the page response is an anti-bot challenge or empty JavaScript SPA skeleton.

    Returns:
        tuple[bool, str]: (is_blocked_or_empty, reason)
    """
    if status_code in (403, 429, 503):
        return True, f"HTTP_{status_code}_STATUS_BLOCK"

    low_html = html_content.lower()

    # Check for WAF signatures
    for sig in CONFIG.waf_signatures:
        if sig in low_html:
            return True, f"WAF_SIGNATURE_DETECTED: {sig}"

    # Check for empty SPA skeleton
    if len(text_content.strip()) < 250:
        for marker in CONFIG.spa_markers:
            if marker in low_html:
                return True, "EMPTY_SPA_SKELETON"
        if len(text_content.strip()) < 80:
            return True, "INSUFFICIENT_TEXT_CONTENT"

    return False, "CLEAN"


class TieredExtractor:
    """Manages Tier 1 (fast HTTP), Tier 2 (warm Playwright), and Tier 3 (Tavily rescue)."""

    def __init__(self):
        self.reranker = TwoStageReranker()
        self._playwright = None
        self._browser = None
        self._browser_lock = asyncio.Lock()

    async def _get_browser(self):
        """Lazy-start warm Playwright Chromium singleton."""
        if self._browser is None:
            async with self._browser_lock:
                if self._browser is None:
                    from playwright.async_api import async_playwright
                    self._playwright = await async_playwright().start()
                    self._browser = await self._playwright.chromium.launch(
                        headless=CONFIG.headless,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-gpu",
                            "--disable-dev-shm-usage",
                            "--no-sandbox",
                        ],
                    )
        return self._browser

    async def close(self) -> None:
        """Cleanly close persistent browser resources."""
        async with self._browser_lock:
            if self._browser is not None:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._playwright is not None:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

            try:
                import psutil
                killed = []
                for child in psutil.Process().children(recursive=True):
                    if any(b in child.name().lower() for b in ("chrome", "chromium", "playwright")):
                        try:
                            child.kill()
                            killed.append(child)
                        except Exception:
                            pass
                if killed:
                    psutil.wait_procs(killed, timeout=3.0)
            except Exception:
                pass

    async def _extract_tier2_playwright(self, url: str) -> tuple[str, str, str | None]:
        """Tier 2: Render dynamic SPA using persistent warm Playwright browser."""
        # Mirror the tier-1 SSRF policy before Chromium is even launched: the URL
        # must use an allowed scheme/port and resolve only to public addresses.
        host, port = validate_url_security(url)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, resolve_and_verify_host, host, port)

        browser = await self._get_browser()
        context = await browser.new_context(
            user_agent=CONFIG.user_agent,
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )
        page = await context.new_page()

        # Every request Chromium makes (document, XHR, iframe, redirect target) is
        # re-validated; DNS is resolved off the event loop and cached per host.
        validated_hosts: dict[tuple[str, int], None] = {}

        async def _guarded_route(route) -> None:
            if route.request.resource_type in ("image", "media", "font"):
                await route.abort()
                return
            try:
                req_host, req_port = validate_url_security(route.request.url)
                if (req_host, req_port) not in validated_hosts:
                    await loop.run_in_executor(None, resolve_and_verify_host, req_host, req_port)
                    validated_hosts[(req_host, req_port)] = None
            except Exception:
                await route.abort()
                return
            await route.continue_()

        await page.route("**/*", _guarded_route)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=CONFIG.page_timeout_ms)
            # Short dynamic content settle window
            await asyncio.sleep(0.5)

            title = await page.title()
            html_content = await page.content()

            extracted_md = extract_markdown(html_content)

            return title, extracted_md, None
        finally:
            await page.close()
            await context.close()

    async def _extract_tier3_tavily(self, url: str) -> tuple[str, str, str | None]:
        """Tier 3: Rescue heavily protected enterprise WAF page using Tavily Extract."""
        if not CONFIG.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY not configured for Tier 3 rescue")

        from tavily import TavilyClient
        client = TavilyClient(api_key=CONFIG.tavily_api_key)

        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(
            None,
            lambda: client.extract(urls=[url], extract_depth="advanced"),
        )
        results = res.get("results", [])
        if not results:
            failed = res.get("failed_results", [])
            err_msg = failed[0].get("error", "Tavily extract returned empty") if failed else "No content"
            raise RuntimeError(f"Tier 3 rescue failed: {err_msg}")

        item = results[0]
        title = item.get("title", "")
        raw_text = item.get("raw_content", "") or item.get("content", "")
        return title, raw_text, None

    async def extract_url(
        self,
        url: str,
        *,
        query: str | None = None,
        chunks_per_source: int = 3,
        force_tier2: bool = False,
    ) -> SourceItem | FailedItem:
        """Execute tiered extraction pipeline with automatic WAF fallback."""
        title = ""
        markdown_text = ""

        try:
            if not force_tier2:
                # --- Tier 1: Fast HTTP ---
                status, headers, body = await safe_fetch_url(url)
                html_text = body.decode("utf-8", errors="replace")

                # Extract title via BeautifulSoup
                soup = BeautifulSoup(html_text, "html.parser")
                title_tag = soup.find("title")
                title = title_tag.get_text().strip() if title_tag else ""

                markdown_text = extract_markdown(html_text)

                # Check if Tier 1 hit a WAF or empty SPA skeleton
                is_blocked, reason = is_blocked_or_spa(html_text, markdown_text, status)
                if is_blocked:
                    # Upgrade to Tier 2 Playwright
                    try:
                        title_t2, text_t2, _ = await self._extract_tier2_playwright(url)
                        if len(text_t2.strip()) > len(markdown_text.strip()):
                            title = title_t2 or title
                            markdown_text = text_t2
                    except Exception:
                        # If Tier 2 failed, attempt Tier 3 Tavily rescue
                        if CONFIG.tavily_api_key:
                            try:
                                title_t3, text_t3, _ = await self._extract_tier3_tavily(url)
                                title = title_t3 or title
                                markdown_text = text_t3
                            except Exception:
                                pass
            else:
                # Direct Tier 2 request
                title, markdown_text, _ = await self._extract_tier2_playwright(url)

            if not markdown_text.strip():
                return FailedItem(url=url, error="Empty page content after all tiers", blocked_by_waf=False)

            # Sanitize any prompt injections in extracted text
            clean_md, _ = sanitize_untrusted_content(markdown_text)

            # Two-Stage intra-page chunk ranking
            effective_query = query if query else (title or "main overview content")
            ranked_chunks = self.reranker.rank_passages(
                query=effective_query,
                markdown_text=clean_md,
                chunks_per_source=chunks_per_source,
            )

            # Stitched content
            stitched_content = "\n\n".join(c.content for c in ranked_chunks)
            if not stitched_content.strip():
                stitched_content = clean_md[:1500]

            overall_score = ranked_chunks[0].score if ranked_chunks else 0.5

            return SourceItem(
                title=title or "Untitled Source",
                url=url,
                content=stitched_content,
                score=overall_score,
                raw_content=clean_md if CONFIG.default_extract_tokens > 2000 else None,
                chunks=ranked_chunks,
            )

        except SecurityValidationError as sec_err:
            return FailedItem(url=url, error=f"Security Policy Blocked: {sec_err}", blocked_by_waf=True)
        except Exception as exc:
            # Automatic fallback to Tier 3 on hard network exception
            if CONFIG.tavily_api_key:
                try:
                    title_t3, text_t3, _ = await self._extract_tier3_tavily(url)
                    clean_md, _ = sanitize_untrusted_content(text_t3)
                    ranked_chunks = self.reranker.rank_passages(
                        query=query or title_t3 or "main content",
                        markdown_text=clean_md,
                        chunks_per_source=chunks_per_source,
                    )
                    stitched = "\n\n".join(c.content for c in ranked_chunks) or clean_md[:1500]
                    return SourceItem(
                        title=title_t3 or "Rescued Source",
                        url=url,
                        content=stitched,
                        score=0.85,
                        chunks=ranked_chunks,
                    )
                except Exception:
                    pass

            return FailedItem(url=url, error=f"Extraction failure: {type(exc).__name__}: {str(exc)[:200]}", blocked_by_waf=False)

