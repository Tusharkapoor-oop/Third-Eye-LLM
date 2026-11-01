#!/usr/bin/env python
"""Numeric and provenance linter for the generated report.

Fails the build if any numeric token in the report is absent from the reporter
manifest, if a claimed metric lacks n/interval, if a forbidden phrase appears, if
the ledger chain is broken, if a timestamp is impossible, or if the report is not
byte-identical to a fresh rebuild.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_report  # noqa: E402
import verify_evidence  # noqa: E402

NUMBER_RE = re.compile(r"(?<![0-9A-Za-z_])[0-9]+(?:\.[0-9]+)?(?![0-9A-Za-z_])")
FORBIDDEN = [
    "certified",
    "production ready",
    "production-ready",
    "zero vulnerabilities",
    "fully secure",
    "impenetrable",
    "guaranteed",
    "hallucination-free",
]
EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
LABELS = {"ACHIEVED_10X", "PARTIAL", "TIE_OR_WORSE", "NOT_ESTABLISHED"}


def main() -> int:
    problems: list[str] = []
    report = build_report.OUT_REPORT
    manifest_path = build_report.OUT_MANIFEST

    ok, chain_problems, _ = verify_evidence.verify(build_report.LEDGER, check_files=True)
    if not ok:
        problems.extend(chain_problems[:5])

    if not report.exists() or not manifest_path.exists():
        print("FAIL report or manifest missing", file=sys.stderr)
        return 1
    text = report.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # 1. reproducible rebuild
    try:
        fresh, fresh_manifest = build_report.build()
    except build_report.BuildError as exc:
        problems.append(f"rebuild failed: {exc}")
        fresh, fresh_manifest = "", {}
    if fresh != text:
        problems.append("report is not byte-identical to a fresh rebuild")
    if fresh_manifest != manifest:
        problems.append("manifest differs from a fresh rebuild")

    # 2. numeric traceability
    allowed = set(manifest.get("allowed_numbers", []))
    for token in NUMBER_RE.findall(text):
        if token not in allowed:
            problems.append(f"untraceable number in report: {token}")

    # 3. forbidden phrases
    lowered = text.lower()
    for phrase in FORBIDDEN:
        if phrase in lowered:
            problems.append(f"forbidden phrase: {phrase}")

    # 4. empty-file hash
    if EMPTY_SHA in lowered:
        problems.append("report contains the SHA-256 of an empty file")

    # 5. metric integrity
    for key, metric in manifest.get("metrics", {}).items():
        kind = metric["kind"]
        value = metric["value"]
        if kind in {"proportion", "continuous"}:
            if metric.get("n") is None or metric.get("ci") is None:
                problems.append(f"{key}: missing n or interval")
            if metric.get("n") is not None and metric["n"] < 30 and "too small to support a claim" not in value:
                problems.append(f"{key}: n<30 without the required caveat")
        if kind == "label" and value not in LABELS:
            problems.append(f"{key}: verdict label not from the pre-registered set")
        if kind == "ratio":
            expected = build_report.stats.label_ratio(metric["ratio"], metric["lower_ci"])
            if value != expected:
                problems.append(f"{key}: label {value} != rule-derived {expected}")
        if metric.get("class") == "SIMULATED" and kind in {"proportion", "continuous"}:
            if "SIMULATED" not in text:
                problems.append("simulated metrics present but report does not label them")

    # 6. run ids referenced by metrics must exist in the ledger
    ids = {json.loads(line)["id"] for line in build_report.LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()}
    for key, metric in manifest.get("metrics", {}).items():
        for evidence in metric.get("evidence", []):
            if evidence.startswith("EXP-") and evidence not in ids:
                problems.append(f"{key}: unknown evidence id {evidence}")

    # 7. timestamps and durations
    # Per-record sanity for every inherited record, plus strict non-overlap for
    # this pass's runs (sorted by start). The inherited chain came from a prior
    # parallel session and contains genuine overlaps; that fact is reported in
    # meta.timeline_note instead of being silently ignored.
    records = []
    for line in build_report.LEDGER.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        try:
            started_raw = rec.get("started_utc") or rec.get("utc_start")
            ended_raw = rec.get("ended_utc") or rec.get("utc_end")
            started = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
            ended = datetime.fromisoformat(ended_raw.replace("Z", "+00:00"))
        except (KeyError, ValueError, AttributeError):
            problems.append(f"{rec.get('id')}: unparseable timestamp")
            continue
        if ended < started:
            problems.append(f"{rec['id']}: ended before started")
        if abs((ended - started).total_seconds() - float(rec["duration_s"])) > 5:
            problems.append(f"{rec['id']}: duration does not match start/end")
        records.append((rec["id"], started, ended))

    current = sorted((r for r in records if r[0] in build_report.REQUIRED), key=lambda r: r[1])
    previous_end = None
    for rid, started, ended in current:
        if previous_end is not None and started < previous_end:
            problems.append(f"{rid}: this pass's runs overlap in time")
        previous_end = ended

    # 8. competitor honesty
    if "tavily" not in lowered:
        problems.append("report omits Tavily entirely")
    elif "not run" not in lowered:
        problems.append("report does not mark unrun competitors")

    # 9. report markers
    for needle in ("Honesty section", "Evidence provenance", "NOT RUN"):
        if needle.lower() not in lowered:
            problems.append(f"report missing required section marker: {needle}")

    if problems:
        for problem in problems:
            print(f"FAIL {problem}")
        print(f"FAIL {len(problems)} lint problem(s)")
        return 1
    print(f"PASS lint: {len(manifest['metrics'])} metrics traceable, chain verified, report reproducible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
