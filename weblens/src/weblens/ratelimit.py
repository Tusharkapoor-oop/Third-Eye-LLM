"""O(1) token-bucket rate limiting keyed by tenant or client address.

The limiter is deliberately synchronous: an ASGI worker runs on one event loop,
and a token-bucket check has no await points.  That keeps the hot path shorter
than a deque-per-client sliding window and bounds memory with an LRU.
"""

from __future__ import annotations

import math
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    reset_after: int


@dataclass
class _Bucket:
    tokens: float
    updated: float


class TenantRateLimiter:
    """Per-key token bucket with per-tenant overrides.

    ``limit`` is requests per ``window_s``.  Capacity is one full window, so a
    client may burst up to its configured quota and then refills continuously.
    """

    def __init__(
        self,
        default_limit: int = 120,
        *,
        window_s: float = 60.0,
        per_tenant: Mapping[str, int] | None = None,
        max_buckets: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ):
        if default_limit < 1:
            raise ValueError("default_limit must be >= 1")
        if window_s <= 0:
            raise ValueError("window_s must be > 0")
        if max_buckets < 1:
            raise ValueError("max_buckets must be >= 1")
        self.default_limit = int(default_limit)
        self.window_s = float(window_s)
        self.per_tenant = {key: max(1, int(value)) for key, value in (per_tenant or {}).items()}
        self.max_buckets = int(max_buckets)
        self._clock = clock
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()

    def limit_for(self, key: str) -> int:
        if key.startswith("tenant:"):
            return self.per_tenant.get(key[7:], self.default_limit)
        return self.default_limit

    def check(self, key: str, *, limit: int | None = None) -> RateDecision:
        cap = float(max(1, int(limit if limit is not None else self.limit_for(key))))
        rate = cap / self.window_s
        now = self._clock()

        bucket = self._buckets.get(key)
        if bucket is None:
            if len(self._buckets) >= self.max_buckets:
                # Bound state created by spoofed addresses or tenant churn.
                self._buckets.popitem(last=False)
            bucket = _Bucket(tokens=cap, updated=now)
            self._buckets[key] = bucket
        else:
            elapsed = max(0.0, now - bucket.updated)
            bucket.tokens = min(cap, bucket.tokens + elapsed * rate)
            bucket.updated = now
            self._buckets.move_to_end(key)

        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            allowed = True
            retry_after = 0
        else:
            allowed = False
            retry_after = max(1, math.ceil((1.0 - bucket.tokens) / rate))

        reset_after = max(0, math.ceil((cap - bucket.tokens) / rate))
        return RateDecision(
            allowed=allowed,
            limit=int(cap),
            remaining=max(0, int(bucket.tokens)),
            retry_after=retry_after,
            reset_after=reset_after,
        )

    def active_buckets(self) -> int:
        return len(self._buckets)


def client_ip_from_scope(scope: dict) -> str:
    """Return the right-most XFF entry from an ASGI scope.

    The right-most entry is the hop appended by the closest trusted proxy
    (Cloud Run / load-balancer behavior). It is the hardest for upstream
    callers to spoof, and the left-most entries are omitted because they are
    caller-controlled and must not be used as a rate-limit key.
    """

    headers = {k.lower(): v for k, v in scope.get("headers") or []}
    forwarded_raw = headers.get(b"x-forwarded-for", b"").decode("latin-1")
    forwarded = [part.strip() for part in forwarded_raw.split(",") if part.strip()]
    if forwarded:
        return forwarded[-1]
    client = scope.get("client") or ("unknown", 0)
    return str(client[0])


def trusted_client_ip(scope: dict) -> str:
    """Return the client address used for rate limiting.

    By default (``trust_proxy_headers`` False) the peer address from the ASGI
    scope is used and ``X-Forwarded-For`` is ignored entirely, because spoofed
    XFF values must not bypass per-client limits. When explicitly trusted,
    the right-most XFF entry is used instead.
    """
    state = scope.get("state") or {}
    if isinstance(state, dict):
        settings = state.get("settings")
        if getattr(settings, "trust_proxy_headers", False):
            return client_ip_from_scope(scope)
    client = scope.get("client") or ("unknown", 0)
    return str(client[0])


def rate_limit_key(scope: dict) -> str:
    state = scope.get("state") or {}
    tenant = state.get("tenant_id") if isinstance(state, dict) else None
    if tenant:
        return f"tenant:{tenant}"
    return f"ip:{trusted_client_ip(scope)}"
