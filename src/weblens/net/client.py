"""Bounded, SSRF-safe HTTP fetching with streaming size caps and redirect checks."""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from ..cache import Cache, cache_key
from ..config import Settings
from ..errors import ErrCode, FetchError
from ..urls import decode_bing_redirect, host_of, normalize_url
from .ssrf import DestinationPolicy, SafeNetworkBackend

REDIRECT_CODES = {301, 302, 303, 307, 308}
RETRY_CODES = {429, 502, 503, 504}


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _charset(content_type: str) -> str:
    for part in content_type.split(";")[1:]:
        k, _, v = part.strip().partition("=")
        if k.lower() == "charset" and v:
            return v.strip("\"'")
    return "utf-8"


def _decode(body: bytes, content_type: str) -> str:
    enc = _charset(content_type)
    try:
        return body.decode(enc, "replace")
    except LookupError:
        return body.decode("utf-8", "replace")


def _auth_fingerprint(headers: dict[str, str] | None) -> str:
    if not headers:
        return ""
    for k, v in headers.items():
        if k.lower() == "authorization":
            return hashlib.sha256(v.encode("utf-8")).hexdigest()
    return ""


@dataclass
class FetchResponse:
    url: str
    final_url: str
    status: int
    headers: dict[str, str]
    body: bytes
    fetched_at: str
    from_cache: bool = False
    truncated: bool = False
    sha256: str = ""
    redirects: list[str] = field(default_factory=list)

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").lower()

    @property
    def text(self) -> str:
        return _decode(self.body, self.content_type)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self) -> Any:
        import json

        return json.loads(self.body.decode("utf-8", "replace"))

    @property
    def media_kind(self) -> str:
        ct = self.content_type
        if "pdf" in ct:
            return "pdf"
        if "html" in ct or "xhtml" in ct:
            return "html"
        if ct.startswith("text/plain") or "markdown" in ct:
            return "text"
        if "json" in ct or "xml" in ct:
            return "data"
        return "binary"


class SafeFetcher:
    def __init__(self, settings: Settings, cache: Cache):
        self.s = settings
        self.cache = cache
        self.policy = DestinationPolicy(settings)
        limits = httpx.Limits(
            max_connections=settings.max_concurrency * 2,
            max_keepalive_connections=settings.max_concurrency,
            keepalive_expiry=60.0,
        )
        self._client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(
                connect=settings.connect_timeout_s,
                read=settings.read_timeout_s,
                write=settings.read_timeout_s,
                pool=settings.connect_timeout_s,
            ),
            limits=limits,
            http2=True,
            trust_env=False,
            headers={
                "User-Agent": settings.user_agent,
                "Accept-Language": settings.accept_language,
                "Accept": "text/html,application/xhtml+xml,application/pdf,text/plain;q=0.9,*/*;q=0.5",
            },
        )
        # Swap in the policy-enforcing backend. httpcore's pool keeps TLS SNI
        # tied to the request origin, so connecting to the validated IP is safe.
        self._client._transport._pool._network_backend = SafeNetworkBackend(self.policy)  # type: ignore[attr-defined]
        self._global = asyncio.Semaphore(settings.max_concurrency)
        self._per_host: dict[str, asyncio.Semaphore] = {}
        self._host_lock = asyncio.Lock()

    async def _host_sem(self, host: str) -> asyncio.Semaphore:
        async with self._host_lock:
            sem = self._per_host.get(host)
            if sem is None:
                sem = asyncio.Semaphore(self.s.per_host_concurrency)
                self._per_host[host] = sem
            return sem

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        max_bytes: int | None = None,
        cache_ttl: float | None = None,
        max_redirects: int | None = None,
        use_cache: bool = True,
        method: str = "GET",
        json_body: Any | None = None,
        content: bytes | None = None,
    ) -> FetchResponse:
        started = time.perf_counter()
        limit = max_bytes or self.s.max_response_bytes
        hops: list[str] = []
        current = normalize_url(decode_bing_redirect(url))
        if not current:
            raise FetchError("invalid or disallowed URL", code=ErrCode.BAD_INPUT)
        redirects = self.s.max_redirects if max_redirects is None else max_redirects
        req_body = content
        if json_body is not None:
            import json as _json

            req_body = _json.dumps(json_body, separators=(",", ":")).encode()
            headers = {**(headers or {}), "Content-Type": "application/json"}

        auth_fp = _auth_fingerprint(headers)
        for _hop in range(redirects + 1):
            self.policy.check_hostname(host_of(current))
            key = cache_key("http", method.upper(), current, auth_fp, (req_body or b"").decode("utf-8", "replace"))
            cached: FetchResponse | None = None
            if use_cache and self.cache.s.cache_enabled:
                got = await self.cache.get(key)
                if got is not None:
                    body, meta, created = got
                    age = time.time() - created
                    ttl = cache_ttl if cache_ttl is not None else self.s.page_cache_ttl_s
                    cached = FetchResponse(
                        url=current,
                        final_url=str(meta.get("final_url", current)),
                        status=int(meta.get("status", 200)),
                        headers=dict(meta.get("headers", {})),
                        body=body,
                        fetched_at=str(meta.get("fetched_at", utc_now_iso())),
                        from_cache=True,
                        truncated=bool(meta.get("truncated", False)),
                        sha256=hashlib.sha256(body).hexdigest(),
                    )
                    if age < ttl:
                        cached.redirects = list(meta.get("redirects", []))
                        return cached

            req_headers = dict(headers or {})
            if cached is not None:
                etag = cached.headers.get("etag")
                lm = cached.headers.get("last-modified")
                if etag:
                    req_headers["If-None-Match"] = etag
                if lm:
                    req_headers["If-Modified-Since"] = lm

            resp = await self._request_once(current, req_headers, limit, method.upper(), req_body)
            if resp.status == 304 and cached is not None:
                cached.from_cache = True
                cached.fetched_at = utc_now_iso()
                await self.cache.set(
                    key,
                    cached.body,
                    {
                        "kind": "http",
                        "final_url": cached.final_url,
                        "status": cached.status,
                        "headers": cached.headers,
                        "fetched_at": cached.fetched_at,
                        "truncated": cached.truncated,
                        "redirects": hops,
                    },
                    cache_ttl or self.s.page_cache_ttl_s,
                )
                return cached

            location = resp.headers.get("location")
            if resp.status in REDIRECT_CODES and location:
                nxt = normalize_url(location, base=current)
                if not nxt:
                    raise FetchError(
                        f"redirect to disallowed URL: {location[:100]}", code=ErrCode.BLOCKED_URL
                    )
                if nxt in hops:
                    raise FetchError("redirect loop", code=ErrCode.HTTP)
                hops.append(current)
                current = nxt
                continue

            if not resp.ok:
                code = ErrCode.HTTP
                raise FetchError(
                    f"HTTP {resp.status} for {current}",
                    code=code,
                    retryable=resp.status in RETRY_CODES,
                )

            resp.redirects = hops
            resp.final_url = current
            if use_cache and self.cache.s.cache_enabled and resp.status == 200:
                await self.cache.set(
                    key,
                    resp.body,
                    {
                        "kind": "http",
                        "final_url": current,
                        "status": resp.status,
                        "headers": {
                            k: v
                            for k, v in resp.headers.items()
                            if k.lower() in {"content-type", "etag", "last-modified", "cache-control"}
                        },
                        "fetched_at": resp.fetched_at,
                        "truncated": resp.truncated,
                        "redirects": hops,
                    },
                    cache_ttl or self.s.page_cache_ttl_s,
                )
            _ = time.perf_counter() - started
            return resp

        raise FetchError("too many redirects", code=ErrCode.HTTP)

    async def _request_once(
        self,
        url: str,
        headers: dict[str, str],
        limit: int,
        method: str = "GET",
        body: bytes | None = None,
    ) -> FetchResponse:
        host = host_of(url)
        assert host
        for attempt in range(2):
            async with self._global, await self._host_sem(host):
                try:
                    async with self._client.stream(method, url, headers=headers, content=body) as r:
                        cl = r.headers.get("content-length")
                        if cl and cl.isdigit() and int(cl) > limit:
                            raise FetchError(
                                f"response too large ({cl} bytes)", code=ErrCode.TOO_LARGE
                            )
                        chunks: list[bytes] = []
                        total = 0
                        truncated = False
                        async for chunk in r.aiter_bytes(65_536):
                            total += len(chunk)
                            if total > limit:
                                cut = len(chunk) - (total - limit)
                                if cut > 0:
                                    chunks.append(chunk[:cut])
                                truncated = True
                                break
                            chunks.append(chunk)
                        body = b"".join(chunks)
                        hdrs = {k.lower(): v for k, v in r.headers.items()}
                        return FetchResponse(
                            url=url,
                            final_url=url,
                            status=r.status_code,
                            headers=hdrs,
                            body=body,
                            fetched_at=utc_now_iso(),
                            truncated=truncated,
                            sha256=hashlib.sha256(body).hexdigest(),
                        )
                except httpx.TimeoutException as e:
                    if attempt == 0:
                        continue
                    raise FetchError(f"timeout fetching {host}", code=ErrCode.TIMEOUT) from e
                except httpx.HTTPError as e:
                    if attempt == 0:
                        continue
                    raise FetchError(f"network error fetching {host}: {e}", code=ErrCode.HTTP) from e
        raise FetchError(f"failed to fetch {host}", code=ErrCode.HTTP)

    async def fetch_text(self, url: str, **kw: Any) -> tuple[str, FetchResponse]:
        r = await self.fetch(url, **kw)
        return r.text, r
