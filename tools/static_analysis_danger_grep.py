#!/usr/bin/env python3
"""Dependency-free static analysis scanner for dangerous patterns in WebLens and WebIntel codebases.

Scans for:
- eval / exec
- subprocess with shell=True
- os.system / os.popen
- pickle deserialization
- unsafe YAML loading
- unparameterized SQL queries (f-strings or % formatting in execute calls)
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEARCH_DIRS = [ROOT / "weblens" / "src", ROOT / "src"]


def scan_file(path: Path) -> list[dict]:
    findings = []
    content = path.read_text(encoding="utf-8", errors="ignore")
    rel_path = str(path.relative_to(ROOT)).replace("\\", "/")

    # 1. Regex checks
    patterns = [
        (r"\beval\s*\(", "eval_call", "high", "Dynamic code evaluation via eval()"),
        (r"\bexec\s*\(", "exec_call", "high", "Dynamic code execution via exec()"),
        (r"\bos\.system\s*\(", "os_system", "high", "Command execution via os.system()"),
        (r"\bos\.popen\s*\(", "os_popen", "high", "Command execution via os.popen()"),
        (r"\bpickle\.(?:loads?|Unpickler)\b", "pickle_deserialization", "high", "Unsafe deserialization via pickle"),
        (r"\byaml\.load\s*\([^,)]+\)", "unsafe_yaml", "medium", "Potentially unsafe YAML load without SafeLoader"),
        (r"\.execute\s*\(\s*f['\"]", "sql_fstring", "high", "SQL query constructed via f-string (SQL injection risk)"),
        (r"\.execute\s*\([^,)]*%\s*[^,)]*\)", "sql_percent", "high", "SQL query constructed via % formatting (SQL injection risk)"),
    ]

    for line_idx, line in enumerate(content.splitlines(), start=1):
        line_clean = line.strip()
        if line_clean.startswith("#"):
            continue
        for pat, rule_id, sev, desc in patterns:
            if re.search(pat, line):
                findings.append({
                    "file": rel_path,
                    "line": line_idx,
                    "rule": rule_id,
                    "severity": sev,
                    "description": desc,
                    "snippet": line_clean[:120],
                })

    # 2. AST check for subprocess shell=True
    try:
        tree = ast.parse(content, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                elif isinstance(node.func, ast.Name):
                    func_name = node.func.id
                if func_name in {"run", "Popen", "call", "check_call", "check_output"}:
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            findings.append({
                                "file": rel_path,
                                "line": node.lineno,
                                "rule": "subprocess_shell_true",
                                "severity": "high",
                                "description": "subprocess called with shell=True",
                                "snippet": content.splitlines()[node.lineno - 1].strip()[:120],
                            })
    except Exception:
        pass

    return findings


def main():
    print("Running static analysis security scan...")
    all_findings = []
    scanned_files = 0

    for d in SEARCH_DIRS:
        if d.exists():
            for p in d.rglob("*.py"):
                scanned_files += 1
                findings = scan_file(p)
                all_findings.extend(findings)

    report = {
        "files_scanned": scanned_files,
        "findings_count": len(all_findings),
        "findings": all_findings,
    }

    out_file = ROOT / "evidence" / "static_analysis_findings.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    main()

