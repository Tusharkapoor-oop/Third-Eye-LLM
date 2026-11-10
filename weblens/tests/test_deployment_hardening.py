"""Regression guards for the deployment-hardening pass (2026-11-10).

Covers four defects found during a multi-model audit and a Render deployment
dry-run:

1. ``SafeFetcher`` forwarded caller credentials across a cross-host redirect.
2. API keys carried in a URL query string reached the on-disk cache and error text.
3. The default ``allowed_hosts`` had no port wildcard, so every real client got 421.
4. ``http_port`` ignored ``$PORT``, so a platform that injects it was never reached.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import Response

from weblens.cache import Cache
from weblens.cli import _transport_security_settings
from weblens.config import Settings
from weblens.net.client import SafeFetcher, _same_origin, _strip_credentials, redact_url

# --------------------------------------------------------------------------- #
# 1. cross-origin redirects must not carry credentials
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "a,b,same",
    [
        ("https://api.tavily.com/a", "https://api.tavily.com/b", True),
        ("https://api.tavily.com:443/a", "https://api.tavily.com/b", True),
        ("https://api.tavily.com/a", "http://api.tavily.com/b", False),
        ("https://api.tavily.com/a", "https://evil.example.com/b", False),
        ("https://api.tavily.com/a", "https://api.tavily.com:8443/b", False),
        ("https://api.tavily.com/a", "https://sub.api.tavily.com/b", False),
    ],
)
def test_same_origin_only_for_identical_scheme_host_port(a, b, same):
    assert _same_origin(a, b) is same


def test_cross_origin_redirect_strips_credentials_but_keeps_benign_headers():
    headers = {
        "Authorization": "Bearer SECRET",
        "X-Subscription-Token": "KEY",
        "Cookie": "session=1",
        "Accept": "text/html",
    }
    out = _strip_credentials(headers)
    assert "Accept" in out, "benign headers must survive"
    for secret in ("Authorization", "X-Subscription-Token", "Cookie"):
        assert secret not in out, f"{secret} must not follow a cross-origin redirect"


# --------------------------------------------------------------------------- #
# 2. secrets in URLs are redacted before they can be cached or logged
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "param",
    ["key", "api_key", "apikey", "access_token", "token", "secret", "password", "signature"],
)
def test_secret_query_parameters_are_redacted(param):
    url = f"https://api.example.com/v1/search?{param}=SUPERSECRETVALUE&q=test"
    out = redact_url(url)
    assert "SUPERSECRETVALUE" not in out
    assert "REDACTED" in out
    assert "q=test" in out, "non-secret parameters must be preserved"


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example.com/v1/search?q=test&page=2",
        "https://api.example.com/v1/search",
        "https://api.example.com/",
    ],
)
def test_urls_without_secrets_are_unchanged(url):
    assert redact_url(url) == url


def test_redaction_is_case_insensitive():
    assert "SUPERSECRETVALUE" not in redact_url("https://x.example/?Key=SUPERSECRETVALUE")


# --------------------------------------------------------------------------- #
# 3. the default allowed_hosts must accept a real client's Host header
# --------------------------------------------------------------------------- #


def test_default_allowed_hosts_accepts_a_port_qualified_client():
    """MCP matches Host exactly or via host:*; a bare entry never matches a port."""
    settings = Settings()
    ts = _transport_security_settings(settings)
    assert ts is not None
    assert ts.enable_dns_rebinding_protection is True, "protection must stay on"

    from mcp.server.transport_security import TransportSecurityMiddleware

    middleware = TransportSecurityMiddleware(ts)
    for host in ("127.0.0.1:8765", "localhost:8765", "[::1]:8765", "127.0.0.1"):
        assert middleware._validate_host(host) is True, f"legitimate client Host {host} rejected"
    for host in ("evil.example.com", "evil.example.com:8765", "attacker:8080"):
        assert middleware._validate_host(host) is False, f"hostile Host {host} accepted"


def test_wildcard_allowed_hosts_still_disables_protection_explicitly():
    """The documented '*' escape hatch remains available and stays explicit."""
    ts = _transport_security_settings(Settings(allowed_hosts="*"))
    assert ts is not None
    assert ts.enable_dns_rebinding_protection is False


# --------------------------------------------------------------------------- #
# 4. $PORT is honoured so a platform can route to the process
# --------------------------------------------------------------------------- #


def test_port_env_is_honoured(monkeypatch):
    monkeypatch.delenv("WEBLENS_HTTP_PORT", raising=False)
    monkeypatch.setenv("PORT", "9999")
    assert Settings().http_port == 9999


def test_prefixed_port_name_wins_over_platform_port(monkeypatch):
    monkeypatch.setenv("PORT", "9999")
    monkeypatch.setenv("WEBLENS_HTTP_PORT", "7777")
    assert Settings().http_port == 7777


def test_port_defaults_when_neither_is_set(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("WEBLENS_HTTP_PORT", raising=False)
    assert Settings().http_port == 8765


@pytest.mark.asyncio
async def test_fetch_strips_credentials_on_cross_host_redirect(respx_mock):
    """The redirect loop must not forward an API key to a different origin.

    End-to-end guard for the real defect: the loop reused ``req_headers`` for
    every hop, so a 30x from an API host sent ``Authorization`` and
    ``X-Subscription-Token`` to the redirect target. httpx's own
    follow_redirects drops Authorization across hosts; this hand-rolled loop did
    not. The assertion inspects what the second hop actually received.
    """
    seen: dict[str, dict[str, str]] = {}

    def first(request):
        seen["first"] = dict(request.headers)
        return Response(302, headers={"location": "https://other.example/sink"})

    def second(request):
        seen["second"] = dict(request.headers)
        return Response(200, text="ok")

    respx_mock.get("https://api.example/start").mock(side_effect=first)
    respx_mock.get("https://other.example/sink").mock(side_effect=second)

    fetcher = SafeFetcher(
        Settings(cache_enabled=False, allow_hosts="api.example,other.example"),
        Cache(Settings(cache_dir=Path(".") / ".tmp", cache_enabled=False)),
    )
    try:
        await fetcher.fetch(
            "https://api.example/start",
            headers={"Authorization": "Bearer SECRET", "X-Subscription-Token": "KEY", "Accept": "text/html"},
        )
    finally:
        await fetcher.close()

    assert "first" in seen and "second" in seen, f"both hops must run; got {list(seen)}"
    # Sanity: the credential really was sent on the first (same-origin) hop.
    assert seen["first"].get("authorization") == "Bearer SECRET"
    # The fix: neither credential follows the redirect.
    assert "authorization" not in seen["second"], "Authorization leaked across origins"
    assert "x-subscription-token" not in seen["second"], "X-Subscription-Token leaked across origins"
    # Benign headers still travel.
    assert seen["second"].get("accept") == "text/html"


def test_dockerfile_does_not_hardcode_the_settings_port():
    """The image must let $PORT win.

    A hardcoded WEBLENS_HTTP_PORT in the Dockerfile would be the more specific
    settings key and would outrank the platform-injected $PORT, so the process
    would bind a port the platform does not route to and every health check would
    fail. The CMD passes --port explicitly instead.
    """
    from pathlib import Path

    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
    if not dockerfile.exists():  # running from an sdist without the repo root
        pytest.skip("Dockerfile not present in this checkout")
    text = dockerfile.read_text(encoding="utf-8")
    env_lines = [ln for ln in text.splitlines() if ln.strip().startswith("ENV") or "WEBLENS_HTTP_PORT" in ln]
    assignments = [ln for ln in env_lines if ln.split("#")[0].strip().startswith("WEBLENS_HTTP_PORT=")]
    assert not assignments, (
        f"Dockerfile must not set WEBLENS_HTTP_PORT as an ENV; it outranks $PORT. Found: {assignments}"
    )
    assert "--port" in text, "the CMD must pass --port so it outranks both settings keys"
