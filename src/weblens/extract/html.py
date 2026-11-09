"""HTML/PDF to clean text, preserving headings and tables where useful."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from lxml import etree as lxml_etree
from lxml import html as lxml_html

# lxml raises ParserError (not ValueError) on empty or non-XML input; treat it
# like any other unparseable document so a blank response cannot crash extraction.
_PARSE_ERRORS: tuple[type[BaseException], ...] = (ValueError, TypeError, lxml_etree.ParserError)

ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)
# Bullet/decoration characters surrounding boilerplate labels ("· Skip to
# content •"). Written as escapes so the source stays ASCII and cannot be
# corrupted by an editor's encoding.
BULLET_CHARS = "\u00b7\u2022-\u2013\u2014|[]() "
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Short lines that are almost always site chrome. Long lines are never removed:
# a sentence that happens to contain "subscribe" is content.
BOILERPLATE = {
    "skip to content",
    "skip to main content",
    "skip navigation",
    "accept all",
    "accept all cookies",
    "reject all",
    "cookie settings",
    "manage cookies",
    "sign in",
    "log in",
    "subscribe",
    "newsletter",
    "advertisement",
    "share this article",
    "share on facebook",
    "share on twitter",
    "share on linkedin",
    "table of contents",
    "back to top",
    "all rights reserved",
    "privacy policy",
    "terms of service",
    "follow us",
}

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$", re.MULTILINE)


@dataclass
class ExtractedDoc:
    url: str
    final_url: str
    title: str
    text: str
    fetched_at: str
    sha256: str
    kind: str = "html"
    author: str | None = None
    published: str | None = None
    sitename: str | None = None
    truncated: bool = False
    needs_browser: bool = False
    links: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def date_iso(self) -> str | None:
        return normalize_date(self.published)


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    from ..search.base import parse_date

    return parse_date(value)


def _clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.translate(ZERO_WIDTH)
    text = CONTROL.sub(" ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            lines.append(line)
            continue
        stripped = line.strip()
        if not in_fence and stripped and len(stripped) <= 60:
            # Strip common bullet/marker characters before matching boilerplate.
            probe = stripped.strip(BULLET_CHARS).lower()
            if probe in BOILERPLATE:
                continue
        # GitHub-style source tables emit one line number per line; they are
        # not content and they bloat both tokens and sentence splitting.
        if not in_fence and stripped.isdigit() and len(stripped) <= 4:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _is_js_shell(html_text: str) -> bool:
    low = html_text.lower()
    if len(re.sub(r"<[^>]+>", " ", html_text)) > 1200:
        return False
    markers = (
        "enable javascript",
        "javascript is required",
        'id="root"',
        "id='root'",
        'id="app"',
        "__next_data__",
        "noscript",
    )
    return any(m in low for m in markers)


def _fallback_extract(html_text: str) -> tuple[str, str]:
    """Last-resort main-content extraction when trafilatura returns little."""
    try:
        doc = lxml_html.fromstring(html_text)
    except _PARSE_ERRORS:
        return "", ""
    title = ""
    t = doc.find(".//title")
    if t is not None:
        title = " ".join(t.text_content().split())
    for bad in doc.xpath("//script|//style|//noscript|//nav|//footer|//aside|//form"):
        bad.getparent().remove(bad)
    roots = doc.xpath("//main|//article|//*[@role='main']")
    root = roots[0] if roots else doc.body
    if root is None:
        return title, ""
    parts: list[str] = []
    for el in root.iter():
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag in {"h1", "h2", "h3", "h4"}:
            txt = " ".join(el.text_content().split())
            if txt:
                parts.append("#" * int(tag[1]) + " " + txt)
        elif tag in {"p", "li", "pre", "blockquote", "td", "th"}:
            txt = " ".join(el.text_content().split())
            if len(txt) > 20:
                parts.append(txt)
    return title, _clean_text("\n\n".join(parts))


def extract_meta(html_text: str) -> dict[str, str | None]:
    """Cheap metadata extraction via lxml (trafilatura metadata is seconds slower)."""
    out: dict[str, str | None] = {"title": None, "author": None, "published": None, "sitename": None}
    try:
        doc = lxml_html.fromstring(html_text)
    except _PARSE_ERRORS:
        return out
    title = doc.find(".//title")
    if title is not None and title.text_content().strip():
        out["title"] = " ".join(title.text_content().split())[:300]
    props = {
        "og:title": "title",
        "twitter:title": "title",
        "og:site_name": "sitename",
        "article:published_time": "published",
        "article:modified_time": "published",
        "date": "published",
        "author": "author",
    }
    for meta in doc.xpath("//meta"):
        key = (meta.get("property") or meta.get("name") or "").lower()
        val = (meta.get("content") or "").strip()
        if not val:
            continue
        target = props.get(key)
        if target and not out[target]:
            out[target] = val[:300]
    if not out["published"]:
        for meta in doc.xpath("//meta[@itemprop='datePublished']"):
            val = (meta.get("content") or "").strip()
            if val:
                out["published"] = val[:300]
                break
    if not out["published"]:
        m = re.search(r'"datePublished"\s*:\s*"([^"]{4,40})"', html_text)
        if m:
            out["published"] = m.group(1)
    return out


def extract_html(html_text: str, url: str, *, include_links: bool = False) -> ExtractedDoc:
    import trafilatura

    meta = extract_meta(html_text)
    title = (meta.get("title") or "").strip()
    author = (meta.get("author") or "").strip() or None
    published = (meta.get("published") or "").strip() or None
    sitename = (meta.get("sitename") or "").strip() or None

    text = ""
    # Pre-clean known chrome: Wikipedia and documentation TOCs (F5-F7 requirement)
    input_html = html_text
    if 'id="toc"' in html_text or 'class="toc"' in html_text or 'id="toctitle"' in html_text:
        try:
            tree = lxml_html.fromstring(html_text)
            for el in tree.xpath('//*[@id="toc" or @id="toctitle" or contains(@class, "toc")]'):
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)
            input_html = lxml_html.tostring(tree, encoding="unicode")
        except Exception:
            input_html = html_text

    try:
        text = (
            trafilatura.extract(
                input_html,
                url=url,
                output_format="markdown",
                include_formatting=True,
                include_tables=True,
                include_links=include_links,
                include_comments=False,
                deduplicate=False,
                fast=True,
                favor_precision=False,
                favor_recall=False,
            )
            or ""
        )
    except Exception:
        text = ""
    if len(text) < 200:
        fb_title, fb_text = _fallback_extract(html_text)
        if len(fb_text) > len(text):
            text = fb_text
            title = title or fb_title
    text = _clean_text(text)
    if not title:
        try:
            doc = lxml_html.fromstring(html_text)
            t = doc.find(".//title")
            if t is not None:
                title = " ".join(t.text_content().split())
        except _PARSE_ERRORS:
            pass

    warnings: list[str] = []
    needs_browser = len(text) < 200 and _is_js_shell(html_text)
    if needs_browser:
        warnings.append("javascript_required")
    if len(text) < 200:
        warnings.append("low_content")

    links: list[tuple[str, str]] = []
    try:
        doc = lxml_html.fromstring(html_text)
        base = url
        for a in doc.iter("a"):
            href = (a.get("href") or "").strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            from ..urls import normalize_url

            canon = normalize_url(href, base=base)
            if not canon:
                continue
            text_a = " ".join(a.text_content().split())[:160]
            links.append((canon, text_a))
            if len(links) >= 400:
                break
    except _PARSE_ERRORS:
        pass

    return ExtractedDoc(
        url=url,
        final_url=url,
        title=(title or url)[:300],
        text=text,
        fetched_at="",
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        kind="html",
        author=author,
        published=published,
        sitename=sitename,
        needs_browser=needs_browser,
        links=links,
        warnings=warnings,
    )


def extract_plain(text: str, url: str, title: str = "") -> ExtractedDoc:
    cleaned = _clean_text(text)
    return ExtractedDoc(
        url=url,
        final_url=url,
        title=title or url,
        text=cleaned,
        fetched_at="",
        sha256=hashlib.sha256(cleaned.encode()).hexdigest(),
        kind="text",
        warnings=["low_content"] if len(cleaned) < 200 else [],
    )


def extract_pdf(body: bytes, url: str) -> ExtractedDoc:
    import pymupdf

    warnings: list[str] = []
    try:
        doc = pymupdf.open(stream=body, filetype="pdf")
    except Exception:
        return ExtractedDoc(
            url=url,
            final_url=url,
            title=url,
            text="",
            fetched_at="",
            sha256="",
            kind="pdf",
            warnings=["pdf_parse_failed"],
        )
    try:
        if doc.needs_pass:
            return ExtractedDoc(
                url=url,
                final_url=url,
                title=url,
                text="",
                fetched_at="",
                sha256="",
                kind="pdf",
                warnings=["pdf_encrypted"],
            )
        page_count = doc.page_count
        pages: list[str] = []
        for i in range(min(page_count, 40)):
            try:
                t = doc[i].get_text() or ""
            except Exception:  # noqa: S112 - skip unreadable PDF pages
                continue
            t = _clean_text(t)
            if t:
                pages.append(f"## Page {i + 1}\n\n{t}")
        text = "\n\n".join(pages)
        if page_count > 40:
            warnings.append("pdf_truncated_40_pages")
        if not text:
            warnings.append("pdf_no_text_layer")
        meta = doc.metadata or {}
        return ExtractedDoc(
            url=url,
            final_url=url,
            title=(meta.get("title") or "").strip() or url,
            text=text,
            fetched_at="",
            sha256=hashlib.sha256(text.encode()).hexdigest(),
            kind="pdf",
            author=(meta.get("author") or "").strip() or None,
            warnings=warnings,
        )
    finally:
        doc.close()


def age_days(iso: str | None) -> int | None:
    from ..search.base import parse_date

    parsed = parse_date(iso)
    if not parsed:
        return None
    try:
        d = date.fromisoformat(parsed)
    except ValueError:
        return None
    return (date.today() - d).days


def heading_of(text: str, offset: int) -> str | None:
    """Nearest preceding markdown heading for a character offset."""
    head = text[:offset]
    matches = list(HEADING.finditer(head))
    if not matches:
        return None
    return matches[-1].group(2)[:120]
