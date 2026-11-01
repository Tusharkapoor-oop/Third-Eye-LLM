"""EXP-000: pin the subject and the environment before any scored run."""

from __future__ import annotations

import hashlib
import importlib.metadata as md
import json
import platform
import subprocess
import sys
from pathlib import Path

from _common import ROOT, emit

import weblens


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()


packages = {}
for name in ("mcp", "httpx", "httpcore", "trafilatura", "pymupdf", "tiktoken", "pydantic", "pydantic-settings", "pytest", "playwright"):
    try:
        packages[name] = md.version(name)
    except md.PackageNotFoundError:
        packages[name] = "absent"

files = [
    "weblens/src/weblens/service.py",
    "weblens/src/weblens/net/ssrf.py",
    "weblens/src/weblens/net/client.py",
    "weblens/src/weblens/net/browser_proxy.py",
    "weblens/src/weblens/extract/service.py",
    "weblens/src/weblens/security/injection.py",
    "weblens/src/weblens/cache.py",
    "weblens/src/weblens/mcp_server.py",
    "benchmarks/eval_dataset.json",
    "benchmarks/eval_dataset_expanded.json",
    "benchmarks/tavily_paired_subset.json",
    "evidence/prereg.md",
]

row = {
    "weblens_module": str(Path(weblens.__file__).resolve()),
    "weblens_version": weblens.__version__,
    "python": sys.version,
    "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
    "executable": sys.executable,
    "git_commit": git("rev-parse", "HEAD"),
    "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
    "git_status_porcelain": git("status", "--porcelain=v1").splitlines(),
    "packages": packages,
    "file_hashes": {path: sha(ROOT / path) for path in files if (ROOT / path).exists()},
    "environment_flags": {
        "searxng_url_set": bool(__import__("os").environ.get("WEBLENS_SEARXNG_URL")),
        "tavily_key_set": bool(__import__("os").environ.get("TAVILY_API_KEY")),
        "allow_browser_default": False,
    },
}

emit(
    {
        "experiment": "EXP-000",
        "kind": "baseline-state",
        "class": "REAL",
        "rows": [row],
        "summary": {
            "subject": row["weblens_module"],
            "commit": row["git_commit"][:12],
            "dirty_files": len(row["git_status_porcelain"]),
        },
        "limitations": [
            "The dirty tree includes pre-existing changes and this audit's tools; the tree hash in the ledger pins it.",
            "Package presence does not imply functionality; only executed paths count.",
        ],
    }
)
