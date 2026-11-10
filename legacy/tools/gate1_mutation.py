#!/usr/bin/env python3
"""Gate 1: prove the security tests actually fail against deliberately broken builds.

v6 Part 2.5b requires that a test which passes a broken build is deleted from the
evidence. This script mutates each shipped protection, runs the tests that are
supposed to defend it, and reports CAUGHT / SURVIVED per mutant.

A SURVIVED line is a real defect: it means the protection is not covered by any
test that would notice it being removed.

Usage:
    python tools/gate1_mutation.py            # run all mutants
    python tools/gate1_mutation.py --only ssrf
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

# (name, target file, exact text to replace, replacement, tests that must fail)
MUTANTS = [
    (
        "ssrf-metadata-and-private-ips",
        "weblens/src/weblens/net/ssrf.py",
        "BLOCKED_IPS = {",
        "BLOCKED_IPS = set()  # MUTANT: protections removed\n_UNUSED = {",
        ["weblens/tests/test_ssrf.py"],
    ),
    (
        "injection-scanner-noop",
        "weblens/src/weblens/security/injection.py",
        "def scan_injection(text: str) -> list[str]:",
        "def scan_injection(text: str) -> list[str]:\n    return []  # MUTANT: scanner disabled",
        ["weblens/tests/test_passages.py", "weblens/tests/test_injection_corpus.py"],
    ),
    (
        "token-cap-ceiling-removed",
        "weblens/src/weblens/errors.py",
        "    return min(maximum, requested)",
        "    return requested  # MUTANT: ceiling no longer enforced",
        ["weblens/tests/test_errors_contract.py", "weblens/tests/test_service.py"],
    ),
]


def run_tests(paths: list[str]) -> int:
    existing = [p for p in paths if (ROOT / p).exists()]
    if not existing:
        return -1
    proc = subprocess.run(
        [PY, "-m", "pytest", *existing, "-q", "--timeout=120", "-p", "no:cacheprovider", "--tb=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="run a single mutant by name")
    ap.add_argument("--out", default="evidence/raw/gate1_mutation.json")
    args = ap.parse_args()

    results = []
    for name, rel, old, new, tests in MUTANTS:
        if args.only and name != args.only:
            continue
        target = ROOT / rel
        if not target.exists():
            results.append({"mutant": name, "status": "TARGET_MISSING", "file": rel})
            print(f"[SKIP] {name}: {rel} not found")
            continue
        original = target.read_text(encoding="utf-8")
        if old not in original:
            results.append({"mutant": name, "status": "ANCHOR_MISSING", "file": rel})
            print(f"[SKIP] {name}: anchor {old!r} not found in {rel}")
            continue

        backup = target.with_suffix(target.suffix + ".gate1bak")
        shutil.copy2(target, backup)
        try:
            target.write_text(original.replace(old, new, 1), encoding="utf-8")
            code = run_tests(tests)
        finally:
            shutil.copy2(backup, target)
            backup.unlink()

        if code == -1:
            status = "NO_TEST_FILES"
        elif code != 0:
            status = "CAUGHT"
        else:
            status = "SURVIVED"
        results.append({"mutant": name, "status": status, "file": rel, "tests": tests, "pytest_exit": code})
        print(f"[{status}] {name} ({rel})")

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"mutants": results}, indent=2), encoding="utf-8")

    survived = [r for r in results if r["status"] == "SURVIVED"]
    skipped = [r for r in results if r["status"] not in {"CAUGHT", "SURVIVED"}]
    print(f"\nCAUGHT {len(results) - len(survived) - len(skipped)}/{len(results)}; SURVIVED {len(survived)}; SKIPPED {len(skipped)}")
    return 1 if survived else 0


if __name__ == "__main__":
    raise SystemExit(main())
