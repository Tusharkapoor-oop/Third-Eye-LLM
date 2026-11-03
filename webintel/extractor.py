"""Tiered extraction with atomic code/table protection.

Tier 1  async httpx (SSRF-validated, byte-capped) + DOM-protected Trafilatura.
Tier 2  persistent warm Playwright Chromium with stealth flags and resource
        blocking, for JavaScript shells and soft WAFs.
Tier 3  targeted Tavily ``extract`` rescue when a locally blocked URL matters
        and an API key is configured.

The central trick is that ``<pre>``, ``<code>`` and ``<table>`` subtrees are
lifted out of the DOM *before* any text extractor runs and replaced with a
sentinel. Extractors therefore cannot strip, merge or reflow them. The sentinel
is restored afterwards as a fenced code block or a GitHub-flavoured table.
Anything the extractor drops is appended under "Recovered code and tables"
rather than silently lost.
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlsplit

import httpx
import trafilatura
from bs4 import BeautifulSoup, NavigableString, Tag

from .cache import Cache
from .config import Config
from .http_client import FetchResult, HttpPool
from .schemas import Extraction, utc_now_iso
from .security import UnsafeURLError, validate_url

MARKER = "\u27e6OMNI_ATOMIC_BLOCK_{:04d}\u27e7"
MARKER_RE = re.compile("\u27e6OMNI_ATOMIC_BLOCK_(\\d{4})\u27e7")

BOILER_TAGS = (
    "script", "style", "noscript", "nav", "footer", "aside", "form", "iframe",
    "svg", "canvas", "button", "select", "option", "template", "dialog", "menu",
)
BOILER_ATTR = re.compile(
    r"(cookie|consent|gdpr|newsletter|subscribe|advert|adsbygoogle|sponsor|promo|"
    r"share-|social|related-|recommend|comment|sidebar|breadcrumb|pagination|"
    r"paywall|modal|popup|overlay|site-header|site-footer|navbar|nav-menu|"
    r"skip-link|banner|toolbar|search-form)",
    re.I,
)
SPA_MARKERS = (
    'id="root"></div>', "id='root'></div>", 'id="__next"', 'id="app"></div>',
    'id="__nuxt"', "ng-version=", "data-reactroot", "hydrate-root",
)
WAF_MARKERS = (
    "just a moment", "verify you are human", "enable javascript and cookies",
    "attention required", "access denied", "checking your browser",
    "cf-chl", "captcha", "are you a robot", "request blocked",
    "unusual traffic", "ddos protection",
)
THIN_CHARS = 250
LANG_HINTS = (
    ("python", re.compile(r"^\s*(?:def |class |import |from |async def )", re.M)),
    ("javascript", re.compile(r"^\s*(?:const |let |var |function |import |export )", re.M)),
    ("typescript", re.compile(r"^\s*(?:interface |type |enum |const \w+:)", re.M)),
    ("rust", re.compile(r"^\s*(?:fn |let mut |impl |use |pub struct )", re.M)),
    ("go", re.compile(r"^\s*(?:func |package |type |import \()", re.M)),
    ("sql", re.compile(r"\b(?:SELECT|INSERT INTO|UPDATE|DELETE FROM)\b", re.I)),
    ("html", re.compile(r"^\s*<(?:!doctype|html|div|span)", re.I | re.M)),
    ("bash", re.compile(r"^\s*(?:sudo |apt |brew |npm |pip |uv |cargo |git )", re.M)),
    ("json", re.compile(r'^\s*[\[{]\s*"', re.M)),
)


@dataclass
class AtomicBlock:
    kind: str            # "code" | "table"
    markdown: str
    lang: str = ""


@dataclass
class Rendered:
    markdown: str = ""
    title: str = ""
    date: str = ""
    site: str = ""
    canonical: str = ""
    blocks_recovered: int = 0
    method: str = "trafilatura"
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Code / table rendering
# ---------------------------------------------------------------------------
def _fence_for(text: str) -> str:
    longest = 0
    run = 0
    for ch in text:
        if ch == "`":
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return "`" * max(3, longest + 1)


def _guess_lang(text: str, declared: str = "") -> str:
    if declared:
        return declared.lower()
    for name, pattern in LANG_HINTS:
        if pattern.search(text or ""):
            return name
    return ""


def _declared_lang(node: Tag) -> str:
    for candidate in [node, *node.find_all("code", limit=2)]:
        classes = candidate.get("class") or []
        if isinstance(classes, str):
            classes = [classes]
        for cls in classes:
            m = re.match(r"(?:language|lang|highlight|brush)[-:]([\w+#.-]+)", cls, re.I)
            if m:
                return m.group(1)
    return ""


def _render_code(pre: Tag) -> AtomicBlock:
    text = pre.get_text()
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    # Some highlighters emit one <span> per line with no newlines between them.
    if "\n" not in text and len(text) > 120:
        text = re.sub(r"(?<=[;{}])\s{2,}", "\n", text)
    if len(text) > 12000:
        text = text[:12000] + "\n# ... code truncated at 12,000 characters ..."
    lang = _guess_lang(text, _declared_lang(pre))
    fence = _fence_for(text)
    return AtomicBlock(kind="code", markdown=f"{fence}{lang}\n{text}\n{fence}", lang=lang)


def _cell_text(cell: Tag) -> str:
    text = cell.get_text(" ", strip=True)
    if cell.find(["pre", "code"]):
        text = cell.get_text("\n", strip=True)
    return re.sub(r"\s*\n\s*", "<br>", text).replace("|", "\\|").strip()


def _render_table(table: Tag) -> AtomicBlock:
    rows = table.find_all("tr")
    if not rows:
        return AtomicBlock(kind="table", markdown="")
    matrix: list[list[str]] = []
    header_is_th = False
    for row in rows[:80]:
        cells = row.find_all(["th", "td"])
        if not cells:
            continue
        if not matrix and all(c.name == "th" for c in cells):
            header_is_th = True
        matrix.append([_cell_text(c) for c in cells[:16]])
    if not matrix:
        return AtomicBlock(kind="table", markdown="")

    width = max(len(r) for r in matrix)
    matrix = [r + [""] * (width - len(r)) for r in matrix]
    if header_is_th:
        header, body = matrix[0], matrix[1:]
    else:
        header, body = [f"Column {i + 1}" for i in range(width)], matrix

    lines = ["| " + " | ".join(header) + " |",
             "| " + " | ".join("---" for _ in range(width)) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    if len(rows) > 80:
        lines.append("")
        lines.append(f"_Table truncated: {len(rows) - 80} additional rows omitted._")
    return AtomicBlock(kind="table", markdown="\n".join(lines))


def _protect_atomic(soup: BeautifulSoup) -> list[AtomicBlock]:
    """Replace code/table subtrees with sentinels; return rendered blocks."""
    blocks: list[AtomicBlock] = []

    def swap(node: Tag, block: AtomicBlock) -> None:
        if not block.markdown:
            node.decompose()
            return
        index = len(blocks)
        blocks.append(block)
        sentinel = soup.new_tag("p")
        sentinel.string = MARKER.format(index)
        node.replace_with(sentinel)

    # Tables first: a table may legally contain <code>.
    for table in list(soup.find_all("table")):
        swap(table, _render_table(table))
    for pre in list(soup.find_all("pre")):
        swap(pre, _render_code(pre))

    # Inline code outside pre: keep it inline with backticks.
    for code in list(soup.find_all("code")):
        if code.parent is None:
            continue
        text = code.get_text(" ", strip=True)
        if text:
            code.replace_with(NavigableString(f"`{text}`"))
        else:
            code.decompose()
    return blocks


def _drop_anchors(soup: BeautifulSoup) -> None:
    """Remove heading permalink anchors before text extraction."""
    pattern = re.compile(r"(headerlink|anchor-link|permalink|hash-link)", re.I)
    for node in list(soup.find_all("a", class_=pattern)):
        node.decompose()
    for node in list(soup.find_all(class_=pattern)):
        if node.parent is not None:
            node.decompose()


def _normalize_prose(text: str) -> str:
    """Collapse extractor whitespace artifacts without touching code fences."""
    out: list[str] = []
    in_fence = False
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.lstrip().startswith("```") or line.lstrip().startswith("~~~"):
            in_fence = not in_fence
            out.append(line.rstrip())
            continue
        if in_fence:
            out.append(line)
            continue
        cleaned = line.replace("\u00b6", "").strip()
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
        out.append(cleaned)
    joined = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", joined).strip()


def _remove_boilerplate(soup: BeautifulSoup) -> None:
    _drop_anchors(soup)
    for tag in list(soup.find_all(BOILER_TAGS)):
        if tag.parent is not None:
            tag.decompose()
    for tag in list(soup.find_all(True)):
        if tag.parent is None or tag.name in ("body", "main", "article", "html"):
            continue
        classes = tag.get("class") or []
        if isinstance(classes, str):
            classes = [classes]
        ident = " ".join([
            str(tag.get("id") or ""),
            " ".join(str(c) for c in classes),
            str(tag.get("role") or ""),
            str(tag.get("aria-label") or ""),
        ])
        if ident.strip() and BOILER_ATTR.search(ident):
            tag.decompose()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------
def _meta_value(soup: BeautifulSoup, *keys: str) -> str:
    for key in keys:
        node = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if node and node.get("content"):
            return str(node["content"]).strip()[:300]
    return ""


def extract_metadata(html: str, url: str) -> dict:
    meta = {"title": "", "date": "", "site": "", "canonical": ""}
    try:
        soup = BeautifulSoup(html or "", "lxml")
    except Exception:
        return meta
    title = _meta_value(soup, "og:title", "twitter:title")
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    if title:
        title = re.sub(r"\s+[|\u2013\u2014-]\s+[^|\u2013\u2014-]{2,40}$", "", title).strip()
    meta["title"] = title[:180]
    meta["date"] = _meta_value(
        soup, "article:published_time", "datePublished", "date", "pubdate",
        "publish-date", "og:updated_time",
    )[:40]
    if not meta["date"]:
        node = soup.find("time")
        if node is not None:
            meta["date"] = str(node.get("datetime") or node.get_text(" ", strip=True) or "")[:40]
    meta["site"] = _meta_value(soup, "og:site_name")[:80]
    canonical = soup.find("link", attrs={"rel": lambda v: v and "canonical" in v})
    if canonical is not None and canonical.get("href"):
        meta["canonical"] = str(canonical["href"]).strip()[:300]
    return meta


# ---------------------------------------------------------------------------
# DOM -> Markdown fallback
# ---------------------------------------------------------------------------
_BLOCK_TAGS = {"article", "main", "section", "div", "header", "figure", "figcaption",
               "details", "summary", "dl", "dt", "dd", "blockquote", "center"}
_SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "template", "iframe"}


def _inline_text(node) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag) or node.name in _SKIP_TAGS:
        return ""
    if node.name == "br":
        return "\n"
    if node.name == "img":
        alt = node.get("alt") or ""
        return f"![{alt}]({node.get('src', '')})" if alt else ""
    inner = "".join(_inline_text(child) for child in node.children)
    inner = re.sub(r"[ \t]+", " ", inner)
    if node.name in ("strong", "b") and inner.strip():
        return f"**{inner.strip()}**"
    if node.name in ("em", "i") and inner.strip():
        return f"*{inner.strip()}*"
    if node.name == "code" and inner.strip():
        return f"`{inner.strip()}`"
    if node.name == "a":
        href = str(node.get("href") or "")
        text = inner.strip()
        return text if not href.startswith("http") else text
    return inner


def _walk(node: Tag, out: list[str]) -> None:
    for child in node.children:
        if isinstance(child, NavigableString):
            text = str(child).strip()
            if text:
                out.append(text)
            continue
        if not isinstance(child, Tag) or child.name in _SKIP_TAGS:
            continue
        name = child.name
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = child.get_text(" ", strip=True)
            if text:
                out.append("#" * int(name[1]) + " " + text)
        elif name == "p":
            text = _inline_text(child).strip()
            if text:
                out.append(text)
        elif name in ("ul", "ol"):
            for li in child.find_all("li", recursive=False):
                text = _inline_text(li).strip()
                if text:
                    out.append(("- " if name == "ul" else "1. ") + text)
        elif name == "blockquote":
            text = child.get_text(" ", strip=True)
            if text:
                out.append("> " + text)
        elif name == "hr":
            out.append("---")
        elif name in ("table", "pre"):
            # Should have been replaced by a sentinel already; keep text as a
            # last resort so nothing is lost.
            out.append(child.get_text("\n", strip=True))
        elif name in _BLOCK_TAGS:
            _walk(child, out)
        else:
            text = _inline_text(child).strip()
            if text:
                out.append(text)


def _dom_markdown(html: str) -> str:
    soup = BeautifulSoup(html or "", "lxml")
    body = soup.body or soup
    best: Optional[Tag] = None
    best_score = 0.0
    for candidate in [body, *body.find_all(["article", "main", "section", "div"], limit=400)]:
        text = candidate.get_text(" ", strip=True)
        if len(text) < 120:
            continue
        link_text = sum(len(a.get_text(" ", strip=True)) for a in candidate.find_all("a"))
        density = len(text) - 1.6 * link_text
        if density > best_score:
            best_score = density
            best = candidate
    target = best or body
    out: list[str] = []
    _walk(target, out)
    text = "\n\n".join(p for p in out if p.strip())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ---------------------------------------------------------------------------
# Trafilatura + protection pipeline
# ---------------------------------------------------------------------------
def _postprocess_links(text: str) -> str:
    text = re.sub(r"\(https?://[^()\s]*\)", "", text)
    text = re.sub(r"\]\(", "](", text)
    text = text.replace("\\_", "_").replace("\\*", "*").replace("\\#", "#").replace("\\>", ">")
    text = text.replace("\\`", "`")
    text = MARKER_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _strip_front_matter(text: str) -> tuple[str, dict]:
    meta: dict = {}
    if not text.startswith("---"):
        return text, meta
    end = text.find("\n---", 3)
    if end <= 0:
        return text, meta
    for line in text[3:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().lower().strip('"')
            if key in ("title", "url", "date", "sitename", "canonical", "description"):
                meta[key] = value.strip().strip('"')[:300]
    return text[end + 4:], meta


def html_to_markdown(html: str, url: str = "") -> Rendered:
    """Convert raw HTML to clean Markdown with atomic blocks preserved."""
    if not html or not html.strip():
        return Rendered()

    meta = extract_metadata(html, url)
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return Rendered(markdown="", **(meta or {}), method="none")

    blocks = _protect_atomic(soup)
    _remove_boilerplate(soup)
    protected_html = str(soup)

    text = ""
    try:
        text = trafilatura.extract(
            protected_html,
            url=url or None,
            include_links=True,
            include_tables=False,
            include_images=False,
            include_comments=False,
            output_format="markdown",
            with_metadata=True,
        ) or ""
    except Exception:
        text = ""

    method = "trafilatura"
    found = [int(m) for m in MARKER_RE.findall(text)]
    missing = [i for i in range(len(blocks)) if i not in found]
    # Code/table fidelity beats prose completeness: if the extractor dropped
    # even one protected block, rebuild from the DOM where sentinels are intact.
    if not text.strip() or len(text.strip()) < THIN_CHARS or missing:
        fallback = _dom_markdown(protected_html)
        if fallback.strip():
            text = fallback
            method = "dom-readability"

    text, fm = _strip_front_matter(text)
    for key, value in fm.items():
        if not meta.get(key):
            meta[key] = value

    recovered = 0

    def restore(match: re.Match) -> str:
        nonlocal recovered
        idx = int(match.group(1))
        if 0 <= idx < len(blocks):
            return "\n\n" + blocks[idx].markdown + "\n\n"
        return ""

    text = MARKER_RE.sub(restore, text)
    still_missing = [
        i for i in range(len(blocks))
        if blocks[i].markdown and blocks[i].markdown not in text
    ]
    if still_missing:
        recovered = len(still_missing)
        appendix = ["", "## Recovered code and tables", ""]
        for idx in still_missing:
            appendix.append(blocks[idx].markdown)
            appendix.append("")
        text = (text.rstrip() + "\n" + "\n".join(appendix)).strip()

    text = _normalize_prose(_postprocess_links(text))
    return Rendered(
        markdown=text,
        title=meta.get("title", ""),
        date=meta.get("date", ""),
        site=meta.get("site", ""),
        canonical=meta.get("canonical", ""),
        blocks_recovered=recovered,
        method=method,
        meta=meta,
    )


# ---------------------------------------------------------------------------
# Quality detection
# ---------------------------------------------------------------------------
def detect_low_quality(status: int, html: str, markdown: str) -> str:
    """Return a machine reason when Tier 1 output must not be trusted."""
    if status in (401, 403, 407, 429, 503):
        return f"http_{status}"
    low_html = (html or "")[:40000].lower()
    for marker in WAF_MARKERS:
        if marker in low_html:
            return "waf_challenge"
    body = (markdown or "").strip()
    if len(body) < THIN_CHARS:
        if any(marker in low_html for marker in SPA_MARKERS):
            return "spa_shell"
        return "thin_text"
    # A 200 response whose only text is navigation is a JS shell in disguise.
    if len(html) > 60000 and len(body) < 800:
        return "spa_shell"
    return ""


# ---------------------------------------------------------------------------
# Tier 2: persistent stealth browser
# ---------------------------------------------------------------------------
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


class BrowserEngine:
    """Singleton warm Chromium. Started once, reused for every extraction."""

    def __init__(self, profile_dir: str, *, headless: bool = True,
                 timeout_ms: int = 25000, max_pages: int = 2):
        self.profile_dir = profile_dir
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.max_pages = max(1, max_pages)
        self._playwright = None
        self._context = None
        self._start_lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(self.max_pages)
        self._started = False
        self.last_error = ""

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> bool:
        if self._started:
            return True
        async with self._start_lock:
            if self._started:
                return True
            try:
                from playwright.async_api import async_playwright

                self._playwright = await async_playwright().start()
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=self.profile_dir,
                    headless=self.headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-features=Translate,BackForwardCache",
                    ],
                    user_agent=_BROWSER_UA,
                    locale="en-US",
                    viewport={"width": 1366, "height": 900},
                    java_script_enabled=True,
                    ignore_https_errors=True,
                )
                self._context.set_default_timeout(self.timeout_ms)
                await self._context.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                )
                await self._context.route("**/*", self._route)
                self._started = True
                self.last_error = ""
                return True
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"[:200]
                await self._safe_close()
                return False

    @staticmethod
    async def _route(route) -> None:
        try:
            if route.request.resource_type in ("image", "media", "font", "other"):
                await route.abort()
            else:
                await route.continue_()
        except Exception:
            try:
                await route.continue_()
            except Exception:
                pass

    async def fetch(self, url: str, *, allow_private: bool = False) -> tuple[int, str, str]:
        """Render a URL. Returns (status, html, final_url). Raises on failure."""
        validate_url(url, allow_private)
        if not await self.start():
            raise RuntimeError(f"browser unavailable: {self.last_error}")
        async with self._sem:
            page = await self._context.new_page()
            try:
                response = await page.goto(url, wait_until="domcontentloaded",
                                           timeout=self.timeout_ms)
                status = response.status if response is not None else 0
                previous = -1
                stable = 0
                for _ in range(24):
                    await page.wait_for_timeout(250)
                    length = await page.evaluate(
                        "() => document.body ? document.body.innerText.length : 0"
                    )
                    if length == previous:
                        stable += 1
                    else:
                        stable = 0
                        previous = length
                    if stable >= 3 and length > 200:
                        break
                html = await page.content()
                final_url = page.url
                # A redirect may have landed on an internal address; never
                # hand such content back to the caller.
                try:
                    validate_url(final_url, allow_private)
                except UnsafeURLError:
                    raise
                return status, html, final_url
            finally:
                try:
                    await page.close()
                except Exception:
                    pass

    async def _safe_close(self) -> None:
        self._started = False
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    async def close(self) -> None:
        async with self._start_lock:
            await self._safe_close()


# ---------------------------------------------------------------------------
# Tier 3: Tavily rescue
# ---------------------------------------------------------------------------
async def _tavily_extract(cfg: Config, url: str) -> tuple[str, str]:
    key = cfg.search.tavily_key
    if not key:
        raise RuntimeError("no Tavily key")
    from tavily import TavilyClient

    def run() -> tuple[str, str]:
        client = TavilyClient(api_key=key)
        result = client.extract(urls=[url], extract_depth="advanced")
        for item in result.get("results", []):
            content = item.get("raw_content") or ""
            if content.strip():
                return content, str(item.get("url") or url)
        failed = result.get("failed_results") or []
        raise RuntimeError(f"tavily extract failed: {str(failed)[:120]}")

    return await asyncio.to_thread(run)


# ---------------------------------------------------------------------------
# Public extractor
# ---------------------------------------------------------------------------
class TieredExtractor:
    def __init__(self, cfg: Config, pool: HttpPool, cache: Optional[Cache] = None,
                 browser: Optional[BrowserEngine] = None):
        self.cfg = cfg
        self.pool = pool
        self.cache = cache
        self.browser = browser
        self._cache_version = "ext5"

    def _cache_key(self, url: str) -> str:
        return f"{self._cache_version}|{url}"

    async def extract(self, url: str, *, query: str = "",
                      allow_tavily: bool = True,
                      timeout: Optional[float] = None) -> Extraction:
        t0 = time.perf_counter()
        key = self._cache_key(url)
        if self.cache is not None:
            cached = self.cache.get("extract", key, self.cfg.ttl_extract)
            if cached:
                try:
                    model = Extraction.model_validate(cached)
                    model.from_cache = True
                    model.elapsed_ms = int((time.perf_counter() - t0) * 1000)
                    return model
                except Exception:
                    pass

        reasons: list[str] = []
        http_status = 0

        # ---------------- Tier 1 ----------------
        try:
            fetched: FetchResult = await self.pool.fetch(
                url, timeout=timeout or self.cfg.http_timeout_fetch
            )
            http_status = fetched.status
            content_type = (fetched.content_type or "").lower()
            if "pdf" in content_type or content_type.startswith("image/") or "octet-stream" in content_type:
                return Extraction(url=url, final_url=fetched.url, status="unsupported_type",
                                  reason=f"content-type: {content_type.split(';')[0]}",
                                  http_status=fetched.status, tier=1,
                                  elapsed_ms=int((time.perf_counter() - t0) * 1000))
            rendered = html_to_markdown(fetched.text, fetched.url)
            reason = detect_low_quality(fetched.status, fetched.text, rendered.markdown)
            if not reason and rendered.markdown.strip():
                result = Extraction(
                    url=url, final_url=fetched.url, status="ok", tier=1,
                    markdown=rendered.markdown, title=rendered.title, date=rendered.date,
                    site=rendered.site, canonical=rendered.canonical,
                    http_status=fetched.status, bytes_read=fetched.size,
                    truncated=fetched.truncated,
                    elapsed_ms=int((time.perf_counter() - t0) * 1000),
                )
                self._store(key, result)
                return result
            reasons.append(f"tier1:{reason or 'empty'}")
        except UnsafeURLError as exc:
            return Extraction(url=url, status="blocked", reason=str(exc)[:160], tier=1,
                              elapsed_ms=int((time.perf_counter() - t0) * 1000))
        except httpx.TimeoutException:
            reasons.append("tier1:timeout")
        except httpx.ConnectError:
            reasons.append("tier1:connect")
        except (httpx.NetworkError, httpx.InvalidURL, ValueError) as exc:
            reasons.append(f"tier1:{type(exc).__name__}")
        except Exception as exc:
            reasons.append(f"tier1:{type(exc).__name__}")

        # ---------------- Tier 2 ----------------
        if self.browser is not None:
            try:
                status, html, final_url = await self.browser.fetch(
                    url, allow_private=self.cfg.allow_private_net
                )
                http_status = status or http_status
                rendered = html_to_markdown(html, final_url)
                if len(rendered.markdown.strip()) >= THIN_CHARS:
                    result = Extraction(
                        url=url, final_url=final_url, status="ok", tier=2,
                        markdown=rendered.markdown, title=rendered.title, date=rendered.date,
                        site=rendered.site, canonical=rendered.canonical,
                        http_status=status, bytes_read=len(html),
                        truncated=False,
                        elapsed_ms=int((time.perf_counter() - t0) * 1000),
                    )
                    self._store(key, result)
                    return result
                reasons.append(f"tier2:thin({len(rendered.markdown)}ch)")
            except UnsafeURLError as exc:
                return Extraction(url=url, status="blocked", reason=str(exc)[:160], tier=2,
                                  elapsed_ms=int((time.perf_counter() - t0) * 1000))
            except Exception as exc:
                reasons.append(f"tier2:{type(exc).__name__}:{str(exc)[:60]}")

        # ---------------- Tier 3 ----------------
        if allow_tavily and self.cfg.search.tavily_key:
            try:
                raw, final_url = await asyncio.wait_for(
                    _tavily_extract(self.cfg, url), timeout=25.0
                )
                rendered = html_to_markdown(raw, final_url) if "<" in raw[:400] else Rendered(markdown=raw)
                body = rendered.markdown or raw
                if len(body.strip()) >= THIN_CHARS:
                    meta = extract_metadata("", final_url)
                    result = Extraction(
                        url=url, final_url=final_url, status="ok", tier=3,
                        markdown=body, title=meta.get("title", ""), date=meta.get("date", ""),
                        site=urlsplit(final_url).hostname or "",
                        canonical=meta.get("canonical", ""),
                        http_status=http_status,
                        elapsed_ms=int((time.perf_counter() - t0) * 1000),
                    )
                    self._store(key, result)
                    return result
                reasons.append("tier3:thin")
            except asyncio.TimeoutError:
                reasons.append("tier3:timeout")
            except Exception as exc:
                reasons.append(f"tier3:{type(exc).__name__}")

        joined = "; ".join(reasons) or "no extraction tier produced content"
        if http_status in (401, 403, 407, 429, 503) or "waf" in joined:
            status = "blocked"
        elif "spa" in joined or "thin" in joined:
            status = "thin_content_js"
        elif "timeout" in joined or "connect" in joined:
            status = "unreachable"
        else:
            status = "no_content"
        return Extraction(
            url=url, status=status, reason=joined[:240], tier=0,
            http_status=http_status, elapsed_ms=int((time.perf_counter() - t0) * 1000),
        )

    def _store(self, key: str, result: Extraction) -> None:
        if self.cache is None:
            return
        try:
            self.cache.put("extract", key, result.model_dump())
        except Exception:
            pass

    async def extract_many(self, urls: list[str], *, query: str = "",
                           concurrency: int = 4,
                           allow_tavily: bool = True) -> list[Extraction]:
        sem = asyncio.Semaphore(max(1, concurrency))

        async def one(target: str) -> Extraction:
            async with sem:
                try:
                    return await self.extract(target, query=query, allow_tavily=allow_tavily)
                except Exception as exc:
                    return Extraction(url=target, status="error",
                                      reason=f"{type(exc).__name__}: {exc}"[:160])

        return list(await asyncio.gather(*(one(u) for u in urls)))


def fetched_at_now() -> str:
    return utc_now_iso()
