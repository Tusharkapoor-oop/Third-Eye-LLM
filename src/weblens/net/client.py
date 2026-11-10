"""Bounded, SSRF-safe HTTP fetching with streaming size caps and redirect checks."""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from ..cache import Cache, cache_key
from ..config import Settings
from ..errors import ErrCode, FetchError
from ..urls import decode_bing_redirect, host_of, normalize_url
from .ssrf import DestinationPolicy, SafeNetworkBackend

REDIRECT_CODES = {301, 302, 303, 307, 308}
RETRY_CODES = {429, 502, 503, 504}


def _stale_eligible(fetch_err: FetchError) -> bool:
    """Only transient failures may be answered from the stale cache.

    A 404/403 or a blocked/too-large response is a real answer, not a network
    accident, so it must not be masked by old content.
    """
    return fetch_err.code == ErrCode.TIMEOUT or fetch_err.retryable


def _mark_stale(resp: FetchResponse, created: float) -> FetchResponse:
    resp.stale = True
    resp.from_cache = True
    resp.stale_age_s = max(0.0, time.time() - created)
    return resp


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


# Header names that carry caller credentials and must never cross an origin
# boundary on a redirect. Search-provider API keys travel in these.
_CREDENTIAL_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "x-subscription-token",
        "x-api-key",
        "api-key",
        "cookie",
    }
)


def _origin_of(url: str) -> tuple[str, str, int] | None:
    """(scheme, host, port) with default ports resolved, or None if unparseable."""
    try:
        parsed = urlsplit(url)
        scheme = (parsed.scheme or "").lower()
        host = (parsed.hostname or "").lower()
        port = parsed.port
        if port is None:
            port = 443 if scheme == "https" else 80
        return scheme, host, port
    except (ValueError, AttributeError):
        return None


def _same_origin(a: str, b: str) -> bool:
    """True only when both URLs share scheme, host and port."""
    oa, ob = _origin_of(a), _origin_of(b)
    return oa is not None and oa == ob


def _strip_credentials(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of ``headers`` without credential-bearing entries."""
    return {k: v for k, v in headers.items() if k.lower() not in _CREDENTIAL_HEADERS}


# Query parameters that routinely carry API keys. Providers such as Stack
# Exchange put their key in the URL, so the URL itself must be redacted before it
# is written to the on-disk cache or interpolated into an error message.
_SECRET_QUERY_PARAMS = frozenset(
    {
        "key",
        "api_key",
        "apikey",
        "access_token",
        "token",
        "secret",
        "client_secret",
        "password",
        "auth",
        "sig",
        "signature",
    }
)


def redact_url(url: str) -> str:
    """Return ``url`` with secret-looking query values replaced by ``REDACTED``.

    Used anywhere a URL can be persisted or surfaced (cache metadata, error text,
    logs). Failure to parse leaves the URL untouched rather than raising, because
    redaction must never break a fetch.
    """
    try:
        parsed = urlsplit(url)
    except (ValueError, AttributeError):
        return url
    if not parsed.query:
        return url
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
    except ValueError:
        return url
    if not any(k.lower() in _SECRET_QUERY_PARAMS for k, _ in pairs):
        return url
    redacted = [
        (k, "REDACTED" if k.lower() in _SECRET_QUERY_PARAMS else v) for k, v in pairs
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(redacted), parsed.fragment))


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
    # True when a failed live fetch was answered from an expired cache entry.
    # ``fetched_at`` deliberately keeps the original fetch time.
    stale: bool = False
    stale_age_s: float = 0.0
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
        self._client = self._new_client(settings, limits, http2=True)
        # Some origins (notably Yahoo Search) reset HTTP/2 streams immediately.
        # Keep a second connection pool that speaks HTTP/1.1 and fall back to it
        # only after a protocol-level failure, so a broken h2 endpoint does not
        # turn into a provider-wide outage.
        self._client_h1 = self._new_client(settings, limits, http2=False)
        self._global = asyncio.Semaphore(settings.max_concurrency)
        self._per_host: dict[str, asyncio.Semaphore] = {}
        self._host_lock = asyncio.Lock()

    def _new_client(self, settings: Settings, limits: httpx.Limits, *, http2: bool) -> httpx.AsyncClient:
        client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(
                connect=settings.connect_timeout_s,
                read=settings.read_timeout_s,
                write=settings.read_timeout_s,
                pool=settings.connect_timeout_s,
            ),
            limits=limits,
            http2=http2,
            trust_env=False,
            headers={
                "User-Agent": settings.user_agent,
                "Accept-Language": settings.accept_language,
                "Accept": "text/html,application/xhtml+xml,application/pdf,text/plain;q=0.9,*/*;q=0.5",
            },
        )
        # Swap in the policy-enforcing backend. httpcore's pool keeps TLS SNI
        # tied to the request origin, so connecting to the validated IP is safe.
        client._transport._pool._network_backend = SafeNetworkBackend(self.policy)  # type: ignore[attr-defined]
        return client

    async def _host_sem(self, host: str) -> asyncio.Semaphore:
        async with self._host_lock:
            sem = self._per_host.get(host)
            if sem is None:
                sem = asyncio.Semaphore(self.s.per_host_concurrency)
                self._per_host[host] = sem
            return sem

    async def close(self) -> None:
        await asyncio.gather(self._client.aclose(), self._client_h1.aclose())

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
        timeout_s: float | None = None,
        stale_ok: bool = False,
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

        budget = self.s.total_timeout_s if timeout_s is None else timeout_s
        deadline = time.monotonic() + budget if budget and budget > 0 else None
        auth_fp = _auth_fingerprint(headers)
        for _hop in range(redirects + 1):
            self.policy.check_hostname(host_of(current))
            key = cache_key("http", method.upper(), current, auth_fp, (req_body or b"").decode("utf-8", "replace"))
            cached_resp: FetchResponse | None = None
            stale_resp: FetchResponse | None = None
            stale_created = 0.0
            if use_cache and self.cache.s.cache_enabled:
                got = await self.cache.get_cached(key, self.s.cache_stale_grace_s)
                if got is not None:
                    body, meta, created, expired = got
                    age = time.time() - created
                    ttl = cache_ttl if cache_ttl is not None else self.s.page_cache_ttl_s
                    cached_resp = FetchResponse(
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
                    if not expired and age < ttl:
                        cached_resp.redirects = list(meta.get("redirects", []))
                        return cached_resp
                    # Keep the expired copy as a fallback only for page-like
                    # GET requests. Search provider APIs and POSTs must see the
                    # real failure so they can fail over to another provider.
                    if stale_ok and method.upper() == "GET" and ttl > 0:
                        stale_resp = cached_resp
                        stale_created = created

            req_headers = dict(headers or {})
            if cached_resp is not None:
                etag = cached_resp.headers.get("etag")
                lm = cached_resp.headers.get("last-modified")
                if etag:
                    req_headers["If-None-Match"] = etag
                if lm:
                    req_headers["If-Modified-Since"] = lm

            try:
                resp = await self._request_once(
                    current,
                    req_headers,
                    limit,
                    method.upper(),
                    req_body,
                    deadline=deadline,
                )
            except FetchError as exc:
                if stale_resp is not None and _stale_eligible(exc):
                    return _mark_stale(stale_resp, stale_created)
                raise

            if resp.status == 304 and cached_resp is not None:
                cached_resp.from_cache = True
                cached_resp.fetched_at = utc_now_iso()
                await self.cache.set(
                    key,
                    cached_resp.body,
                    {
                        "kind": "http",
                        "final_url": redact_url(cached_resp.final_url),
                        "status": cached_resp.status,
                        "headers": cached_resp.headers,
                        "fetched_at": cached_resp.fetched_at,
                        "truncated": cached_resp.truncated,
                        "redirects": hops,
                    },
                    cache_ttl or self.s.page_cache_ttl_s,
                )
                return cached_resp

            location = resp.headers.get("location")
            if resp.status in REDIRECT_CODES and location:
                nxt = normalize_url(location, base=current)
                if not nxt:
                    raise FetchError(f"redirect to disallowed URL: {location[:100]}", code=ErrCode.BLOCKED_URL)
                if nxt in hops:
                    raise FetchError("redirect loop", code=ErrCode.HTTP)
                # Caller credentials (Tavily's Authorization, Brave's
                # X-Subscription-Token) must not follow a redirect to a different
                # origin. httpx drops Authorization on cross-host redirects;
                # this loop is hand-rolled and previously did not, so a 30x from
                # an API host -- or one injected via a misconfigured base_url --
                # would have forwarded the operator's paid key to the target.
                if not _same_origin(current, nxt):
                    req_headers = _strip_credentials(req_headers)
                hops.append(current)
                current = nxt
                continue

            if not resp.ok:
                fetch_err = FetchError(
                    f"HTTP {resp.status} for {redact_url(current)}",
                    code=ErrCode.HTTP,
                    retryable=resp.status in RETRY_CODES,
                    status=resp.status,
                )
                if stale_resp is not None and _stale_eligible(fetch_err):
                    return _mark_stale(stale_resp, stale_created)
                raise fetch_err

            resp.redirects = hops
            resp.final_url = redact_url(current)
            if use_cache and self.cache.s.cache_enabled and resp.status == 200:
                await self.cache.set(
                    key,
                    resp.body,
                    {
                        "kind": "http",
                        "final_url": redact_url(current),
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
        *,
        deadline: float | None = None,
    ) -> FetchResponse:
        host = host_of(url)
        assert host
        clients = (self._client, self._client_h1)
        # No caller deadline: keep the historical two-round retry across both
        # protocol pools. With a deadline, one HTTP/2 attempt plus one HTTP/1.1
        # fallback fits the budget; repeating both rounds would just time out.
        slots = [*clients, *clients] if deadline is None else list(clients)
        last_error: Exception | None = None
        for slot, client in enumerate(slots):
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0.05:
                break
            if remaining is None:
                attempt_timeout = self.s.read_timeout_s
            elif len(slots) == 2 and slot == 0:
                # Give the primary attempt most of the budget but reserve
                # enough for the protocol fallback. Without this split a slow
                # HTTP/2 stream consumes the whole research deadline and the
                # HTTP/1.1 pool is never tried.
                attempt_timeout = max(0.1, remaining * 0.65)
            else:
                attempt_timeout = max(0.05, remaining)
            try:
                async with self._global, await self._host_sem(host):
                    async with asyncio.timeout(attempt_timeout):
                        async with client.stream(method, url, headers=headers, content=body) as r:
                            # Do not reject solely on Content-Length: a server
                            # can omit or lie about it. Enforce the cap while
                            # streaming and return a marked, truncated body.
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
            except (TimeoutError, httpx.TimeoutException) as e:
                last_error = e
                continue
            except (httpx.ProtocolError, httpx.ReadError) as e:
                # Try the HTTP/1.1 pool before retrying the same protocol.
                last_error = e
                continue
            except httpx.HTTPError as e:
                last_error = e
                continue
        if last_error is None:
            raise FetchError(f"deadline exceeded fetching {host}", code=ErrCode.TIMEOUT, retryable=True)
        if isinstance(last_error, (TimeoutError, httpx.TimeoutException)):
            raise FetchError(f"timeout fetching {host}", code=ErrCode.TIMEOUT, retryable=True) from last_error
        if isinstance(last_error, httpx.ProtocolError):
            raise FetchError(
                f"protocol error fetching {host}: {last_error}",
                code=ErrCode.HTTP,
                retryable=True,
            ) from last_error
        raise FetchError(f"failed to fetch {host}", code=ErrCode.HTTP, retryable=True) from last_error

    async def fetch_text(self, url: str, **kw: Any) -> tuple[str, FetchResponse]:
        r = await self.fetch(url, **kw)
        return r.text, r
