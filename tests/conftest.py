"""Conftest for the webintel test suite (NOT the legacy src/weblens scaffold).

- Puts the repo root on sys.path so `python -m pytest tests` works from any cwd.
- No fixtures are required by webintel tests; keep this file dependency-light.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# tests/test_apps.py and tests/test_adversarial_grounding.py exercise the bundled
# `weblens` package, which lives in an src/ layout and is not installed here.
WEBLENS_SRC = ROOT / "weblens" / "src"
if WEBLENS_SRC.is_dir() and str(WEBLENS_SRC) not in sys.path:
    sys.path.append(str(WEBLENS_SRC))
