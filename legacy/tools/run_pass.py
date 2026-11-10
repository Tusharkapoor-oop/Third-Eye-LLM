#!/usr/bin/env python
"""Resumable driver for this pass's experiments.

Runs only missing experiment ids through the evidence runner. An id that exists in
the ledger but whose result.json is missing is reported as an error rather than
silently re-run (run ids are immutable).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "evidence" / "ledger.jsonl"

PLAN = [
    ("EXP-000", "REAL", "evidence/experiments/exp_00_state.py", "pin environment and prereg"),
    ("EXP-001b", "REAL", "evidence/experiments/exp_01b_tests.py", "weblens test suite, corrected counts"),
    ("EXP-002", "SIMULATED", "evidence/experiments/exp_02_ssrf.py", "SSRF loopback matrix"),
    ("EXP-003", "SIMULATED", "evidence/experiments/exp_03_injection.py", "injection scanner corpus"),
    ("EXP-004b", "REAL", "evidence/experiments/exp_04b_cache.py", "cache correctness, corrected eviction payload"),
    ("EXP-005", "SIMULATED", "evidence/experiments/exp_05_extract.py", "extraction fixtures"),
    ("EXP-006", "REAL", "evidence/experiments/exp_06_tokens.py", "MCP schema tokens"),
    ("EXP-007b", "REAL", "evidence/experiments/exp_07b_mutation.py", "mutation and tamper, corrected counting"),
    ("EXP-008", "REAL", "evidence/experiments/exp_08_secrets.py", "secret scan"),
]


def ledger_ids() -> set[str]:
    if not LEDGER.exists():
        return set()
    return {json.loads(line)["id"] for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()}


def main() -> int:
    ids = ledger_ids()
    failures = 0
    for rid, klass, script, note in PLAN:
        raw = ROOT / "evidence" / "raw" / rid
        if rid in ids:
            if not (raw / "result.json").exists():
                print(f"ERROR {rid}: ledger entry exists but result.json is missing; use a new id")
                failures += 1
            else:
                print(f"SKIP {rid}: already recorded")
            continue
        if raw.exists():
            print(f"ERROR {rid}: stale run directory without ledger entry; inspect before proceeding")
            failures += 1
            continue
        cmd = [
            sys.executable, str(ROOT / "tools" / "evidence_run.py"),
            "--id", rid, "--class", klass, "--note", note, "--timeout", "600",
            "--", sys.executable, str(ROOT / script),
        ]
        print(f"RUN {rid} [{klass}] {note}", flush=True)
        done = subprocess.run(cmd, cwd=ROOT)
        if done.returncode != 0:
            print(f"FAIL {rid}: runner exit {done.returncode}", flush=True)
            failures += 1
    print(f"pass failures: {failures}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
