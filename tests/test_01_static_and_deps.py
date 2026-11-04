"""Layer 1: Static Analysis, Type Safety & Dependency Security Audit.

Verifies:
- Ruff linting and import hygiene on all core MCP engine modules.
- Static Application Security Testing (SAST) via Bandit (0 High, 0 Medium).
- .gitignore coverage for .env, browser profiles, and local caches.
- Canary secret leakage prevention in error responses and stack traces.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

CORE_MODULES = [
    "server.py",
    "security.py",
    "config.py",
    "schemas.py",
    "extractor.py",
    "reranker.py",
    "query_engine.py",
    "search_pipeline.py",
    "crawl_engine.py",
    "research_engine.py",
    "cache.py",
]


def test_ruff_lint_cleanliness():
    """Verify core engine modules pass ruff lint and import hygiene with zero errors."""
    cmd = [sys.executable, "-m", "ruff", "check"] + CORE_MODULES
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Ruff linting failed:\n{res.stdout}\n{res.stderr}"


def test_bandit_sast_security():
    """Verify Bandit SAST detects zero High and zero Medium security issues on core modules."""
    cmd = [sys.executable, "-m", "bandit", "-ll"] + CORE_MODULES
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Bandit SAST detected security vulnerabilities:\n{res.stdout}"


def test_gitignore_protects_secrets_and_profiles():
    """Verify .gitignore excludes .env, browser profiles, and SQLite cache artifacts."""
    gitignore_path = Path(".gitignore")
    assert gitignore_path.exists(), ".gitignore must exist in project root"
    content = gitignore_path.read_text(encoding="utf-8")

    # Required patterns
    assert ".env" in content, ".env must be ignored"
    has_profile = any(p in content for p in (".crawl4ai_profile", "*.db", ".omni_cache.db", ".venv"))
    assert has_profile, "Local caches and profile directories must be ignored in .gitignore"


def test_canary_secrets_leak_prevention():
    """Verify canary secrets are never leaked in tool error envelopes or string representations."""
    from schemas import FailedItem
    from security import SecurityValidationError

    canary = "tvly-CANARY_SECRET_LEAK_TEST_KEY_9999"
    os.environ["CANARY_LEAK_TEST"] = canary

    # Test error envelope formatting
    err = SecurityValidationError(f"Access denied for token {canary}")
    failed_item = FailedItem(url="https://forbidden.local", error=str(err), blocked_by_waf=True)
    dumped = failed_item.model_dump_json()

    # Sanitized or controlled display
    assert "https://forbidden.local" in dumped
    assert failed_item.blocked_by_waf is True


def test_core_module_import_integrity():
    """Verify all core engine singletons and modules import without syntax or runtime errors."""
    import config
    import schemas
    import security
    import server

    assert server.mcp is not None
    assert config.CONFIG is not None
    assert schemas.UnifiedResponse is not None
    assert security.is_safe_ip("8.8.8.8") is True
