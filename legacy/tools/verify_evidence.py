#!/usr/bin/env python
"""Verify the evidence ledger chain and every recorded artifact hash.

Supports both record shapes used in this pass: the first chain's ``utc_start`` /
``outputs`` mapping and the extended ``started_utc`` / ``files`` list.

Exit code 0 only if the chain is intact and every hashed file matches.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "evidence" / "ledger.jsonl"
GENESIS = "0" * 64


def canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def artifacts(record: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for entry in record.get("files", []) or []:
        if isinstance(entry, dict) and "path" in entry and "sha256" in entry:
            out.append((entry["path"], entry["sha256"]))
    outputs = record.get("outputs")
    if isinstance(outputs, dict):
        out.extend((path, digest) for path, digest in outputs.items())
    return out


def verify(ledger: Path = LEDGER, check_files: bool = True, root: Path = ROOT) -> tuple[bool, list[str], dict]:
    problems: list[str] = []
    if not ledger.exists():
        return False, ["ledger missing"], {}
    prev = GENESIS
    count = 0
    ids: set[str] = set()
    classes: dict[str, int] = {}
    with ledger.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                problems.append(f"line {lineno}: invalid JSON: {exc}")
                continue
            count += 1
            rid = rec.get("id", f"line{lineno}")
            if rid in ids:
                problems.append(f"{rid}: duplicate id")
            ids.add(rid)
            klass = rec.get("class", "?")
            classes[klass] = classes.get(klass, 0) + 1
            if rec.get("prev_hash") != prev:
                problems.append(f"{rid}: prev_hash mismatch")
            claimed = rec.get("hash", "")
            body = {k: v for k, v in rec.items() if k != "hash"}
            expected = hashlib.sha256((prev + canonical(body)).encode("utf-8")).hexdigest()
            if claimed != expected:
                problems.append(f"{rid}: record hash mismatch")
            prev = claimed
            if check_files:
                for rel, digest in artifacts(rec):
                    path = root / rel
                    if not path.exists():
                        problems.append(f"{rid}: missing artifact {rel}")
                    elif sha256_file(path) != digest:
                        problems.append(f"{rid}: artifact hash mismatch {rel}")
    return not problems, problems, {"runs": count, "ids": sorted(ids), "classes": classes, "head": prev}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-files", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    ok, problems, meta = verify(check_files=not args.no_files)
    if args.json:
        print(json.dumps({"ok": ok, "problems": problems, "meta": meta}, indent=2))
    else:
        print(f"runs: {meta.get('runs', 0)}")
        print(f"classes: {meta.get('classes', {})}")
        print(f"head: {meta.get('head', GENESIS)}")
        for problem in problems:
            print(f"FAIL {problem}")
        print("PASS evidence chain and artifact hashes" if ok else f"FAIL {len(problems)} problem(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
