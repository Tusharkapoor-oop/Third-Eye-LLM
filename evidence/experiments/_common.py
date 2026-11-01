"""Shared helpers for evidence experiments.

The primary subject is the ``weblens/`` package. The repository also contains a
second, unrelated copy at ``src/weblens`` which shadows it on the normal import
path, so every experiment pins ``weblens/src`` explicitly and asserts the loaded
module path before doing anything else.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEBLENS_SRC = ROOT / "weblens" / "src"
if str(WEBLENS_SRC) not in sys.path:
    sys.path.insert(0, str(WEBLENS_SRC))


def run_dir() -> Path:
    rid = os.environ.get("EVIDENCE_RUN_ID")
    if not rid:
        raise SystemExit("EVIDENCE_RUN_ID is not set: run this experiment through tools/evidence_run.py")
    path = ROOT / "evidence" / "raw" / rid
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_result(payload: dict) -> None:
    path = run_dir() / "result.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload.get("summary", {}), indent=2, sort_keys=True))


def emit(payload: dict) -> None:
    write_result(payload)


def assert_subject(module_file: str) -> str:
    resolved = Path(module_file).resolve()
    expected = (WEBLENS_SRC / "weblens").resolve()
    if expected not in resolved.parents and resolved != expected:
        raise SystemExit(f"wrong weblens package loaded: {resolved} (expected under {expected})")
    return str(resolved)
