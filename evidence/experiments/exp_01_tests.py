"""EXP-01: run the WebLens package test suite and record exact counts."""

from __future__ import annotations

import os
import re
import subprocess
import sys

from _common import ROOT, emit, run_dir

OUT = run_dir()
PY = sys.executable
CWD = ROOT / "weblens"

env = os.environ.copy()
env["PYTHONPATH"] = str(ROOT / "weblens" / "src")
env["PYTHONDONTWRITEBYTECODE"] = "1"

cmd = [PY, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", "--tb=short"]
done = subprocess.run(cmd, cwd=CWD, env=env, capture_output=True, text=True, errors="replace", timeout=600)
(OUT / "pytest_output.txt").write_text(done.stdout + "\n---STDERR---\n" + done.stderr, encoding="utf-8")

text = done.stdout + "\n" + done.stderr


def count(word: str) -> int:
    total = 0
    for match in re.finditer(rf"(\d+)\s+{word}\b", text):
        total += int(match.group(1))
    return total


passed = count("passed")
failed = count("failed")
errors = count("error") + count("errors")
skipped = count("skipped")
xfailed = count("xfailed")
collected = passed + failed + errors + skipped + xfailed
row = {
    "suite": "weblens/tests",
    "command": " ".join(cmd),
    "cwd": "weblens",
    "pythonpath": "weblens/src",
    "exit_code": done.returncode,
    "passed": passed,
    "failed": failed,
    "errors": errors,
    "skipped": skipped,
    "xfailed": xfailed,
    "collected": collected,
}
emit(
    {
        "experiment": "EXP-01",
        "kind": "test-suite",
        "class": "REAL",
        "rows": [row],
        "summary": {
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "collected": collected,
            "exit_code": done.returncode,
        },
        "limitations": [
            "Root tests/ suite (second stack) was not run in this pass; its counts are NOT RUN, not passed.",
            "A passing suite is not evidence of runtime correctness; it only counts executed tests.",
        ],
    }
)
if done.returncode != 0:
    print(text[-4000:], file=sys.stderr)
