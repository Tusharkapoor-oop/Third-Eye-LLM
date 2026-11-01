"""EXP-001b: test suite with summary counts actually enabled.

EXP-001 ran with the package's `addopts = -q` plus an extra `-q`, which suppressed
the summary line and made the parser record zero executed tests. That run is kept
as superseded evidence; this run clears addopts so counts are emitted.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

from _common import ROOT, emit, run_dir

OUT = run_dir()
env = os.environ.copy()
env["PYTHONPATH"] = str(ROOT / "weblens" / "src")
env["PYTHONDONTWRITEBYTECODE"] = "1"

cmd = [
    sys.executable, "-m", "pytest", "tests",
    "-o", "addopts=", "-q", "-p", "no:cacheprovider", "--tb=short",
]
done = subprocess.run(cmd, cwd=ROOT / "weblens", env=env, capture_output=True, text=True, errors="replace", timeout=600)
text = done.stdout + "\n" + done.stderr
(OUT / "pytest_output.txt").write_text(text, encoding="utf-8")


def count(word: str) -> int:
    return sum(int(m.group(1)) for m in re.finditer(rf"(\d+)\s+{word}\b", text))


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
        "experiment": "EXP-001b",
        "kind": "test-suite",
        "class": "REAL",
        "rows": [row],
        "summary": {"passed": passed, "failed": failed, "errors": errors, "skipped": skipped,
                    "collected": collected, "exit_code": done.returncode},
        "limitations": [
            "This is the second attempt: EXP-001 parsed zero counts because of duplicated quiet flags.",
            "The root tests/ suite and root stack were not run; no combined count is reported.",
            "A passing suite is not evidence of runtime correctness.",
        ],
    }
)
if passed == 0:
    print("FAIL: zero passed tests parsed", file=sys.stderr)
    raise SystemExit(1)
