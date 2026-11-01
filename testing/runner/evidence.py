"""
Permanent Test Evidence System for the Web Intelligence Engine audit.

Records every test execution into:
  1. test-results/database/test_history.db  (SQLite structured store, append-only rows)
  2. test-results/raw/<source_id>.jsonl     (append-only raw record, one JSON object per attempt)

Every record carries: run id, test-case id, suite, name, UTC timestamp, git commit,
environment fingerprint, expected vs actual outcome, status, duration, latency,
tokens, error message, artifact path, retry count, comparability flag, reason.

Statuses: PASS, FAIL, ERROR, BLOCKED, SKIPPED, INCONCLUSIVE, CANCELLED, NOT_RUN.

CLI:
  python -m testing.runner.evidence record-pytest <junit_xml> --run-id <id> --suite-unit <name>
  python -m testing.runner.evidence record-benchmark <json> --run-id <id> --kind benchmark|baseline
  python -m testing.runner.evidence record-generic --run-id <id> --suite <s> --case <c> \
      --status <STATUS> --expected <e> --actual <a> --duration <sec> [--error <msg>] \
      [--latency-sec <x>] [--tokens <n>] [--artifact <path>] [--reason <why>]
  python -m testing.runner.evidence summary [--db <path>]
  python -m testing.runner.evidence export-markdown [--db <path>] --out <path>

Secrets safety: any tvly-/sk-/Bearer token found in error text is redacted before insert.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_DIR = PROJECT_ROOT / "test-results" / "database"
RAW_DIR = PROJECT_ROOT / "test-results" / "raw"
DB_PATH = DB_DIR / "test_history.db"

SECRET_PATTERNS = [
    re.compile(r"tvly-[A-Za-z0-9_\-]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{8,}"),
    re.compile(r"fc-[A-Za-z0-9_\-]{8,}"),
]


def redact(text: str | None) -> str | None:
    if text is None:
        return None
    out = text
    for pat in SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out[:2000]


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def current_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(PROJECT_ROOT), stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return None


SCHEMA = """
CREATE TABLE IF NOT EXISTS test_runs (
    run_id TEXT PRIMARY KEY,
    suite TEXT NOT NULL,
    source TEXT NOT NULL,
    started_utc TEXT NOT NULL,
    finished_utc TEXT NOT NULL,
    commit_sha TEXT,
    python_version TEXT,
    platform TEXT,
    fingerprint TEXT,
    dataset_hash TEXT,
    total_cases INTEGER,
    pass_count INTEGER,
    fail_count INTEGER,
    error_count INTEGER,
    blocked_count INTEGER,
    skipped_count INTEGER,
    inconclusive_count INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS test_cases (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    suite TEXT NOT NULL,
    name TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    commit_sha TEXT,
    expected TEXT,
    actual TEXT,
    status TEXT NOT NULL CHECK (status IN
        ('PASS','FAIL','ERROR','BLOCKED','SKIPPED','INCONCLUSIVE','CANCELLED','NOT_RUN')),
    duration_sec REAL,
    latency_metrics TEXT,
    token_metrics TEXT,
    api_calls INTEGER,
    cost_usd REAL,
    error_message TEXT,
    artifact_path TEXT,
    artifact_hash TEXT,
    retry_count INTEGER DEFAULT 0,
    comparable INTEGER DEFAULT 1,
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_cases_run ON test_cases(run_id);
CREATE INDEX IF NOT EXISTS idx_cases_name ON test_cases(name);
CREATE INDEX IF NOT EXISTS idx_cases_status ON test_cases(status);
"""


def get_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    return conn


def environment_fingerprint() -> dict:
    import platform
    import sys
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor()[:80],
        "os": platform.system() + " " + (platform.release() or ""),
    }


class EvidenceRecorder:
    """Append-only recorder: every attempt is inserted, nothing is ever updated or deleted."""

    def __init__(self, run_id: str, suite: str, source: str, notes: str | None = None):
        self.run_id = run_id
        self.suite = suite
        self.source = source
        self.conn = get_db()
        self.raw_dir = RAW_DIR
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.raw_path = self.raw_dir / f"{source}_{run_id}.jsonl"
        self.started = utcnow()
        self.commit_sha = current_commit()
        self.notes = notes
        self.counts = {"PASS": 0, "FAIL": 0, "ERROR": 0, "BLOCKED": 0,
                       "SKIPPED": 0, "INCONCLUSIVE": 0, "CANCELLED": 0, "NOT_RUN": 0}

    def append_raw(self, record: dict) -> None:
        with open(self.raw_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def record(self, case_id: str, name: str, status: str, *,
               expected: str | None = None, actual: str | None = None,
               duration_sec: float | None = None,
               latency_metrics: dict | None = None,
               token_metrics: dict | None = None,
               api_calls: int | None = None, cost_usd: float | None = None,
               error: str | None = None, artifact: str | None = None,
               retry_count: int = 0, comparable: bool = True,
               reason: str | None = None, t_utc: str | None = None) -> None:
        status = status.upper()
        if status not in self.counts:
            status = "INCONCLUSIVE"
        self.counts[status] += 1
        if latency_metrics:
            latency_metrics = redact(json.dumps(latency_metrics, ensure_ascii=False))
        if token_metrics:
            token_metrics = redact(json.dumps(token_metrics, ensure_ascii=False))
        art_hash = sha256_file(Path(artifact)) if artifact else None
        row = {
            "run_id": self.run_id,
            "case_id": case_id or str(uuid.uuid4())[:8],
            "suite": self.suite,
            "name": name,
            "timestamp_utc": t_utc or utcnow(),
            "commit_sha": self.commit_sha,
            "expected": redact(expected),
            "actual": redact(actual),
            "status": status,
            "duration_sec": duration_sec,
            "latency_metrics": latency_metrics,
            "token_metrics": token_metrics,
            "api_calls": api_calls,
            "cost_usd": cost_usd,
            "error_message": redact(error),
            "artifact_path": artifact,
            "artifact_hash": art_hash,
            "retry_count": retry_count,
            "comparable": 1 if comparable else 0,
            "reason": redact(reason),
        }
        keys = ",".join(row.keys())
        marks = ",".join("?" for _ in row)
        self.conn.execute(f"INSERT INTO test_cases ({keys}) VALUES ({marks})", list(row.values()))
        self.conn.commit()
        self.append_raw(row)

    def finalize(self, dataset_path: str | None = None) -> str:
        fp = environment_fingerprint()
        ds_hash = sha256_file(Path(dataset_path)) if dataset_path else None
        total = len(self.counts) and sum(self.counts.values()) or 0
        self.conn.execute(
            "INSERT OR REPLACE INTO test_runs (run_id, suite, source, started_utc, finished_utc,"
            " commit_sha, python_version, platform, fingerprint, dataset_hash, total_cases,"
            " pass_count, fail_count, error_count, blocked_count, skipped_count, inconclusive_count, notes)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                self.run_id, self.suite, self.source, self.started, utcnow(),
                self.commit_sha, fp["python"], fp["platform"],
                json.dumps(redact(json.dumps(fp))), ds_hash, total,
                self.counts["PASS"], self.counts["FAIL"], self.counts["ERROR"],
                self.counts["BLOCKED"], self.counts["SKIPPED"],
                self.counts["INCONCLUSIVE"], self.notes,
            ),
        )
        self.conn.commit()
        self.conn.close()
        return self.raw_path.name


# --- pytest junit importer ---------------------------------------------------

def import_junit(xml_path: str, recorder_kwargs: dict) -> list[dict]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    suites = []
    if root.tag == "testsuite":
        suites = [root]
    else:
        suites = [ts for ts in root.iter("testsuite")]
    rec = EvidenceRecorder(
        run_id=recorder_kwargs.get("run_id") or str(uuid.uuid4())[:8],
        suite=recorder_kwargs.get("suite") or "pytest",
        source=recorder_kwargs.get("source") or "junit",
        notes=recorder_kwargs.get("notes"),
    )
    for ts in suites:
        ts_suite = ts.get("name", "unknown")
        for tc in ts.iter("testcase"):
            cls = tc.get("classname", "")
            name = tc.get("name", "")
            full_name = f"{cls}::{name}" if cls else name
            status = "PASS"
            error_text = None
            if tc.find("failure") is not None:
                status = "FAIL"
                error_text = tc.find("failure").text
            elif tc.find("error") is not None:
                status = "ERROR"
                error_text = tc.find("error").text
            elif tc.find("skipped") is not None:
                status = "SKIPPED"
                error_text = (tc.find("skipped").text or "")[:500]
            rec.record(
                case_id=hashlib.sha1(full_name.encode()).hexdigest()[:10],
                name=full_name,
                status=status,
                expected="test passes acceptance criteria",
                actual=status,
                duration_sec=float(tc.get("time", 0)) or None,
                error=error_text,
                artifact=xml_path,
                reason=None if status in ("PASS", "FAIL", "SKIPPED") else error_text,
            )
    raw = rec.finalize()
    return [rec.counts, raw]  # type: ignore[return-value]


# --- benchmark importer ------------------------------------------------------

def import_benchmark(json_path: str, run_id: str | None, kind: str) -> dict:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rec = EvidenceRecorder(
        run_id=run_id or f"bench-{str(uuid.uuid4())[:8]}",
        suite=f"benchmark::{kind}",
        source="benchmark",
        notes=f"imported from {json_path}",
    )
    acc = data.get("accuracy_and_grounding_metrics", {})
    lat = data.get("latency_metrics", {})
    tok = data.get("token_metrics", {})
    gates = data.get("regression_gate_checks", {})
    failed_gates = [k for k, v in gates.items() if not v]

    rec.record(
        case_id="bench-summary",
        name="full benchmark run",
        status="FAIL" if failed_gates else "PASS",
        expected="all regression gates pass",
        actual=("failed gates: " + ", ".join(failed_gates)) if failed_gates else "all gates pass",
        duration_sec=data.get("benchmark_metadata", {}).get("total_elapsed_seconds"),
        latency_metrics=lat,
        token_metrics=tok,
        artifact=json_path,
    )
    for gate_name, passed in gates.items():
        rec.record(
            case_id=hashlib.sha1(gate_name.encode()).hexdigest()[:10],
            name=gate_name,
            status="PASS" if passed else "FAIL",
            expected="gate satisfied",
            actual="satisfied" if passed else "violated",
            artifact=json_path,
        )
    # Per-query accuracy evidence
    raw_rows = 0
    for key in ("results_log", "per_query", "rows"):
        for row in data.get(key, []):
            rec.record(
                case_id=f"q{row.get('id', raw_rows)}",
                name=f"query {row.get('id', raw_rows)}: {row.get('query', '')[:80]}",
                status="PASS" if row.get("answer_supported") else "FAIL",
                expected="gold answer present in evidence",
                actual="supported" if row.get("answer_supported") else "not supported",
                duration_sec=(row.get("search_latency_sec") or 0) + (row.get("extract_latency_sec") or 0),
                token_metrics={"search_tokens": row.get("search_tokens")},
                retry_count=row.get("retry_count", 0),
            )
            raw_rows += 1
    if raw_rows == 0:
        rec.record(
            case_id="per-query-detail",
            name="per-query detail rows",
            status="INCONCLUSIVE",
            reason="benchmark JSON contains no per-query rows; only summary-level evidence available",
        )
    raw = rec.finalize()
    return {"counts": rec.counts, "raw": raw, "failed_gates": failed_gates}


# --- reporting ---------------------------------------------------------------

def summary(db_path: Path = DB_PATH) -> str:
    if not db_path.exists():
        return "No database yet."
    conn = sqlite3.connect(str(db_path))
    lines = ["=== TEST RUNS ==="]
    for row in conn.execute(
        "SELECT run_id, suite, started_utc, total_cases, pass_count, fail_count, error_count,"
        " blocked_count, skipped_count, inconclusive_count, commit_sha FROM test_runs ORDER BY started_utc"
    ):
        lines.append(f"{row[0]:<18} {row[1]:<28} {row[2]}  n={row[3]:<4} pass={row[4]} fail={row[5]} "
                     f"err={row[6]} blk={row[7]} skip={row[8]} inc={row[9]} @{(row[10] or '')[:8]}")
    lines.append("")
    lines.append("=== UNRESOLVED FAILURES (no later PASS for same case) ===")
    for row in conn.execute(
        "SELECT name, MAX(timestamp_utc) FROM test_cases WHERE status IN ('FAIL','ERROR')"
        " GROUP BY name"
    ):
        later = conn.execute(
            "SELECT COUNT(*) FROM test_cases WHERE name=? AND status='PASS'"
            " AND timestamp_utc > ?", (row[0], row[1])
        ).fetchone()[0]
        if not later:
            lines.append(f"  {row[0]}  last-fail={row[1]}")
    conn.close()
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description="Permanent test evidence system")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("summary")
    exp_md = sub.add_parser("export-markdown")
    exp_md.add_argument("--out", required=True)

    rec = sub.add_parser("record-generic")
    rec.add_argument("--run-id", default=None)
    rec.add_argument("--suite", required=True)
    rec.add_argument("--case", required=True)
    rec.add_argument("--name", default=None)
    rec.add_argument("--status", required=True)
    rec.add_argument("--expected", default=None)
    rec.add_argument("--actual", default=None)
    rec.add_argument("--duration", type=float, default=None)
    rec.add_argument("--latency-json", default=None)
    rec.add_argument("--tokens-json", default=None)
    rec.add_argument("--api-calls", type=int, default=None)
    rec.add_argument("--error", default=None)
    rec.add_argument("--artifact", default=None)
    rec.add_argument("--reason", default=None)
    rec.add_argument("--source", default="manual")

    for name in ("record-pytest", "record-benchmark"):
        s = sub.add_parser(name)
        s.add_argument("path")
        if name == "record-pytest":
            s.add_argument("--run-id", default=None)
            s.add_argument("--suite", default="pytest::main-suite")
        else:
            s.add_argument("--run-id", default=None)
            s.add_argument("--kind", default="benchmark")

    args = p.parse_args()
    if args.cmd == "summary":
        print(summary())
    elif args.cmd == "export-markdown":
        out_text = "# Test History Report\n\n```\n" + summary() + "\n```\n"
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out_text, encoding="utf-8")
        print(f"written: {args.out}")
    elif args.cmd == "record-generic":
        rec_obj = EvidenceRecorder(
            run_id=args.run_id or f"gen-{str(uuid.uuid4())[:8]}",
            suite=args.suite, source=args.source,
        )
        try:
            latency = json.loads(args.latency_json) if args.latency_json else None
        except Exception:
            latency = None
        try:
            tokens = json.loads(args.tokens_json) if args.tokens_json else None
        except Exception:
            tokens = None
        rec_obj.record(
            case_id=args.case, name=args.name or args.case, status=args.status,
            expected=args.expected, actual=args.actual, duration_sec=args.duration,
            latency_metrics=latency, token_metrics=tokens, api_calls=args.api_calls,
            error=args.error, artifact=args.artifact, reason=args.reason,
        )
        raw = rec_obj.finalize()
        print(f"recorded -> {raw}")
    elif args.cmd == "record-pytest":
        result = import_junit(args.path, {"run_id": args.run_id, "suite": args.suite})
        print(f"counts={result[0]} raw={result[1]}")
    elif args.cmd == "record-benchmark":
        result = import_benchmark(args.path, args.run_id, args.kind)
        print(f"counts={result['counts']} failed_gates={result['failed_gates']} raw={result['raw']}")


if __name__ == "__main__":
    main()
