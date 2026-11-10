"""Pooled HTTP layer: one shared AsyncClient (keepalive, HTTP/2 off, cap sizes),
manual redirect handling with per-hop re-validation, streaming byte cap. Third
parties (bench/tests) inject a transport to test without network."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import AsyncIterator, Dict, Optional, Tuple

import httpx

from .config import Config
from .security import check_host, validate_url, UnsafeURLError

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
_BROWSER_CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
_HEADERS: Dict[str, str] = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8;q=0.9,*/*;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
}


@dataclass
class FetchResult:
    url: str                 # final URL after redirects
    status: int
    content_type: str
    headers: Dict[str, str]
    text: str                # decoded
    size: int                # downloaded bytes (capped)
    elapsed_ms: float
    truncated: bool
    redirected: bool
    hrefs: Optional[list] = None
    title: Optional[str] = None


class HttpPool:
    def __init__(self, cfg: Config, client: Optional[httpx.AsyncClient] = None):
        self._cfg = cfg
        limits = httpx.Limits(max_keepalive_connections=cfg.max_concurrency,
                              max_connections=cfg.max_concurrency * 2,
                              keepalive_expiry=30.0)
        self._client = client or httpx.AsyncClient(
            headers=_HEADERS,
            limits=limits,
            follow_redirects=False,               # we handle hops ourselves (must re-validate)
            timeout=httpx.Timeout(connect=min(cfg.http_timeout_fetch, 6.0),
                                  read=cfg.http_timeout_fetch,
                                  write=cfg.http_timeout_fetch,
                                  pool=5.0),
            verify=True,
        )
        self._sem = asyncio.Semaphore(cfg.max_concurrency)

    @property
    def client(self) -> httpx.AsyncClient:
        return self._client

    async def aclose(self):
        close = getattr(self._client, "aclose", None)
        if close is not None:      # tolerate injected fake transports in tests/bench
            await close()

    async def fetch(self, url: str, *, timeout: Optional[float] = None,
                    max_bytes: Optional[int] = None,
                    text_only: bool = True) -> FetchResult:
        """Fetch with SSRF re-validation on every redirect hop and a hard size cap.
        Raises httpx.TimeoutException / ConnectError on transport failure;
        UnsafeURLError if a hop/target fails the security contract."""
        cfg = self._cfg
        for _ in range(3):
            try:
                return await self._fetch_one(url, timeout, max_bytes, text_only)
            except httpx.NetworkError as e:
                # transient network-level retry (idempotent GET)
                await get_sleep(_backoff())
                last_err: Optional[Exception] = e
            except httpx.HTTPStatusError:
                raise
        raise last_err  # type: ignore[misc]

    async def _fetch_one(self, url: str, timeout: Optional[float], max_bytes: Optional[int],
                         text_only: bool) -> FetchResult:
        cfg = self._cfg
        t0 = time.perf_counter()
        current = validate_url(url, cfg.allow_private_net)
        rurl = current
        redirected = False
        status = 0
        headers: Dict[str, str] = {}
        content_type = ""
        hops = cfg.max_redirects

        async with self._sem:
            for hop in range(hops + 1):
                # security re-check at connection time of THIS hop
                validate_url(rurl, cfg.allow_private_net)
                resp = await self._client.get(rurl, timeout=httpx.Timeout(
                    connect=5.0, read=timeout or cfg.http_timeout_fetch,
                    write=timeout or cfg.http_timeout_fetch, pool=5.0))
                status = resp.status_code
                headers = {k.lower(): v for k, v in resp.headers.items()}
                content_type = headers.get("content-type", "")
                if status in (301, 302, 303, 307, 308):
                    loc = headers.get("location")
                    if not loc:
                        break
                    from urllib.parse import urljoin
                    nxt = urljoin(rurl, loc).split("#")[0]
                    validate_url(nxt, cfg.allow_private_net)
                    rurl = nxt
                    redirected = True
                    continue
                break

        t0_stream = time.perf_counter()
        cap = max_bytes or cfg.max_response_bytes
        data = bytearray()
        truncated = False
        gzip_forced = False
        async for chunk in resp.aiter_bytes(65536):
            data.extend(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
            if len(data) >= cap:
                data = data[:cap]
                truncated = True
                break
        encoding = headers.get("content-encoding", "")
        text = ""
        if text_only:
            text = decode_response(bytes(data), headers.get("content-type", ""))
            if truncated and not text:  # decode failed mid-path on truncated body
                text = decode_response(bytes(data[: cap // 2]), headers.get("content-type", ""))
        elapsed = (time.perf_counter() - t0) * 1000
        return FetchResult(url=rurl, status=status, content_type=content_type,
                           headers=headers, text=text, size=len(data),
                           elapsed_ms=elapsed, truncated=truncated,
                           redirected=redirected)


_BAD_FWD_DECT = {"deflate": 1}


def _backoff() -> float:
    return 0.25


async def get_sleep(seconds: float):
    await asyncio.sleep(seconds)


def decode_response(body: bytes, content_type: str) -> str:
    """Decode response body using declared charset, then BOM sniff, then UTF-8."""
    cs = None
    for part in (content_type or "").split(";"):
        part = part.strip().lower()
        if part.startswith("charset="):
            cs = part.split("=")[1].strip().strip('"')
            break
    try:
        if not cs:
            if body.startswith(b"\xef\xbb\xbf"):
                cs = "utf-8"
            else:
                cs = "utf-8"
        return body.decode(cs or "utf-8", errors="replace")
    except (LookupError, UnicodeError):
        return body.decode("utf-8", errors="replace")
