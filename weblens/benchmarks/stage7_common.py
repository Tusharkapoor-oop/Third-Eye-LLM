"""Shared helpers for the Stage 7 Tavily comparison campaign."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import math
import os
import platform
import random
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from weblens import __version__
from weblens.tokens import TOKENIZER_NAME, count_json_tokens, count_tokens
from weblens.urls import registrable_domain

ROOT = Path(__file__).resolve().parents[2]
WEBLENS_DIR = ROOT / "weblens"
REPORT_DIR = ROOT / "reports" / "tavily-comparison"
DATA_DIR = REPORT_DIR / "data"
RAW_DIR = REPORT_DIR / "raw"
WORK_DIR = REPORT_DIR / "work"
DATASET_PATH = DATA_DIR / "stage7_dataset.jsonl"
MANIFEST_PATH = DATA_DIR / "stage7_manifest.json"
PREREG_PATH = REPORT_DIR / "PREREGISTRATION.json"

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"
TAVILY_MAP_URL = "https://api.tavily.com/map"
TAVILY_CRAWL_URL = "https://api.tavily.com/crawl"
TAVILY_USAGE_URL = "https://api.tavily.com/usage"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_tavily_key() -> str:
    """Read the key from the environment or weblens/.env without printing it."""
    key = os.environ.get("WEBLENS_TAVILY_API_KEY", "").strip()
    if key:
        return key
    env_path = WEBLENS_DIR / ".env"
    if not env_path.exists():
        raise SystemExit("WEBLENS_TAVILY_API_KEY is not set and weblens/.env is absent")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("WEBLENS_TAVILY_API_KEY="):
            value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                return value
    raise SystemExit("WEBLENS_TAVILY_API_KEY is blank or absent")


def git_state() -> dict[str, Any]:
    def run(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", "-C", str(ROOT), *args],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout.strip()
        except Exception:
            return ""

    return {
        "commit": run("rev-parse", "HEAD"),
        "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
        "porcelain": run("status", "--porcelain"),
    }


def environment() -> dict[str, Any]:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "tokenizer": TOKENIZER_NAME,
        "weblens_version": __version__,
        "git": git_state(),
        "cwd": str(Path.cwd()),
        "timestamp": now_iso(),
    }


def load_dataset() -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in DATASET_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    actual = sha256_file(DATASET_PATH)
    if actual != manifest["dataset_sha256"]:
        raise SystemExit(f"FROZEN DATASET HASH MISMATCH: actual={actual} claimed={manifest['dataset_sha256']}")
    return rows


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            fh.flush()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, math.ceil(p / 100 * len(ordered)) - 1))
    return round(ordered[k], 3)


def mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def bootstrap_mean_ci(values: list[float], *, iterations: int = 10_000, seed: int = 20261028) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "lo": None, "hi": None}
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(iterations):
        means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return {
        "n": n,
        "mean": round(sum(values) / n, 4),
        "lo": round(means[int(0.025 * iterations)], 4),
        "hi": round(means[int(0.975 * iterations) - 1], 4),
    }


def paired_delta_ci(
    left: list[float], right: list[float], *, iterations: int = 10_000, seed: int = 20261028
) -> dict[str, Any]:
    if len(left) != len(right) or not left:
        return {"n": 0, "mean": None, "lo": None, "hi": None}
    diffs = [a - b for a, b in zip(left, right, strict=True)]
    out = bootstrap_mean_ci(diffs, iterations=iterations, seed=seed)
    out["mean_left"] = round(sum(left) / len(left), 4)
    out["mean_right"] = round(sum(right) / len(right), 4)
    return out


def is_relevant(url: str, entry: dict[str, Any]) -> bool:
    for prefix in entry.get("relevant_url_prefixes") or []:
        if url.startswith(prefix):
            return True
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    domain = registrable_domain(host)
    for want in entry.get("relevant_domains") or []:
        want = want.lower()
        if host == want or host.endswith("." + want) or domain == want:
            return True
    return False


def support(entry: dict[str, Any], text: str) -> bool | None:
    terms = [t.lower() for t in entry.get("answer_terms") or []]
    if not terms:
        return None
    low = text.lower()
    if entry.get("support_mode") == "all":
        return all(t in low for t in terms)
    return any(t in low for t in terms)


def citation_errors(items: list[dict[str, Any]], text_key: str = "c") -> list[str]:
    errors: list[str] = []
    for i, item in enumerate(items):
        text = item.get(text_key)
        span = item.get("s")
        url = item.get("u")
        at = item.get("at")
        if not isinstance(text, str) or not text:
            errors.append(f"item {i}: missing text")
            continue
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            errors.append(f"item {i}: bad url")
        if not isinstance(at, str) or not at:
            errors.append(f"item {i}: missing fetched_at")
        if (
            not isinstance(span, list)
            or len(span) != 2
            or not all(isinstance(x, int) for x in span)
            or span[0] < 0
            or span[1] < span[0]
        ):
            errors.append(f"item {i}: bad span")
            continue
        if len(text) != span[1] - span[0]:
            errors.append(f"item {i}: text length {len(text)} != span {span}")
    return errors


def json_tokens(value: Any) -> int:
    return count_json_tokens(value)


def text_tokens(value: str) -> int:
    return count_tokens(value)


def serialized_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("PageFaultCount", wt.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def process_memory() -> dict[str, int] | None:
    if os.name != "nt":
        return None
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    try:
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        handle = kernel32.GetCurrentProcess()
        ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), ctypes.sizeof(counters))
        if not ok:
            return None
    except Exception:
        return None
    return {
        "working_set_bytes": int(counters.WorkingSetSize),
        "peak_working_set_bytes": int(counters.PeakWorkingSetSize),
        "pagefile_bytes": int(counters.PagefileUsage),
        "peak_pagefile_bytes": int(counters.PeakPagefileUsage),
    }


def resource_snapshot() -> dict[str, Any]:
    mem = process_memory()
    return {
        "at": now_iso(),
        "process_cpu_s": round(time.process_time(), 3),
        "memory": mem,
    }


async def tavily_usage(client: httpx.AsyncClient, key: str) -> dict[str, Any]:
    try:
        r = await client.get(
            TAVILY_USAGE_URL,
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            timeout=15,
        )
    except Exception as e:
        return {"status": "error", "error": type(e).__name__}
    if r.status_code != 200:
        return {"status": "http_error", "http_status": r.status_code}
    try:
        data = r.json()
    except ValueError:
        return {"status": "invalid_json", "http_status": r.status_code}
    key_info = data.get("key") or {}
    account = data.get("account") or {}
    return {
        "status": "ok",
        "key": {
            k: key_info.get(k)
            for k in ("usage", "limit", "search_usage", "crawl_usage", "extract_usage", "map_usage", "research_usage")
        },
        "account": {
            k: account.get(k)
            for k in (
                "current_plan",
                "plan_usage",
                "plan_limit",
                "search_usage",
                "crawl_usage",
                "extract_usage",
                "map_usage",
                "research_usage",
                "paygo_usage",
                "paygo_limit",
            )
        },
    }


def fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def fmt_ms(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f} ms"
