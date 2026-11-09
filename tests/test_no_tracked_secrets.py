"""Guard against committing live-looking API secrets.

This scans files tracked by git (not the untracked local ``.env``) for full-shape
credential patterns. Canary/test placeholders are allowed because they are marked
as such. If this test fails, remove the value from the file and rotate the key:
git history must be purged separately (a leaked key stays recoverable).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Full-shape credential patterns. Deliberately require realistic length so that
# prose such as "nvapi-" or "AIza" alone does not fail; prefixes in documentation
# (``nvapi-<redacted>``) do not match either.
_PATTERNS = (
    re.compile(r"nvapi-[A-Za-z0-9_\-]{15,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{25,}"),
    re.compile(r"tvly-[A-Za-z0-9_\-]{15,}"),
    re.compile(r"sk-(?:proj|ant|live)-[A-Za-z0-9_\-]{15,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AQ\.Ab8RN[A-Za-z0-9_\-]{10,}"),
)

# Lines containing one of these markers are deliberate placeholders/canaries.
_ALLOW_MARKERS = (
    "CANARY",
    "canary",
    "EXAMPLE",
    "example",
    "REDACTED",
    "redacted",
    "placeholder",
    "dummy",
    "fake",
    "test-",
    "xxxx",
    "<SECRET>",
)

_TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".json",
    ".jsonl",
    ".yml",
    ".yaml",
    ".toml",
    ".txt",
    ".cfg",
    ".ini",
    ".sh",
    ".ps1",
    ".js",
    ".ts",
}
_MAX_BYTES = 2_000_000


def _tracked_files() -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - git missing
        pytest.skip(f"git unavailable: {exc}")
    if proc.returncode != 0:  # pragma: no cover - not a git checkout
        pytest.skip("not a git checkout")
    return [p for p in proc.stdout.split("\0") if p]


def _iter_text_lines(rel: str):
    path = ROOT / rel
    if path.suffix.lower() not in _TEXT_SUFFIXES:
        return
    try:
        if path.stat().st_size > _MAX_BYTES:
            return
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for lineno, line in enumerate(text.splitlines(), 1):
        yield lineno, line


def test_no_live_shaped_secrets_in_tracked_files():
    tracked = _tracked_files()
    assert tracked, "expected a non-empty tracked file list"

    findings: list[str] = []
    for rel in tracked:
        if rel == "tests/test_no_tracked_secrets.py":
            continue  # the pattern definitions themselves
        if Path(rel).name.startswith(".env"):
            continue  # untracked by policy; covered elsewhere
        for lineno, line in _iter_text_lines(rel):
            if any(marker in line for marker in _ALLOW_MARKERS):
                continue
            for pattern in _PATTERNS:
                match = pattern.search(line)
                if match:
                    redacted = match.group(0)[:10] + "<redacted>"
                    findings.append(f"{rel}:{lineno}: {redacted}")
                    break

    assert not findings, (
        "tracked files contain live-looking API secrets (remove them and rotate the key):\n"
        + "\n".join(findings)
    )


# Directories that frequently hold benchmark/measurement output but are often
# untracked, so a tracked-only scan would miss a key echoed into a artifact.
_UNTRACKED_SCAN_DIRS = ("reports", "evidence", "scratch")
_UNTRACKED_MAX_FILES = 4000


def _untracked_artifact_files() -> list[Path]:
    tracked = set(_tracked_files())
    out: list[Path] = []
    for name in _UNTRACKED_SCAN_DIRS:
        root = ROOT / name
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
                continue
            try:
                rel = path.relative_to(ROOT).as_posix()
            except ValueError:
                continue
            if rel in tracked:
                continue
            out.append(path)
            if len(out) >= _UNTRACKED_MAX_FILES:
                return out
    return out


def test_no_live_shaped_secrets_in_untracked_artifacts():
    """Benchmark output is often untracked, so guard it before it is committed.

    A tracked-only scan cannot catch a key echoed into a fresh results file; this
    covers the report/evidence/scratch trees regardless of git status.
    """
    findings: list[str] = []
    for path in _untracked_artifact_files():
        try:
            if path.stat().st_size > _MAX_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for lineno, line in enumerate(text.splitlines(), 1):
            if any(marker in line for marker in _ALLOW_MARKERS):
                continue
            for pattern in _PATTERNS:
                match = pattern.search(line)
                if match:
                    findings.append(f"{rel}:{lineno}: {match.group(0)[:10]}<redacted>")
                    break

    assert not findings, (
        "untracked report/evidence artifacts contain live-looking API secrets:\n"
        + "\n".join(findings)
    )
