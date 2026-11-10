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
    # The inherited chain mixes three schema generations:
    #   (a) current:   id, started_utc, ended_utc, duration_s
    #   (b) legacy A:  experiment instead of id (V8_SESSION_SUMMARY)
    #   (c) legacy B:  single `utc` stamp and no duration (quality-loop records)
    # All three are hash-committed, so rewriting them would break a chain that
    # verifies. Instead the id is normalised, and a record is only treated as
    # malformed when it cannot be identified at all. A linter that crashes is a
    # linter that silently passes everything downstream of it.
    def _record_id(row: dict) -> str | None:
        for key in ("id", "experiment"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    ledger_rows: list[dict] = []
    for lineno, line in enumerate(build_report.LEDGER.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"ledger line {lineno}: not valid JSON ({exc})")
            continue
        if not isinstance(row, dict):
            problems.append(f"ledger line {lineno}: record is not a JSON object")
            continue
        rid = _record_id(row)
        if rid is None:
            problems.append(f"ledger line {lineno}: record has neither 'id' nor 'experiment'")
            continue
        ledger_rows.append({**row, "_rid": rid})
    ids = {row["_rid"] for row in ledger_rows}
    for key, metric in manifest.get("metrics", {}).items():
        for evidence in metric.get("evidence", []):
            if evidence.startswith("EXP-") and evidence not in ids:
                problems.append(f"{key}: unknown evidence id {evidence}")

    # 7. timestamps and durations
    # Per-record sanity for every inherited record, plus strict non-overlap for
    # this pass's runs (sorted by start). The inherited chain came from a prior
    # parallel session and contains genuine overlaps; that fact is reported in
    # meta.timeline_note instead of being silently ignored.
    # Only claims the record actually makes are checked: a legacy record with a
    # single `utc` stamp states no duration, so there is nothing to contradict.
    records = []
    for row in ledger_rows:
        rid = row["_rid"]
        started_raw = row.get("started_utc") or row.get("utc_start")
        ended_raw = row.get("ended_utc") or row.get("utc_end")
        if not (started_raw and ended_raw):
            # Legacy single-stamp record: no interval claimed, nothing to verify.
            continue
        try:
            started = datetime.fromisoformat(str(started_raw).replace("Z", "+00:00"))
            ended = datetime.fromisoformat(str(ended_raw).replace("Z", "+00:00"))
        except (TypeError, ValueError, AttributeError):
            problems.append(f"{rid}: unparseable timestamp")
            continue
        if ended < started:
            problems.append(f"{rid}: ended before started")
        duration_raw = row.get("duration_s")
        if duration_raw is not None:
            try:
                duration_s = float(duration_raw)
            except (TypeError, ValueError):
                problems.append(f"{rid}: 'duration_s' is not numeric")
                continue
            if abs((ended - started).total_seconds() - duration_s) > 5:
                problems.append(f"{rid}: duration does not match start/end")
        records.append((rid, started, ended))

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
