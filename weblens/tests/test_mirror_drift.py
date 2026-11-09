"""Guard against mirror/canonical drift in src/weblens vs weblens/src/weblens."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]  # workspace root
MIRROR = REPO_ROOT / "src" / "weblens"
CANONICAL = REPO_ROOT / "weblens" / "src" / "weblens"


# Files intentionally not mirrored (e.g. wheel metadata, CLI entry point).
_IGNORED = {"__pycache__"}


def _walk_text_files(root: Path):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in _IGNORED for part in p.parts):
            continue
        yield p.relative_to(root)


@pytest.mark.parametrize("rel", [pytest.param(p, id=str(p).replace("\\", "/")) for p in _walk_text_files(CANONICAL)])
def test_canonical_file_mirrored(rel: Path):
    """Every file in the canonical tree must be byte-identical in the mirror."""
    canon = CANONICAL / rel
    mirror = MIRROR / rel
    assert mirror.exists(), f"Mirror missing {rel}"
    assert canon.read_bytes() == mirror.read_bytes(), f"Drift in {rel}"


def test_mirror_has_no_extra_files():
    """The mirror must not contain files absent from the canonical tree."""
    extra = []
    for rel in _walk_text_files(MIRROR):
        if not (CANONICAL / rel).exists():
            extra.append(str(rel).replace("\\", "/"))
    assert not extra, f"Mirror contains extra files: {extra}"


def test_drift_guard_runs_in_house():
    """Sanity check that this test file can locate both trees."""
    assert CANONICAL.is_dir()
    assert MIRROR.is_dir()
