"""EXP-08: secret exposure scan and redaction self-test.

Values are never printed. The scan reports pattern kinds, file paths and boolean
comparisons only. ``.env`` is expected to hold the live key and is excluded from
the tree scan (it is git-ignored); ``.env.example`` is inspected by shape only.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from _common import ROOT, emit

sys.path.insert(0, str(ROOT / "tools"))
from evidence_run import SECRET_PATTERNS, redact  # noqa: E402

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "evidence",
    "test-results",
    ".freebuff",
}
TEXT_SUFFIXES = {
    ".py", ".md", ".json", ".jsonl", ".toml", ".yaml", ".yml", ".txt", ".ini", ".cfg", ".html", ".js", ".ts",
    ".sh", ".ps1", ".env", ".example", ".csv", ".xml", ".lock", ".gitignore", "",
}

tree_hits: list[dict] = []
scanned = 0
for path in ROOT.rglob("*"):
    if not path.is_file():
        continue
    rel_parts = set(path.relative_to(ROOT).parts)
    if rel_parts & EXCLUDE_DIRS:
        continue
    if path.name in {".env"}:
        continue
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {".gitignore", ".env.example"}:
        continue
    if path.stat().st_size > 2_000_000:
        continue
    scanned += 1
    text = path.read_text(encoding="utf-8", errors="replace")
    for name, pattern in SECRET_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            tree_hits.append(
                {
                    "kind": name,
                    "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "matches": len(matches),
                    "equals_live_env_key": any(m == os.environ.get("TAVILY_API_KEY", "") for m in matches),
                }
            )

env_example = ROOT / ".env.example"
example_facts: dict[str, object] = {"exists": env_example.exists()}
if env_example.exists():
    text = env_example.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^TAVILY_API_KEY[^\S\r\n]*=[^\S\r\n]*(.*)$", text, re.M)
    value = (match.group(1).strip() if match else "")
    example_facts.update(
        {
            "has_key_line": bool(match),
            "value_len_bucket": "0" if not value else ("1-20" if len(value) <= 20 else "21-80"),
            "starts_with_tvly": value.startswith("tvly-"),
            "looks_placeholder": bool(re.search(r"(your|changeme|example|replace|<|xxx|dummy)", value, re.I)),
            "matches_tvly_pattern": bool(re.search(r"tvly-[A-Za-z0-9_-]{10,}", value)),
        }
    )

# Git history scan: commit/path only, never the matched value.
history_hits: list[dict] = []
commits: list[str] = []
try:
    commits = subprocess.run(["git", "rev-list", "--all"], cwd=ROOT, capture_output=True, text=True, timeout=30).stdout.split()
    for commit in commits:
        done = subprocess.run(
            ["git", "grep", "-I", "-n", "-E", "tvly-[A-Za-z0-9_-]{10,}", commit, "--"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=60,
        )
        for line in done.stdout.splitlines():
            parts = line.split(":", 2)
            if len(parts) >= 2:
                history_hits.append({"commit": commit[:12], "path": parts[1]})
except Exception as exc:
    history_hits.append({"error": type(exc).__name__})

# Redaction self-test with a synthetic canary.
canary = "tvly-CANARY-" + "A" * 24
clean, hits = redact(f"leaked {canary} and Bearer abcdefghijklmnopqrstuvwxyz012345", [])
redaction_ok = canary not in clean and "CANARY" not in clean and "tavily" in hits

emit(
    {
        "experiment": "EXP-08",
        "kind": "secret-scan",
        "class": "REAL",
        "rows": [
            {"case": "tree_scan", "scanned_files": scanned, "hits": tree_hits},
            {"case": "env_example_shape", **example_facts},
            {"case": "git_history_scan", "commits": len(commits), "hits": history_hits},
            {"case": "redaction_self_test", "passed": redaction_ok, "hits": hits},
        ],
        "summary": {
            "files_scanned": scanned,
            "tree_hits": len(tree_hits),
            "history_hits": len(history_hits),
            "env_example_starts_with_tvly": example_facts.get("starts_with_tvly"),
            "env_example_looks_placeholder": example_facts.get("looks_placeholder"),
            "redaction_ok": redaction_ok,
        },
        "limitations": [
            "Pattern-based scan only; gitleaks/trufflehog are not installed, so this is not a substitute for them.",
            "No entropy analysis; a credential that matches no known shape would not be found.",
        ],
    }
)
