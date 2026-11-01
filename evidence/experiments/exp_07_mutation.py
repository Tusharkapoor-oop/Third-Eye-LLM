"""EXP-07 (Gate 1): tamper detection and broken-build sensitivity.

Three checks:
1. Mutate a copied ledger record -> chain verification must fail.
2. Mutate a copied raw artifact -> artifact-hash verification must fail.
3. Disable the SSRF guard in a copied package -> the existing SSRF tests must fail.

If any of these pass silently, the corresponding evidence must be discarded.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _common import ROOT, emit

sys.path.insert(0, str(ROOT / "tools"))
import verify_evidence  # noqa: E402

LEDGER = ROOT / "evidence" / "ledger.jsonl"
rows: list[dict] = []


def copy_tree() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="tamper-"))
    shutil.copytree(ROOT / "evidence", tmp / "evidence")
    return tmp


with tempfile.TemporaryDirectory() as raw_tmp:
    root = Path(raw_tmp)
    shutil.copytree(ROOT / "evidence", root / "evidence")
    ok_before, problems_before, _ = verify_evidence.verify(root / "evidence" / "ledger.jsonl", root=root)

    # 1. ledger record mutation
    ledger = root / "evidence" / "ledger.jsonl"
    lines = [line for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    first = json.loads(lines[0])
    first["exit_code"] = 0 if first.get("exit_code") != 0 else 1
    lines[0] = json.dumps(first, sort_keys=True)
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok_ledger, problems_ledger, _ = verify_evidence.verify(ledger, root=root, check_files=False)
    rows.append(
        {
            "case": "ledger_record_tamper",
            "detected": (not ok_ledger) and bool(problems_ledger),
            "detail": problems_ledger[0] if problems_ledger else "not detected",
        }
    )

    # 2. raw artifact mutation (restore ledger first)
    shutil.copyfile(ROOT / "evidence" / "ledger.jsonl", ledger)
    target = None
    for entry in first.get("files", []):
        candidate = root / entry["path"]
        if candidate.exists() and candidate.suffix in {".json", ".txt"}:
            target = candidate
            break
    if target is not None:
        data = bytearray(target.read_bytes())
        if data:
            index = len(data) // 2
            data[index] = data[index] ^ 0x01
        else:
            data = bytearray(b"tampered")
        target.write_bytes(bytes(data))
        ok_raw, problems_raw, _ = verify_evidence.verify(ledger, root=root, check_files=True)
        rows.append(
            {
                "case": "raw_artifact_tamper",
                "detected": (not ok_raw) and any("artifact hash mismatch" in p for p in problems_raw),
                "detail": target.name,
            }
        )
    else:
        rows.append({"case": "raw_artifact_tamper", "detected": None, "detail": "no artifact available"})

    rows.append(
        {
            "case": "clean_copy_verifies",
            "detected": ok_before,
            "detail": f"problems={problems_before[:2]}",
        }
    )

# 3. broken-build mutation: turn the SSRF guard off and run the package's own tests.
with tempfile.TemporaryDirectory() as mut_tmp:
    base = Path(mut_tmp)
    pkg_root = base / "pkg"
    shutil.copytree(
        ROOT / "weblens" / "src" / "weblens",
        pkg_root / "weblens",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(
        ROOT / "weblens" / "tests",
        base / "tests",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    ssrf = pkg_root / "weblens" / "net" / "ssrf.py"
    text = ssrf.read_text(encoding="utf-8")
    mutated = text.replace("if self.s.allow_private_networks:\n            return", "if True:\n            return")
    patches = text.count("if self.s.allow_private_networks:")
    ssrf.write_text(mutated, encoding="utf-8")
    (base / "pytest.ini").write_text(
        "[pytest]\nasyncio_mode = auto\ntestpaths = tests\npythonpath = pkg\naddopts = -q -p no:cacheprovider\n",
        encoding="utf-8",
    )
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_ssrf.py", "-q", "-p", "no:cacheprovider", "--tb=no"],
        cwd=base,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=300,
    )
    out = done.stdout + done.stderr
    (Path(ROOT / "evidence" / "raw" / __import__("os").environ["EVIDENCE_RUN_ID"]) / "mutation_pytest.txt").write_text(
        out, encoding="utf-8"
    )
    import re

    match = re.search(r"(\d+)\s+failed", out)
    failed = int(match.group(1)) if match else 0
    rows.append(
        {
            "case": "broken_build_ssrf_guard_off",
            "detected": failed > 0,
            "detail": f"guard_sites_patched={patches} failed_tests={failed} exit={done.returncode}",
        }
    )

emit(
    {
        "experiment": "EXP-07",
        "kind": "mutation-and-tamper",
        "class": "REAL",
        "rows": rows,
        "summary": {
            "cases": len(rows),
            "detected": sum(1 for r in rows if r["detected"] is True),
        },
        "limitations": [
            "Only the SSRF guard was mutation-tested; token-cap, injection-scanner and random-result mutations are NOT RUN.",
            "Tamper tests mutate copies of the evidence tree, never the committed ledger.",
        ],
    }
)
