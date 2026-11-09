from __future__ import annotations

import pytest
from pydantic import ValidationError

from weblens.config import Settings
from weblens.tenancy import (
    ApiKeyRegistry,
    current_tenant,
    normalise_api_keys,
    parse_api_keys,
    parse_tenant_rate_limits,
    tenant_state_path,
    validate_tenant,
)


def test_parse_api_keys_accepts_json_and_pairs():
    assert parse_api_keys('{"acme":"12345678","beta":"abcdefgh"}') == {
        "acme": "12345678",
        "beta": "abcdefgh",
    }
    assert parse_api_keys("acme=12345678,beta=abcdefgh") == {
        "acme": "12345678",
        "beta": "abcdefgh",
    }
    assert parse_api_keys("acme=12345678;beta=abcdefgh") == {
        "acme": "12345678",
        "beta": "abcdefgh",
    }
    assert normalise_api_keys("") == ""


@pytest.mark.parametrize(
    "raw",
    [
        '{"bad tenant":"12345678"}',
        '{"acme":"short"}',
        '{"acme":"12345678","acme2":"12345678"}',
        '{"acme":"12345678","beta":"12345678"}',
        "not-a-pair",
        "[1,2,3]",
    ],
)
def test_parse_api_keys_rejects_unsafe_or_ambiguous_config(raw):
    with pytest.raises(ValueError):
        parse_api_keys(raw)


def test_settings_normalises_api_keys_and_rate_limits():
    settings = Settings(
        api_keys="acme=12345678,beta=abcdefgh",
        tenant_rate_limits="acme=600,beta=120",
    )
    assert settings.api_key_map == {"acme": "12345678", "beta": "abcdefgh"}
    assert settings.tenant_rate_limit_map == {"acme": 600, "beta": 120}
    assert "12345678" not in repr(settings)


def test_settings_rejects_invalid_tenant_limits():
    with pytest.raises(ValidationError):
        Settings(tenant_rate_limits='{"acme": 0}')
    with pytest.raises(ValidationError):
        Settings(api_keys='{"acme": "short"}')


def test_registry_authenticates_bearer_and_api_key_headers():
    registry = ApiKeyRegistry({"acme": "12345678", "beta": "abcdefgh"})
    assert registry.authenticate_header("Bearer 12345678") == "acme"
    assert registry.authenticate_header("bearer abcdefgh") == "beta"
    assert registry.authenticate_header(None, "abcdefgh") == "beta"
    assert registry.authenticate_header("Bearer nope") is None
    assert registry.authenticate_header("Basic 12345678") is None
    assert registry.authenticate_header("") is None
    assert registry.tenants == ("acme", "beta")
    assert len(registry) == 2


def test_registry_rejects_duplicate_keys():
    with pytest.raises(ValueError):
        ApiKeyRegistry({"acme": "12345678", "beta": "12345678"})


def test_tenant_state_path_keeps_default_and_isolates_others(tmp_path):
    assert tenant_state_path(tmp_path, "default", "crawl2rag.db") == tmp_path / "crawl2rag.db"
    assert tenant_state_path(tmp_path, "acme", "crawl2rag.db") == tmp_path / "tenants" / "acme" / "crawl2rag.db"
    with pytest.raises(ValueError):
        tenant_state_path(tmp_path, "../escape", "crawl2rag.db")
    with pytest.raises(ValueError):
        validate_tenant("")
    assert current_tenant.get() == "default"


def test_tenant_rate_limits_support_pairs_and_json():
    assert parse_tenant_rate_limits('{"acme":600}') == {"acme": 600}
    assert parse_tenant_rate_limits("acme=600,beta=120") == {"acme": 600, "beta": 120}
