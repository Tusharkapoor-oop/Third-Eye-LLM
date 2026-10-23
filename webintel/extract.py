"""Extraction pipeline: fetch -> main-content extraction (trafilatura) -> chunk
-> score vs query -> top chunks within token budget. Every returned chunk is a
verbatim span of the page, attached to url + fetch timestamp (R2).

Full-page mode only on explicit request (full=true), capped by max_tokens.
PDFs/binary are refused with an explicit status (no hidden damage).
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import httpx
import trafilatura

from .limits import TokenBudget, estimate_tokens, json_tokens
from .ranking import score_chunks, registrable_domain
from .security import UnsafeURLError
from .utils import dumps, query_tokens, sha256, normalize_text, dedup_by

_MAX_CHUNK_TOKENS = 220      # a chunk bigger than this is unusable for R1 anyway
_CHUNK_MAX_WORDS = 150
_CHUNK_OVERLAP_WORDS = 18
EXTRACT_CACHE_VERSION = "v4"  # bump when extraction/ranking semantics change

_EXTRACT_STATUSES = ("ok", "no_content", "thin_content_js", "blocked", "unreachable",
                     "unsupported_type", "error")

PP = re.compile(r"\n{2,}")


@dataclass
class Chunk:
    span: str
    section: str = ""


def _split_blocks(text: str) -> Tuple[List[str], List[str]]:
    """Split extracted markdown/plain text into blocks; headings become section context."""
    lines: List[str] = [l for l in text.split("\n") if l.strip()]
    blocks: List[str] = []
    sections: List[str] = []
    cur: List[str] = []
    cur_h = ""
    words = 0
    started_list_block = False
    for line in lines:
        is_heading = line.lstrip().startswith("#")
        if is_heading and cur:
            blocks.append("\n".join(cur).strip())
            sections.append(cur_h or "top")
            cur, words = [], 0
        if is_heading:
            cur_h = line.lstrip("#").strip()
            continue
        toks = len(line.split())
        if cur and words + toks > _CHUNK_MAX_WORDS:
            blocks.append("\n".join(cur).strip())
            sections.append(cur_h or "top")
            cur, words = [], 0
        cur.append(line)
        words += toks
    if cur:
        blocks.append("\n".join(cur).strip())
        sections.append(cur_h or "top")
    return blocks, sections


def extract_batches(blocks: List[str], sections: List[str]) -> List[Chunk]:
    out = dedup_by(
        (Chunk(span=b, section=s) for b, s in zip(blocks, sections)),
        key=lambda c: sha256(normalize_text(c.span)),
    )
    return list(out)


def extract_main_content(html: str, url: str, *, full: bool = False) -> Tuple[Optional[str], dict]:
    """Single trafilatura pass (measured: alternatives covered in docs/research.md).
    Markdown output keeps heading structure; embedded YAML front matter is parsed
    for metadata and stripped from the text (one parse, not two)."""
    meta: dict = {}
    try:
        doc = trafilatura.extract(html or "", url=url,
                                  include_links=True, include_tables=True,
                                  include_images=False, include_comments=False,
                                  output_format="markdown", with_metadata=True)
    except Exception:
        doc = None
    if not doc:
        return None, meta
    # strip front matter and harvest metadata from it
    text = doc
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            for line in text[3:end].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip().lower().strip('"')
                    if k in ("title", "url", "date", "sitename", "canonical", "description"):
                        meta[k] = v.strip().strip('"')[:200]
            text = text[end + 4:]
    # post-process: deterministic cleanup - keep link TEXT, drop parenthesized
    # hrefs, unescape markdown escapes. Improves matching and legibility.
    text = re.sub(r"\(https?://[^()\s]*\)", "", text)
    text = re.sub(r"\]\(", ")", text)
    text = text.replace("\\_", "_").replace("\\*", "*").replace("\\#", "#").replace("\\>", ">")
    return text.strip(), meta


_THIN_THRESHOLD_CHARS = 400


async def extract_url(pool, cache, cfg, url: str, *, query: Optional[str] = None,
                      full: bool = False, max_tokens: int = 1500,
                      top_k: int = 8, timeout: Optional[float] = None) -> dict:
    """The MCP-masked workhorse. Returns compact JSON-able dict."""
    t0 = time.perf_counter()
    cache_key = f"{EXTRACT_CACHE_VERSION}|{url}|q={query or ''}|f={int(full)}|b={max_tokens}"
    cached = cache.get("extract", cache_key, cfg.ttl_extract) if cache else None
    if cached is not None:
        cached = dict(cached)
        cached["fetch_ms"] = round((time.perf_counter() - t0) * 1000)
        cached["cached"] = True
        return cached

    from .http_client import FetchResult
    try:
        fetch: FetchResult = await pool.fetch(url, timeout=timeout or cfg.http_timeout_fetch)
    except UnsafeURLError as e:
        # Must precede the ValueError clause: UnsafeURLError subclasses ValueError
        return _status_out(url, "blocked", str(e)[:80], t0, query)
    except httpx.TimeoutException:
        return _status_out(url, "unreachable", "timeout", t0, query)
    except httpx.ConnectError as e:
        return _status_out(url, "unreachable", f"connect: {type(e).__name__}", t0, query)
    except (httpx.NetworkError, httpx.InvalidURL, ValueError) as e:
        return _status_out(url, "unreachable", type(e).__name__, t0, query)

    ct = (fetch.content_type or "").lower()
    if "pdf" in ct or ct.startswith("image/") or "octet-stream" in ct:
        return _status_out(url, "unsupported_type", f"content-type: {ct.split(';')[0]}", t0, query,
                           final_url=fetch.url)

    if fetch.status in (401, 402, 403):
        return _status_out(url, "blocked", f"HTTP {fetch.status}", t0, query,
                           final_url=fetch.url)
    if fetch.status >= 500:
        return _status_out(url, "unreachable", f"HTTP {fetch.status}", t0, query,
                           final_url=fetch.url)
    if fetch.status != 200:
        # some sites: 204 etc
        return _status_out(url, "unreachable", f"HTTP {fetch.status}", t0, query,
                           final_url=fetch.url)

    html = fetch.text

    # cache raw for cheap re-chunking (bounded)
    if cache and len(html) <= cfg.max_response_bytes:
        cache.put("raw", sha256(fetch.url), {"charset": "utf-8", "t": html[: cfg.max_response_bytes],
                                             "ts": time.time()})
    text, meta = extract_main_content(html, fetch.url)
    if not text or len(text.strip()) < _THIN_THRESHOLD_CHARS:
        if len(html) > 20_000 and len(text or "") < _THIN_THRESHOLD_CHARS:
            out = _status_out(url, "thin_content_js",
                              "main extractor found <400 chars; page may need JS rendering "
                              "(set WEBINTEL_JS_RENDER=1 with playwright installed for fallback). "
                              "Content was not returned because it would mislead.", t0, query,
                              final_url=fetch.url)
            out["thin"] = True
            out["raw_len"] = len(html)
            out["picked_ms"] = round((time.perf_counter() - t0) * 1000)
            return out
        return _status_out(url, "no_content", "no main content extractable", t0, query,
                           final_url=fetch.url)

    blocks, sections = _split_blocks(text)
    chunks = extract_batches(blocks, sections) if query else [
        Chunk(span=b, section=s) for b, s in zip(blocks, sections)]

    selected: List[Chunk] = []
    if not full:
        if query:
            scores = score_chunks([c.span for c in chunks], query, sections)
            order = sorted(range(len(chunks)), key=lambda i: -scores[i])
        else:
            order = range(len(chunks))
        budget = TokenBudget(max_tokens)
        # envelope tokens estimated inside loop below
        envelope = {"u": url, "fetched_at": "", "status": "ok", "t": (meta.get("title") or "")[:140],
                    "date": (meta.get("date") or "")[:32], "canon": (meta.get("canonical") or "")[:200],
                    "site": (meta.get("sitename") or "")[:80]}
        env_tokens = json_tokens(envelope) + 30
        for i in order:
            c = chunks[i]
            item = {
                "x": c.span,
                "sec": c.section if c.section not in ("", "top") else None,
            }
            tk = json_tokens(item)
            if budget.used + env_tokens + tk > max_tokens or len(selected) >= top_k:
                break
            selected.append(c)
            budget.admit("", est=tk)
        out = {
            "u": fetch.url if fetch.redirected else url,
            "status": "ok",
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "x": [{"sec": ch.section if ch.section not in ("", "top") else "",
                   "span": ch.span} for ch in selected],
            "note": "x = exact spans (verbatim, query-scored; empty sec = top-of-page)."
                    " Field t/others follow only if present above."
        }
        if meta.get("title"):
            out["t"] = meta["title"][:140]
        if meta.get("date"):
            # reject crawl-date as a fact (R2): a date equal to today's fetch date is
            # usually the extractor's fallback, not the page's publication date.
            if meta["date"] != out["fetched_at"][:10]:
                out["date"] = meta["date"][:32]
        if meta.get("canonical") and meta["canonical"] != out["u"]:
            out["canon"] = meta["canonical"][:200]
        if meta.get("sitename"):
            out["site"] = meta["sitename"][:80]
    else:
        pages = trafilatura.extract(html, url=fetch.url, include_links=False, include_tables=True,
                                    include_comments=False, output_format="txt") or ""
        from .limits import trim_text
        trimmed = trim_text(pages, max_tokens)
        out = {
            "u": fetch.url if fetch.redirected else url,
            "status": "ok",
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "full": trimmed,
            "note": "full=true; entire main content trimmed to max_tokens.",
        }
        if meta.get("title"):
            out["t"] = meta["title"][:140]
        if meta.get("date"):
            out["date"] = meta["date"][:32]

    out["ms"] = round((time.perf_counter() - t0) * 1000)
    if cache:
        cache.put("extract", cache_key, out)
    return out


def _status_out(url: str, status: str, detail: str, t0: float, query: Optional[str],
                final_url: Optional[str] = None) -> dict:
    out = {
        "u": final_url or url,
        "status": status,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": detail[:160],
        "ms": round((time.perf_counter() - t0) * 1000),
    }
    return out
