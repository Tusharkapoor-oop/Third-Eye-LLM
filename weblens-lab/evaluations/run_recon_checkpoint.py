"""Run a low-cost, three-system identity and provenance checkpoint.

This is intentionally a pilot, not a superiority claim.  It executes one
curated query per system, records transport identity, and emits explicit
BLOCKED/UNVERIFIED statuses when a dependency is unavailable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "weblens-lab"))
sys.path.insert(0, str(ROOT / "weblens-lab" / "evaluations"))
sys.path.insert(0, str(ROOT / "weblens" / "src"))

from adapters.mcp_adapter import MCPWebLensAdapter
from adapters.tavily_adapter.adapter import TavilyAdapter
from provenance import result_provenance, redact_error, sha256_file, utc_now, write_json


DEFAULT_ENDPOINT = "https://weblens-16131012091.us-central1.run.app/mcp"
DATASET = ROOT / "weblens-lab" / "datasets" / "eval_benchmark_suite.json"


def _result_summary(response: Any) -> dict[str, Any]:
    return {
        "status": response.status,
        "result_count": len(response.results),
        "latency_ms": round(response.latency_ms, 3),
        "tokens_returned": response.tokens_returned,
        "credits_used": response.credits_used,
        "error": redact_error(response.error),
        "urls": [item.url for item in response.results[:5]],
    }


async def _deployment_transport_observation(endpoint: str) -> dict[str, Any]:
    base = endpoint.removesuffix("/mcp")
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
        root_response = await client.get(base + "/")
        # This is a single unauthenticated capability probe, not a load test.
        list_response = await client.post(
            endpoint,
            json={"jsonrpc": "2.0", "id": "recon-tools-list", "method": "tools/list", "params": {}},
            headers={"accept": "application/json, text/event-stream"},
        )
    return {
        "endpoint": endpoint,
        "root": {
            "status_code": root_response.status_code,
            "https": base.startswith("https://"),
            "server_header": root_response.headers.get("server"),
            "content_type": root_response.headers.get("content-type"),
        },
        "unauthenticated_tools_list": {
            "status_code": list_response.status_code,
            "accepted": list_response.status_code == 200,
            "content_type": list_response.headers.get("content-type"),
        },
    }


async def run(query_id: str | None, endpoint: str, output: Path) -> dict[str, Any]:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    item = next((entry for entry in dataset if entry["id"] == query_id), dataset[0]) if query_id else dataset[0]
    experiment_id = "recon-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    dataset_version = "v9.0.0-seed"
    report: dict[str, Any] = {
        "experiment_id": experiment_id,
        "dataset_version": dataset_version,
        "started_at": utc_now(),
        "query": {"id": item["id"], "category": item.get("category"), "sha256": sha256_file(DATASET)},
        "systems": {},
        "transport_observation": None,
    }

    local = MCPWebLensAdapter(system="local_weblens", repo_root=ROOT)
    deployed = MCPWebLensAdapter(system="deployed_weblens", endpoint=endpoint, repo_root=ROOT)
    for system, adapter in (("local_weblens", local), ("deployed_weblens", deployed)):
        try:
            identity = await adapter.open()
            response = await adapter.search(item["query"], max_results=5)
            summary = _result_summary(response)
            report["systems"][system] = {
                "identity": identity,
                "result": summary,
                "provenance": result_provenance(
                    system=system,
                    backend_provider=str(adapter.last_call_metadata.get("backend_provider")) if adapter.last_call_metadata.get("backend_provider") else None,
                    model=adapter.last_call_metadata.get("model"),
                    cache_state=adapter.last_call_metadata.get("cache_state", "unknown"),
                    experiment_id=experiment_id, dataset_version=dataset_version,
                    success=response.status == "ok", latency_ms=response.latency_ms,
                    response=summary, status="PASS" if response.status == "ok" else "PARTIAL",
                    error=response.error,
                ),
            }
        except Exception as exc:
            report["systems"][system] = {
                "provenance": result_provenance(
                    system=system, backend_provider=None, model=None, cache_state="unknown",
                    experiment_id=experiment_id, dataset_version=dataset_version, success=False,
                    latency_ms=0.0, response={}, status="BLOCKED", error=redact_error(exc),
                )
            }
        finally:
            try:
                await adapter.close()
            except Exception as exc:
                report["systems"].setdefault(system, {}).setdefault("cleanup", {})["error"] = redact_error(exc)

    try:
        report["transport_observation"] = await _deployment_transport_observation(endpoint)
    except Exception as exc:
        report["transport_observation"] = {"status": "BLOCKED", "error": redact_error(exc)}

    try:
        tavily = TavilyAdapter(client=httpx.AsyncClient(timeout=30.0))
    except Exception as exc:
        report["systems"]["tavily_direct"] = {
            "provenance": result_provenance(
                system="tavily_direct", backend_provider="tavily", model=None, cache_state="unknown",
                experiment_id=experiment_id, dataset_version=dataset_version, success=False,
                latency_ms=0.0, response={}, status="BLOCKED", error=redact_error(exc),
            )
        }
    else:
        try:
            response = await tavily.search(item["query"], max_results=5)
            summary = _result_summary(response)
            report["systems"]["tavily_direct"] = {
                "identity": {"endpoint": TavilyAdapter.BASE_URL, "operation": "POST /search", "direct": True},
                "result": summary,
                "provenance": result_provenance(
                    system="tavily_direct", backend_provider="tavily", model=None, cache_state="unknown",
                    experiment_id=experiment_id, dataset_version=dataset_version,
                    success=response.status == "ok", latency_ms=response.latency_ms,
                    response=summary, status="PASS" if response.status == "ok" else "PARTIAL",
                    error=response.error,
                ),
            }
        finally:
            if tavily._client is not None and not tavily._client.is_closed:
                await tavily._client.aclose()
    report["finished_at"] = utc_now()
    write_json(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-id")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--output", type=Path, default=ROOT / "evidence" / "raw_results" / "recon_checkpoint.json")
    args = parser.parse_args()
    report = asyncio.run(run(args.query_id, args.endpoint, args.output))
    print(json.dumps({"experiment_id": report["experiment_id"], "output": str(args.output), "systems": {k: v["provenance"]["status"] for k, v in report["systems"].items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
