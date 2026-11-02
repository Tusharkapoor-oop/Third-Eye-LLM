from __future__ import annotations

import json
from pathlib import Path

from provenance import result_provenance, sha256_json
from validate_dataset import validate_dataset


ROOT = Path(__file__).resolve().parents[2]


def test_provenance_has_required_fields_and_stable_hash() -> None:
    payload = {"status": "ok", "res": [{"u": "https://example.com"}]}
    record = result_provenance(
        system="local_weblens",
        backend_provider="ddg",
        model=None,
        cache_state="cold",
        experiment_id="test-exp",
        dataset_version="test-v1",
        success=True,
        latency_ms=12.5,
        response=payload,
        status="PASS",
    )
    assert set(("system", "backend_provider", "model", "cache_state", "experiment_id", "dataset_version", "timestamp", "success", "latency_ms", "response_hash")).issubset(record)
    assert record["response_hash"] == sha256_json(payload)
    assert "tvly-" not in json.dumps(record)


def test_current_seed_is_explicitly_partial_against_target() -> None:
    result = validate_dataset(
        ROOT / "weblens-lab" / "datasets" / "eval_benchmark_suite.json",
        ROOT / "weblens-lab" / "datasets" / "adversarial_suite.json",
        "v9.0.0-seed",
    )
    assert result["status"] == "PARTIAL"
    assert result["achieved"]["unique_queries"] == 30
    assert result["coverage"]["schema_status"] == "PASS"
