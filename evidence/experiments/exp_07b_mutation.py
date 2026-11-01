"""EXP-007b: tamper and broken-build checks, with collection failures distinguished.

EXP-007's mutation run did fail 16 SSRF tests, but pytest's suppressed summary made
the parser record zero failures, and its artifact-tamper case skipped .log files.
This run fixes both and reports the counts from FAILED lines.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _common import ROOT, emit, run_dir

sys.path.insert(0, str(ROOT / "tools"))
import verify_evidence  # noqa: E402

rows: list[dict] = []
RUN_DIR = run_dir()

with tempfile.TemporaryDirectory() as raw_tmp:
    root = Path(raw_tmp)
    shutil.copytree(ROOT / "evidence", root / "evidence")
    ledger_src = ROOT / "evidence" / "ledger.jsonl"
    ledger = root / "evidence" / "ledger.jsonl"

    ok_before, problems_before, _ = verify_evidence.verify(ledger_src, root=root)
    rows.append({"case": "clean_copy_verifies", "detected": ok_before, "detail": f"problems={problems_before[:2]}"})

    lines = [line for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    first = json.loads(lines[0])
    first["exit_code"] = 0 if first.get("exit_code") != 0 else 1
    lines[0] = json.dumps(first, sort_keys=True)
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok_ledger, problems_ledger, _ = verify_evidence.verify(ledger, root=root, check_files=False)
    rows.append({"case": "ledger_record_tamper", "detected": (not ok_ledger) and bool(problems_ledger),
                 "detail": problems_ledger[0] if problems_ledger else "not detected"})

    shutil.copyfile(ledger_src, ledger)
    target = None
    for entry in verify_evidence.artifacts(first):
        candidate = root / entry[0]
        if candidate.exists() and candidate.is_file():
            target = candidate
            break
    if target is None:
        rows.append({"case": "raw_artifact_tamper", "detected": False, "detail": "no artifact available"})
    else:
        data = bytearray(target.read_bytes())
        if data:
            index = len(data) // 2
            data[index] ^= 0x01
        else:
            data = bytearray(b"tampered")
        target.write_bytes(bytes(data))
        ok_raw, problems_raw, _ = verify_evidence.verify(ledger, root=root, check_files=True)
        rows.append({"case": "raw_artifact_tamper",
                     "detected": (not ok_raw) and any("artifact hash mismatch" in p for p in problems_raw),
                     "detail": str(target.relative_to(root))})

with tempfile.TemporaryDirectory() as mut_tmp:
    base = Path(mut_tmp)
    shutil.copytree(ROOT / "weblens" / "src" / "weblens", base / "pkg" / "weblens",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(ROOT / "weblens" / "tests", base / "tests",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    ssrf = base / "pkg" / "weblens" / "net" / "ssrf.py"
    text = ssrf.read_text(encoding="utf-8")
    patches = text.count("if self.s.allow_private_networks:")
    ssrf.write_text(text.replace("if self.s.allow_private_networks:\n            return", "if True:\n            return"), encoding="utf-8")
    (base / "pytest.ini").write_text(
        "[pytest]\nasyncio_mode = auto\ntestpaths = tests\npythonpath = pkg\naddopts = -p no:cacheprovider\n",
        encoding="utf-8",
    )
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_ssrf.py", "-q", "--tb=no"],
        cwd=base, capture_output=True, text=True, errors="replace", timeout=300,
    )
    out = done.stdout + done.stderr
    (RUN_DIR / "mutation_pytest.txt").write_text(out, encoding="utf-8")
    match = re.search(r"(\d+)\s+failed", out)
    failed = int(match.group(1)) if match else len(re.findall(r"^FAILED ", out, re.M))
    failed_lines = len(re.findall(r"^FAILED ", out, re.M))
    rows.append({
        "case": "broken_build_ssrf_guard_off",
        "detected": failed > 0 or failed_lines > 0,
        "detail": f"guard_sites_patched={patches} failed_summary={failed} failed_lines={failed_lines} exit={done.returncode}",
    })

emit(
    {
        "experiment": "EXP-007b",
        "kind": "mutation-and-tamper",
        "class": "REAL",
        "rows": rows,
        "summary": {"cases": len(rows), "detected": sum(1 for r in rows if r["detected"] is True)},
        "limitations": [
            "Second attempt: EXP-007 could not count failures because the pytest summary was suppressed.",
            "Only the SSRF guard was mutation-tested; token-cap, scanner and random-result mutations are NOT RUN.",
            "Tamper tests mutate copies of the evidence tree, never the committed ledger.",
        ],
    }
)
