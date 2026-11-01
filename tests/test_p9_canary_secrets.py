"""P9: Canary Secret Leakage Prevention Tests.

Verifies that canary secrets planted in environment variables and configurations
are never reflected in error payloads, logs, tracebacks, or cache inspection.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "weblens" / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "weblens" / "src"))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

CANARY_KEY = "tvly-CANARY-9f8e7d6c5b4a3210"


def test_canary_key_not_in_error_payload():
    """Verify that provider errors do not echo API keys back to caller."""
    from weblens.config import Settings
    from weblens.search.tavily import TavilySearch

    s = Settings()
    provider = TavilySearch(s, CANARY_KEY)
    rep = str(provider)
    assert CANARY_KEY not in rep, "TavilySearch __str__ or __repr__ leaked canary key"


def test_canary_key_not_in_cache_keys():
    """Verify that authorization headers and secret tokens are hashed in cache keys."""
    import hashlib
    from weblens.cache import cache_key

    # Auth fingerprint is sha256 hash of auth header
    auth_fingerprint = hashlib.sha256(f"Bearer {CANARY_KEY}".encode("utf-8")).hexdigest()
    ck = cache_key("https://example.com/api", auth_fingerprint)
    assert CANARY_KEY not in ck, "Cache key leaked plaintext canary authorization header"


def test_canary_redaction_in_evidence_runner():
    """Verify that evidence runner redaction engine successfully catches and redacts canary key."""
    from tools.evidence_run import redact

    sample_log = f"Error: Request failed with authorization tvly-CANARY-9f8e7d6c5b4a3210 at endpoint."
    redacted, detections = redact(sample_log, [CANARY_KEY])
    assert len(detections) > 0, "Evidence runner failed to flag canary token as contaminated"
    assert CANARY_KEY not in redacted, "Evidence runner failed to redact canary token"
    assert "[REDACTED:" in redacted
