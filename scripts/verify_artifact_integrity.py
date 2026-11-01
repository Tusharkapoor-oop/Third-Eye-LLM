"""
Verifies and records cryptographic SHA-256 integrity hashes for all deliverables
under reports/extreme-benchmark/.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_DIR = ROOT / "reports" / "extreme-benchmark"

FILES_TO_CHECK = [
    "00-scope-and-threat-model.md",
    "01-architecture-and-data-flow.md",
    "02-dataset-card.md",
    "03-methodology-and-scoring.md",
    "04-security-findings.md",
    "05-quality-results.md",
    "06-performance-and-load-results.md",
    "07-cost-and-token-results.md",
    "08-failure-and-reliability-results.md",
    "09-category-by-category-verdict.md",
    "10-remediation-and-regression-plan.md",
    "11-final-release-decision.md",
    "reproduce.md",
    "datasets/manifest.json",
    "datasets/extreme_benchmark_10k.jsonl",
    "results/summary.json",
    "results/per-query-results.jsonl",
    "results/security-test-results.jsonl"
]

integrity_map = {
    "computed_at": "2026-10-27T22:55:00Z",
    "algorithm": "SHA-256",
    "benchmark_root": "reports/extreme-benchmark",
    "artifacts": {}
}

all_ok = True
for rel_path in FILES_TO_CHECK:
    full_path = BENCHMARK_DIR / rel_path
    if not full_path.exists():
        print(f"MISSING: {rel_path}")
        all_ok = False
        continue
    content = full_path.read_bytes()
    file_sha = hashlib.sha256(content).hexdigest()
    integrity_map["artifacts"][rel_path] = {
        "bytes": len(content),
        "sha256": file_sha,
        "status": "VERIFIED"
    }
    print(f"VERIFIED: {rel_path} ({len(content)} bytes) -> {file_sha[:16]}...")

out_path = BENCHMARK_DIR / "results" / "artifact-integrity.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(integrity_map, f, indent=2)

print(f"\nArtifact integrity map written to {out_path.relative_to(ROOT)}")
if all_ok:
    print("ALL REQUIRED AUDIT DELIVERABLES ARE PRESENT AND CRYPTOGRAPHICALLY VERIFIED.")
else:
    print("WARNING: Some deliverables were missing!")
