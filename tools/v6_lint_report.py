#!/usr/bin/env python
"""v6 numeric and provenance linter.

Fails if the chain is broken, the report is not a byte-identical rebuild, a numeric
token is absent from the manifest, a proportion/mean lacks n or an interval, a
small-n value lacks the required caveat, a forbidden phrase appears, the empty-file
hash appears, a metric cites an unknown run, or this pass's runs overlap.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import v6_build_report as builder  # noqa: E402

NUMBER_RE = builder.NUMBER_RE
FORBIDDEN = ["certified", "production ready", "production-ready", "zero vulnerabilities",
             "fully secure", "impenetrable", "guaranteed", "hallucination-free"]
EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def main() -> int:
    problems: list[str] = []
    ok, chain_problems, chain = builder.verify_chain()
    if not ok:
        problems.extend(chain_problems[:5])

    report = builder.OUT_REPORT
    manifest_path = builder.OUT_MANIFEST
    if not report.exists() or not manifest_path.exists():
        print("FAIL report or manifest missing", file=sys.stderr)
        return 1
    text = report.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    try:
        fresh, fresh_manifest = builder.build()
    except builder.BuildError as exc:
        problems.append(f"rebuild failed: {exc}")
        fresh, fresh_manifest = "", {}
    if fresh != text:
        problems.append("report is not byte-identical to a fresh rebuild")
    if fresh_manifest != manifest:
        problems.append("manifest differs from a fresh rebuild")

    allowed = set(manifest.get("allowed_numbers", []))
    for token in NUMBER_RE.findall(text):
        if token not in allowed:
            problems.append(f"untraceable number in report: {token}")

    lowered = text.lower()
    for phrase in FORBIDDEN:
        if phrase in lowered:
            problems.append(f"forbidden phrase: {phrase}")
    if EMPTY_SHA in lowered:
        problems.append("report contains the SHA-256 of an empty file")

    for key, metric in manifest.get("metrics", {}).items():
        if metric["kind"] in {"proportion", "continuous"}:
            if metric.get("n") is None or metric.get("ci") is None:
                problems.append(f"{key}: missing n or interval")
            if metric.get("n") is not None and metric["n"] < 30 and "too small to support a claim" not in metric["value"]:
                problems.append(f"{key}: n<30 without caveat")
        if metric.get("class") == "SIMULATED" and "SIMULATED" not in text:
            problems.append("simulated metrics present but report does not label them")

    ids = {rec["id"] for rec in chain["runs"]}
    for key, metric in manifest.get("metrics", {}).items():
        for evidence in metric.get("evidence", []):
            if evidence.startswith("EXP-") and evidence not in ids:
                problems.append(f"{key}: unknown evidence id {evidence}")

    records = []
    for rec in chain["runs"]:
        try:
            start, end = builder.interval(rec)
        except (TypeError, ValueError):
            problems.append(f"{rec.get('id')}: unparseable timestamp")
            continue
        if end < start:
            problems.append(f"{rec['id']}: ended before started")
        if abs((end - start).total_seconds() - float(rec["duration_s"])) > 5:
            problems.append(f"{rec['id']}: duration does not match start/end")
        records.append((rec["id"], start, end))

    current = sorted((r for r in records if r[0] in builder.REQUIRED), key=lambda r: r[1])
    previous_end = None
    for rid, started, _ in current:
        if previous_end is not None and started < previous_end:
            problems.append(f"{rid}: this pass's runs overlap in time")
        previous_end = records[[r[0] for r in records].index(rid)][2]

    if "tavily" not in lowered:
        problems.append("report omits Tavily")
    if "not run" not in lowered:
        problems.append("report does not mark unrun competitors")
    for needle in ("Honesty section", "Evidence provenance", "NOT RUN"):
        if needle.lower() not in lowered:
            problems.append(f"missing section marker: {needle}")

    if problems:
        for problem in problems:
            print(f"FAIL {problem}")
        print(f"FAIL {len(problems)} lint problem(s)")
        return 1
    print(f"PASS lint: {len(manifest['metrics'])} metrics traceable, chain verified, report reproducible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
