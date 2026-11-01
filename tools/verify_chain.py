#!/usr/bin/env python3
"""Cryptographic verification of the evidence ledger and output files."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "evidence" / "ledger.jsonl"


def canonical_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_ledger() -> bool:
    if not LEDGER_PATH.exists():
        print("ERROR: evidence/ledger.jsonl not found", file=sys.stderr)
        return False

    prev_hash = "0" * 64
    line_num = 0
    errors = 0

    with open(LEDGER_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            line_num += 1
            try:
                record = json.loads(line_str)
            except Exception as e:
                print(f"Line {line_num}: JSON decode error: {e}", file=sys.stderr)
                errors += 1
                continue

            expected_prev = record.get("prev_hash")
            claimed_hash = record.get("hash")
            record_id = record.get("id")

            if expected_prev != prev_hash:
                print(f"Line {line_num} (id={record_id}): prev_hash mismatch. Got {expected_prev}, expected {prev_hash}", file=sys.stderr)
                errors += 1

            rec_copy = dict(record)
            rec_copy.pop("hash", None)
            canonical = canonical_json(rec_copy)
            calculated_hash = hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()

            if calculated_hash != claimed_hash:
                print(f"Line {line_num} (id={record_id}): Hash invalid. Claimed {claimed_hash}, recomputed {calculated_hash}", file=sys.stderr)
                errors += 1

            # Verify outputs
            outputs = record.get("outputs", {})
            for rel_path, claimed_file_hash in outputs.items():
                p = ROOT / rel_path
                if not p.exists():
                    print(f"Line {line_num} (id={record_id}): Output file missing: {rel_path}", file=sys.stderr)
                    errors += 1
                else:
                    actual_file_hash = sha256_file(p)
                    if actual_file_hash != claimed_file_hash:
                        print(f"Line {line_num} (id={record_id}): File hash mismatch for {rel_path}. Claimed {claimed_file_hash}, actual {actual_file_hash}", file=sys.stderr)
                        errors += 1

            prev_hash = claimed_hash

    if errors == 0:
        print(f"PASS: Verified {line_num} ledger entries. Head hash: {prev_hash}")
        return True
    else:
        print(f"FAIL: Encountered {errors} integrity verification errors.", file=sys.stderr)
        return False


if __name__ == "__main__":
    success = verify_ledger()
    sys.exit(0 if success else 1)

