#!/usr/bin/env python
"""Hash-chained evidence runner (backward compatible with the first chain).

Every experiment that can support a claim is executed through this script. Each
run appends one JSON line to ``evidence/ledger.jsonl`` containing argv, cwd, git
commit, working-tree hash, versions, UTC start/end, monotonic duration, exit code,
SHA-256 of stdout/stderr and every output file, plus ``prev_hash`` and ``hash``.

Secrets are redacted before writing. A run whose output still matched a
credential pattern is marked CONTAMINATED and the reporter excludes it. Run ids
are immutable: reusing an existing id is refused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = ROOT / "evidence"
RAW_DIR = EVIDENCE_DIR / "raw"
LEDGER_PATH = EVIDENCE_DIR / "ledger.jsonl"
GENESIS = "0" * 64

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,80}$")

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("tavily", re.compile(r"tvly-[A-Za-z0-9_-]{10,}", re.IGNORECASE)),
    ("openai", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("github", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}")),
    ("aws", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}")),
    ("bearer", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{20,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("env_assignment", re.compile(r"(?i)\b(?:TAVILY|BRAVE|EXA|OPENAI|ANTHROPIC)_API_KEY\s*=\s*[^\s'\"]{8,}")),
]

ENV_SECRET_NAMES = (
    "TAVILY_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "BRAVE_API_KEY",
    "EXA_API_KEY",
    "WEBLENS_HTTP_TOKEN",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_git(*args: str) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=30, check=False
        )
        return done.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def tree_fingerprint() -> str:
    payload = run_git("diff", "HEAD", "--binary") + "\n--STATUS--\n" + run_git("status", "--porcelain=v1")
    return hashlib.sha256(payload.encode("utf-8", "replace")).hexdigest()


def load_known_secrets() -> list[str]:
    secrets = [os.environ.get(name, "") for name in ENV_SECRET_NAMES]
    for env_file in (ROOT / ".env", ROOT / "weblens" / ".env"):
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if "=" not in line or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip("'\"")
            if any(token in key.upper() for token in ("KEY", "SECRET", "TOKEN")) and len(value) > 8:
                secrets.append(value)
    return [s for s in secrets if len(s) >= 8]


def redact(text: str, known: list[str]) -> tuple[str, list[str]]:
    hits: list[str] = []
    for value in known:
        if value and value in text:
            text = text.replace(value, "[REDACTED:env]")
            hits.append("env")
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            text = pattern.sub(f"[REDACTED:{name}]", text)
            hits.append(name)
    return text, sorted(set(hits))


def last_hash() -> str:
    if not LEDGER_PATH.exists():
        return GENESIS
    last = ""
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            last = line
    return json.loads(last)["hash"] if last else GENESIS


def versions() -> dict[str, str]:
    out = {"python": platform.python_version(), "platform": f"{platform.system()} {platform.release()}"}
    for name in ("pytest", "httpx", "trafilatura", "pymupdf", "tiktoken", "mcp", "playwright"):
        try:
            module = __import__(name)
            out[name] = str(getattr(module, "__version__", "unknown"))
        except Exception:
            out[name] = "absent"
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hash-chained evidence runner")
    parser.add_argument("--id", required=True)
    parser.add_argument("--class", dest="run_class", required=True, choices=["REAL", "SIMULATED", "MOCK"])
    parser.add_argument("--note", default="", help="what this run is supposed to establish")
    parser.add_argument("--metadata", default="{}", help="JSON metadata (legacy)")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("cmd", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    if not ID_RE.match(args.id):
        parser.error("invalid --id")
    cmd = [c for c in args.cmd if c != "--"]
    if not cmd:
        parser.error("missing command after --")

    run_dir = RAW_DIR / args.id
    if run_dir.exists():
        print(f"refusing to overwrite existing run {args.id}", file=sys.stderr)
        return 2
    run_dir.mkdir(parents=True)

    known = load_known_secrets()
    started_utc = utc_now()
    t0 = time.perf_counter()
    timed_out = False
    env = os.environ.copy()
    env["EVIDENCE_RUN_ID"] = args.id
    env["EVIDENCE_RAW_DIR"] = str(run_dir)
    env["EVIDENCE_CLASS"] = args.run_class
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("PYTHONHASHSEED", "0")
    try:
        proc = subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True, errors="replace", env=env, timeout=args.timeout
        )
        stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        code = 124
    duration = round(time.perf_counter() - t0, 6)
    ended_utc = utc_now()

    clean_stdout, hits_out = redact(stdout, known)
    clean_stderr, hits_err = redact(stderr, known)
    (run_dir / "stdout.txt").write_text(clean_stdout, encoding="utf-8")
    (run_dir / "stderr.txt").write_text(clean_stderr, encoding="utf-8")

    contaminated_files: list[str] = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name == "record.json":
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        clean, hits = redact(content, known)
        if hits:
            path.write_text(clean, encoding="utf-8")
            contaminated_files.append(str(path.relative_to(ROOT)).replace("\\", "/"))

    files: list[dict[str, Any]] = []
    outputs: dict[str, str] = {}
    for path in sorted(run_dir.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            digest = sha256_file(path)
            outputs[rel] = digest
            files.append({"path": rel, "sha256": digest, "bytes": path.stat().st_size})

    try:
        metadata = json.loads(args.metadata)
    except json.JSONDecodeError:
        metadata = {"raw": args.metadata}

    record: dict[str, Any] = {
        "id": args.id,
        "class": args.run_class,
        "note": args.note,
        "argv": cmd,
        "cwd": str(ROOT),
        "git_commit": run_git("rev-parse", "HEAD"),
        "git_branch": run_git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_diff_hash": tree_fingerprint(),
        "tree_hash": tree_fingerprint(),
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "machine": platform.machine(),
        "versions": versions(),
        "utc_start": started_utc,
        "utc_end": ended_utc,
        "started_utc": started_utc,
        "ended_utc": ended_utc,
        "duration_s": duration,
        "exit_code": code,
        "timed_out": timed_out,
        "redactions": sorted(set(hits_out + hits_err)),
        "contaminated": bool(contaminated_files),
        "contaminated_files": contaminated_files,
        "files": files,
        "outputs": outputs,
        "metadata": metadata,
        "prev_hash": "",
    }
    record["prev_hash"] = last_hash()
    record["hash"] = hashlib.sha256((record["prev_hash"] + canonical_json(record)).encode("utf-8")).hexdigest()

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(canonical_json(record) + "\n")

    print(
        json.dumps(
            {
                "id": record["id"],
                "class": record["class"],
                "exit_code": code,
                "duration_s": duration,
                "contaminated": record["contaminated"],
                "files": len(files),
                "ledger_head": record["hash"],
            },
            indent=2,
        )
    )
    return 0 if code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
