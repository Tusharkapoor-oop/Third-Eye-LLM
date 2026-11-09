from __future__ import annotations

from weblens.ratelimit import TenantRateLimiter, client_ip_from_scope, rate_limit_key


class Clock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def test_token_bucket_allows_burst_then_refills():
    clock = Clock()
    limiter = TenantRateLimiter(2, window_s=60.0, clock=clock)
    assert limiter.check("tenant:acme").allowed is True
    assert limiter.check("tenant:acme").allowed is True
    blocked = limiter.check("tenant:acme")
    assert blocked.allowed is False
    assert blocked.retry_after >= 1
    assert blocked.remaining == 0

    clock.now += 30.0
    assert limiter.check("tenant:acme").allowed is True


def test_per_tenant_limits_are_independent():
    limiter = TenantRateLimiter(
        10,
        window_s=60.0,
        per_tenant={"acme": 1, "beta": 100},
        clock=Clock(),
    )
    assert limiter.check("tenant:acme").allowed is True
    assert limiter.check("tenant:acme").allowed is False
    assert limiter.check("tenant:beta").allowed is True
    assert limiter.check("tenant:beta").allowed is True
    assert limiter.check("ip:203.0.113.7").allowed is True


def test_buckets_are_bounded_and_evicted_lru():
    limiter = TenantRateLimiter(1, window_s=60.0, max_buckets=2, clock=Clock())
    assert limiter.check("ip:one").allowed is True
    assert limiter.check("ip:two").allowed is True
    # Touch "one" so "two" is the least recently used entry.
    assert limiter.check("ip:one").allowed is False
    assert limiter.check("ip:three").allowed is True
    assert limiter.active_buckets() == 2
    # "two" was evicted and starts with a fresh token.
    assert limiter.check("ip:two").allowed is True


def test_rate_limit_key_prefers_tenant_and_ignores_spoofed_xff_by_default():
    scope = {
        "state": {"tenant_id": "acme"},
        "headers": [(b"x-forwarded-for", b"spoofed, 203.0.113.7")],
        "client": ("127.0.0.1", 1),
    }
    assert rate_limit_key(scope) == "tenant:acme"
    del scope["state"]
    # Untrusted: spoofed XFF is ignored, rate limit uses the ASGI peer address.
    assert rate_limit_key(scope) == "ip:127.0.0.1"


def test_rate_limit_key_trusts_rightmost_xff_when_proxy_headers_enabled():
    from weblens.config import Settings

    scope = {
        "state": {"settings": Settings(trust_proxy_headers=True)},
        "headers": [(b"x-forwarded-for", b"spoofed, 203.0.113.7")],
        "client": ("10.0.0.1", 1),
    }
    assert rate_limit_key(scope) == "ip:203.0.113.7"


def test_client_ip_from_scope_returns_rightmost_xff():
    scope = {
        "headers": [(b"x-forwarded-for", b"1.2.3.4, 203.0.113.7")],
        "client": ("127.0.0.1", 1),
    }
    assert client_ip_from_scope(scope) == "203.0.113.7"
