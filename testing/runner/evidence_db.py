"""
Persistent Test Evidence Database.
SQLite-backed storage for all test results, with append-only JSONL backup.
Every test execution creates an immutable record that survives process termination.
"""

import hashlib
import json
import os
import platform
import sqlite3
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any


class TestStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    INCONCLUSIVE = "INCONCLUSIVE"
    CANCELLED = "CANCELLED"
    NOT_RUN = "NOT_RUN"


@dataclass
class TestRecord:
    """Immutable record of a single test execution attempt."""
    test_run_id: str
    test_case_id: str
    suite_name: str
    test_name: str
    timestamp_utc: str
    git_commit: str
    environment_fingerprint: str
    browser_version: str = ""
    model_version: str = ""
    provider: str = ""
    config_id: str = ""
    test_input: str = ""
    expected_outcome: str = ""
    actual_outcome: str = ""
    status: str = TestStatus.NOT_RUN
    duration_seconds: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    token_count: int = 0
    token_method: str = ""
    api_requests: int = 0
    api_calls: int = 0
    cost_usd: float = 0.0
    cpu_percent: float = 0.0
    ram_mb: float = 0.0
    assertion_failures: str = ""
    error_message: str = ""
    artifact_path: str = ""
    evidence_checksum: str = ""
    retry_count: int = 0
    is_comparable: bool = True
    skip_reason: str = ""
    experiment_id: str = ""
    defect_id: str = ""
    extra_data: str = ""  # JSON string for additional data

    def to_dict(self) -> dict:
        return asdict(self)


DB_DIR = Path(__file__).resolve().parent.parent.parent / "test-results" / "database"
DB_PATH = DB_DIR / "test_evidence.db"
JSONL_PATH = DB_DIR / "test_evidence.jsonl"
BACKUP_PATH = DB_DIR / "test_evidence_backup.db"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS test_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_run_id TEXT NOT NULL,
    test_case_id TEXT NOT NULL,
    suite_name TEXT NOT NULL,
    test_name TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    git_commit TEXT NOT NULL,
    environment_fingerprint TEXT NOT NULL,
    browser_version TEXT DEFAULT '',
    model_version TEXT DEFAULT '',
    provider TEXT DEFAULT '',
    config_id TEXT DEFAULT '',
    test_input TEXT DEFAULT '',
    expected_outcome TEXT DEFAULT '',
    actual_outcome TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'NOT_RUN',
    duration_seconds REAL DEFAULT 0.0,
    latency_p50_ms REAL DEFAULT 0.0,
    latency_p95_ms REAL DEFAULT 0.0,
    latency_p99_ms REAL DEFAULT 0.0,
    token_count INTEGER DEFAULT 0,
    token_method TEXT DEFAULT '',
    api_requests INTEGER DEFAULT 0,
    api_calls INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    cpu_percent REAL DEFAULT 0.0,
    ram_mb REAL DEFAULT 0.0,
    assertion_failures TEXT DEFAULT '',
    error_message TEXT DEFAULT '',
    artifact_path TEXT DEFAULT '',
    evidence_checksum TEXT DEFAULT '',
    retry_count INTEGER DEFAULT 0,
    is_comparable BOOLEAN DEFAULT 1,
    skip_reason TEXT DEFAULT '',
    experiment_id TEXT DEFAULT '',
    defect_id TEXT DEFAULT '',
    extra_data TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_test_run ON test_records(test_run_id);
CREATE INDEX IF NOT EXISTS idx_test_case ON test_records(test_case_id);
CREATE INDEX IF NOT EXISTS idx_suite ON test_records(suite_name);
CREATE INDEX IF NOT EXISTS idx_status ON test_records(status);
CREATE INDEX IF NOT EXISTS idx_timestamp ON test_records(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_experiment ON test_records(experiment_id);
"""

# Pre-built analytical queries
QUERIES = {
    "current_revision_passes": """
        SELECT * FROM test_records WHERE git_commit = ? AND status = 'PASS'
        ORDER BY timestamp_utc DESC
    """,
    "previous_revision_failures": """
        SELECT * FROM test_records WHERE git_commit = ? AND status = 'FAIL'
        ORDER BY timestamp_utc DESC
    """,
    "regressions_after_change": """
        SELECT curr.suite_name, curr.test_name, curr.status as current_status,
               prev.status as previous_status
        FROM test_records curr
        JOIN test_records prev ON curr.test_case_id = prev.test_case_id
        WHERE curr.git_commit = ? AND prev.git_commit = ?
          AND curr.status = 'FAIL' AND prev.status = 'PASS'
    """,
    "never_executed": """
        SELECT DISTINCT test_case_id, test_name FROM test_records
        WHERE status = 'NOT_RUN'
        EXCEPT
        SELECT DISTINCT test_case_id, test_name FROM test_records
        WHERE status NOT IN ('NOT_RUN', 'SKIPPED')
    """,
    "unresolved_failures": """
        SELECT test_case_id, test_name, MAX(timestamp_utc) as last_attempt,
               COUNT(*) as failure_count
        FROM test_records
        WHERE status = 'FAIL'
          AND test_case_id NOT IN (
            SELECT test_case_id FROM test_records WHERE status = 'PASS'
            AND timestamp_utc > (SELECT MAX(timestamp_utc) FROM test_records r2
                                 WHERE r2.test_case_id = test_records.test_case_id
                                 AND r2.status = 'FAIL')
          )
        GROUP BY test_case_id, test_name
    """,
    "flaky_tests": """
        SELECT test_case_id, test_name,
               SUM(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END) as passes,
               SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) as fails,
               COUNT(*) as total_runs
        FROM test_records
        GROUP BY test_case_id, test_name
        HAVING passes > 0 AND fails > 0
    """,
    "p95_latency_change": """
        SELECT curr.suite_name, curr.test_name,
               curr.latency_p95_ms as current_p95,
               prev.latency_p95_ms as previous_p95,
               ROUND((curr.latency_p95_ms - prev.latency_p95_ms) / NULLIF(prev.latency_p95_ms, 0) * 100, 2) as pct_change
        FROM test_records curr
        JOIN test_records prev ON curr.test_case_id = prev.test_case_id
        WHERE curr.git_commit = ? AND prev.git_commit = ?
          AND curr.latency_p95_ms > 0 AND prev.latency_p95_ms > 0
    """,
    "token_change": """
        SELECT curr.suite_name, curr.test_name,
               curr.token_count as current_tokens,
               prev.token_count as previous_tokens,
               ROUND((curr.token_count - prev.token_count) * 1.0 / NULLIF(prev.token_count, 0) * 100, 2) as pct_change
        FROM test_records curr
        JOIN test_records prev ON curr.test_case_id = prev.test_case_id
        WHERE curr.git_commit = ? AND prev.git_commit = ?
          AND curr.token_count > 0 AND prev.token_count > 0
    """,
    "optimization_impact": """
        SELECT experiment_id,
               COUNT(*) as test_count,
               SUM(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END) as passes,
               AVG(duration_seconds) as avg_duration,
               AVG(token_count) as avg_tokens,
               AVG(latency_p50_ms) as avg_p50
        FROM test_records
        WHERE experiment_id = ?
        GROUP BY experiment_id
    """,
    "quality_damage_check": """
        SELECT experiment_id, suite_name, test_name, status, token_count,
               latency_p50_ms, error_message
        FROM test_records
        WHERE experiment_id = ? AND status IN ('FAIL', 'ERROR')
    """,
    "summary_by_status": """
        SELECT status, COUNT(*) as count FROM test_records
        WHERE test_run_id = ?
        GROUP BY status
    """,
    "full_run_details": """
        SELECT * FROM test_records WHERE test_run_id = ?
        ORDER BY timestamp_utc
    """,
}


def get_environment_fingerprint() -> str:
    """Generate a stable fingerprint of the current environment."""
    parts = [
        platform.system(),
        platform.release(),
        platform.machine(),
        sys.version,
        platform.node(),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def get_git_commit() -> str:
    """Get current git commit hash."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=str(Path(__file__).resolve().parent.parent.parent)
        )
        return result.stdout.strip()[:12] if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


class TestEvidenceDB:
    """Persistent test evidence storage with SQLite + JSONL backup."""

    def __init__(self, db_path: Path | None = None, jsonl_path: Path | None = None):
        self.db_path = db_path or DB_PATH
        self.jsonl_path = jsonl_path or JSONL_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._env_fingerprint = get_environment_fingerprint()
        self._git_commit = get_git_commit()

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(CREATE_TABLE_SQL)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def generate_run_id(self) -> str:
        """Generate a unique test run ID."""
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        return f"run-{ts}-{uuid.uuid4().hex[:8]}"

    def generate_case_id(self, suite: str, name: str) -> str:
        """Generate a stable test case ID from suite and name."""
        return hashlib.sha256(f"{suite}::{name}".encode()).hexdigest()[:16]

    def record_test(self, record: TestRecord) -> int:
        """Insert a test record into both SQLite and JSONL. Returns the row ID."""
        d = record.to_dict()

        # SQLite insert
        columns = list(d.keys())
        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)
        values = [d[c] for c in columns]

        with self._connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO test_records ({col_names}) VALUES ({placeholders})",
                values
            )
            row_id = cursor.lastrowid

        # Append-only JSONL backup
        d["_row_id"] = row_id
        d["_recorded_at"] = datetime.now(UTC).isoformat()
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(d, separators=(",", ":")) + "\n")

        return row_id

    def create_record(
        self,
        run_id: str,
        suite_name: str,
        test_name: str,
        **kwargs
    ) -> TestRecord:
        """Create a TestRecord with auto-filled environment data."""
        return TestRecord(
            test_run_id=run_id,
            test_case_id=self.generate_case_id(suite_name, test_name),
            suite_name=suite_name,
            test_name=test_name,
            timestamp_utc=datetime.now(UTC).isoformat(),
            git_commit=self._git_commit,
            environment_fingerprint=self._env_fingerprint,
            **kwargs
        )

    def query(self, query_name: str, params: tuple = ()) -> list[dict]:
        """Execute a named analytical query."""
        sql = QUERIES.get(query_name)
        if not sql:
            raise ValueError(f"Unknown query: {query_name}")
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def raw_query(self, sql: str, params: tuple = ()) -> list[dict]:
        """Execute a raw SQL query."""
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def get_run_summary(self, run_id: str) -> dict:
        """Get a summary of a test run."""
        statuses = self.query("summary_by_status", (run_id,))
        total = sum(s["count"] for s in statuses)
        return {
            "run_id": run_id,
            "total_tests": total,
            "status_breakdown": {s["status"]: s["count"] for s in statuses}
        }

    def get_total_records(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM test_records").fetchone()
            return row["cnt"]

    def get_all_runs(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT test_run_id, MIN(timestamp_utc) as started,
                       MAX(timestamp_utc) as ended, COUNT(*) as test_count,
                       SUM(CASE WHEN status='PASS' THEN 1 ELSE 0 END) as passes,
                       SUM(CASE WHEN status='FAIL' THEN 1 ELSE 0 END) as fails,
                       SUM(CASE WHEN status='ERROR' THEN 1 ELSE 0 END) as errors
                FROM test_records
                GROUP BY test_run_id
                ORDER BY started DESC
            """).fetchall()
            return [dict(r) for r in rows]

    def backup(self):
        """Create a backup of the database."""
        import shutil
        if self.db_path.exists():
            shutil.copy2(self.db_path, BACKUP_PATH)

    def verify_integrity(self) -> bool:
        """Check database integrity."""
        with self._connect() as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            return result[0] == "ok"
