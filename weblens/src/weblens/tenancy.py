"""Tenant identity, API-key parsing and per-tenant state paths.

The HTTP transport is intentionally the only place that turns a secret into a
tenant identity.  Tool handlers read that identity from a context variable, so
stateful tools never accept a tenant id from the caller.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from contextvars import ContextVar
from pathlib import Path

# Tenant ids become directory names and log fields.  Keep them boring.
TENANT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_MIN_KEY_LENGTH = 8

# "default" is the single-tenant / stdio identity.  Authenticated HTTP tenants
# get their own value from the API-key registry.
current_tenant: ContextVar[str] = ContextVar("weblens_tenant", default="default")


def validate_tenant(tenant: str) -> str:
    value = (tenant or "").strip()
    if not TENANT_RE.fullmatch(value):
        raise ValueError(f"tenant must match [A-Za-z0-9][A-Za-z0-9_.-]{{0,63}} (got {tenant!r})")
    return value


def _split_pairs(raw: str) -> list[tuple[str, str]]:
    text = (raw or "").strip()
    if not text:
        return []
    if text.startswith("{"):
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON object: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError("expected a JSON object mapping tenant to value")
        return [(str(k), str(v)) for k, v in obj.items()]

    pairs: list[tuple[str, str]] = []
    for part in re.split(r"[,;\n]", text):
        item = part.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"expected tenant=value pairs or a JSON object; cannot parse {item!r}")
        tenant, value = item.split("=", 1)
        pairs.append((tenant.strip(), value.strip()))
    return pairs


def parse_api_keys(raw: str | None) -> dict[str, str]:
    """Parse ``tenant=key`` pairs or ``{"tenant": "key"}`` JSON.

    Keys are secrets: callers must not log the returned mapping.  The registry
    stores only SHA-256 digests after construction.
    """

    keys: dict[str, str] = {}
    seen_keys: dict[str, str] = {}
    for tenant, key in _split_pairs(raw or ""):
        tenant = validate_tenant(tenant)
        if len(key) < _MIN_KEY_LENGTH:
            raise ValueError(f"API key for tenant {tenant!r} is shorter than {_MIN_KEY_LENGTH} characters")
        if tenant in keys:
            raise ValueError(f"duplicate tenant {tenant!r} in API keys")
        if key in seen_keys:
            raise ValueError(f"duplicate API key for tenants {seen_keys[key]!r} and {tenant!r}")
        keys[tenant] = key
        seen_keys[key] = tenant
    return keys


def normalise_api_keys(raw: str | None) -> str:
    """Return a canonical JSON representation without changing key values."""

    parsed = parse_api_keys(raw)
    return json.dumps(parsed, separators=(",", ":"), ensure_ascii=False) if parsed else ""


def parse_tenant_rate_limits(raw: str | None) -> dict[str, int]:
    """Parse per-tenant requests-per-minute overrides."""

    limits: dict[str, int] = {}
    for tenant, value in _split_pairs(raw or ""):
        tenant = validate_tenant(tenant)
        try:
            limit = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"rate limit for tenant {tenant!r} must be an integer") from exc
        if not 1 <= limit <= 100_000:
            raise ValueError(f"rate limit for tenant {tenant!r} must be between 1 and 100000")
        if tenant in limits:
            raise ValueError(f"duplicate tenant {tenant!r} in rate limits")
        limits[tenant] = limit
    return limits


def normalise_tenant_rate_limits(raw: str | None) -> str:
    parsed = parse_tenant_rate_limits(raw)
    return json.dumps(parsed, separators=(",", ":")) if parsed else ""


class ApiKeyRegistry:
    """Constant-time bearer/X-API-Key lookup that yields a tenant id."""

    def __init__(self, keys: Mapping[str, str] | None = None):
        self._entries: list[tuple[bytes, str]] = []
        self._tenants: set[str] = set()
        for tenant, key in (keys or {}).items():
            self.add(tenant, key)

    def add(self, tenant: str, key: str) -> None:
        tenant = validate_tenant(tenant)
        if len(key) < _MIN_KEY_LENGTH:
            raise ValueError(f"API key for tenant {tenant!r} is shorter than {_MIN_KEY_LENGTH} characters")
        if tenant in self._tenants:
            raise ValueError(f"duplicate tenant {tenant!r}")
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        if any(hmac.compare_digest(digest, existing) for existing, _ in self._entries):
            raise ValueError(f"duplicate API key for tenant {tenant!r}")
        self._entries.append((digest, tenant))
        self._tenants.add(tenant)

    def authenticate(self, token: str | None) -> str | None:
        if not token:
            return None
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for existing, tenant in self._entries:
            if hmac.compare_digest(digest, existing):
                return tenant
        return None

    def authenticate_header(self, authorization: str | None, api_key: str | None = None) -> str | None:
        if api_key:
            return self.authenticate(api_key.strip())
        value = (authorization or "").strip()
        scheme, _, token = value.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return None
        return self.authenticate(token.strip())

    @property
    def tenants(self) -> tuple[str, ...]:
        return tuple(sorted(self._tenants))

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)


def tenant_state_path(cache_dir: Path, tenant: str, filename: str) -> Path:
    """Return the isolated database path for a tenant.

    The default identity keeps the historical single-tenant path so existing
    local data remains available.  Every other tenant gets a subdirectory that
    is derived only from a validated tenant id.
    """

    tenant = validate_tenant(tenant)
    if tenant == "default":
        return Path(cache_dir) / filename
    return Path(cache_dir) / "tenants" / tenant / filename


def tenant_state_dir(cache_dir: Path, tenant: str) -> Path:
    return tenant_state_path(cache_dir, tenant, "").parent
