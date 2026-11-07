"""Empirical Evaluation and Benchmarking Suite for NVIDIA NIM Mistral Large 4.

Model: mistralai/mistral-large-4-1t-a52b
Auditor: Agent 17 - NVIDIA Mistral Large 4 Specialist
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from config import CONFIG

MODEL_ID = "mistralai/mistral-large-4-1t-a52b"


def extract_json_payload(raw_content: str) -> tuple[dict | list | None, str | None]:
    """Parse JSON payload from raw model response, handling optional markdown code blocks."""
    cleaned = raw_content.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if match:
        candidate = match.group(1).strip()
    else:
        candidate = cleaned

    try:
        parsed = json.loads(candidate)
        return parsed, None
    except Exception as e:
        return None, str(e)


async def run_query(
    client: httpx.AsyncClient,
    key: str,
    prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 1200,
) -> dict[str, Any]:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    start = time.perf_counter()
    resp = await client.post(
        f"{CONFIG.nvidia_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": MODEL_ID,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
    )
    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    status_code = resp.status_code
    if status_code != 200:
        return {
            "ok": False,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "error": resp.text[:500],
        }

    body = resp.json()
    choice = body.get("choices", [{}])[0]
    msg = choice.get("message", {})
    content = msg.get("content") or ""
    reasoning_content = msg.get("reasoning_content") or ""
    usage = body.get("usage", {})
    completion_details = usage.get("completion_tokens_details", {})
    reasoning_tokens = completion_details.get("reasoning_tokens", 0)

    parsed_json, parse_error = extract_json_payload(content)

    return {
        "ok": True,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "content": content,
        "reasoning_content": reasoning_content,
        "parsed_json": parsed_json,
        "parse_error": parse_error,
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "reasoning_tokens": reasoning_tokens,
            "content_tokens": usage.get("completion_tokens", 0) - reasoning_tokens,
            "total_tokens": usage.get("total_tokens", 0),
        },
    }


async def main():
    raw = CONFIG.nvidia_mistral_large_key or CONFIG.nvidia_gpt_oss_20b_key
    key = raw.strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()

    if not key:
        print(json.dumps({"error": "No NVIDIA API key configured"}, indent=2))
        return

    print("=== STARTING AGENT 17 MISTRAL LARGE 4 BENCHMARK ===")
    async with httpx.AsyncClient(timeout=120.0) as client:
        # 1. Warm Latency Benchmark: 5 sequential identical small requests
        print("\n--- Phase 1: Sequential Warm Latency Measurement (5 runs) ---")
        warmup_prompt = 'Output valid JSON: {"status":"healthy","ping_id":1}'
        latency_runs = []
        for i in range(1, 6):
            res = await run_query(client, key, f"{warmup_prompt} (run {i})")
            latency_runs.append({
                "run": i,
                "latency_ms": res["latency_ms"],
                "ok": res["ok"],
                "prompt_tokens": res.get("usage", {}).get("prompt_tokens"),
                "completion_tokens": res.get("usage", {}).get("completion_tokens"),
                "reasoning_tokens": res.get("usage", {}).get("reasoning_tokens"),
                "content_tokens": res.get("usage", {}).get("content_tokens"),
            })
            print(f"Run {i}: Latency = {res['latency_ms']} ms | Reasoning tokens: {res.get('usage', {}).get('reasoning_tokens')} | Content tokens: {res.get('usage', {}).get('content_tokens')}")
            await asyncio.sleep(1.0)

        # 2. Structured JSON Extraction Adherence Tasks
        print("\n--- Phase 2: Structured JSON Extraction Evaluation ---")
        tasks = [
            {
                "task_id": "TASK-01-ENTITIES",
                "description": "Structured Entity Extraction",
                "system": "You are a precise data extraction engine. You MUST output valid JSON conforming exactly to the requested schema.",
                "prompt": (
                    "Extract all organizations, people, and monetary figures into this exact JSON schema:\n"
                    "{\n"
                    '  "organizations": [{"name": str, "industry": str}],\n'
                    '  "people": [{"name": str, "role": str, "organization": str}],\n'
                    '  "financials": [{"amount_billions": float, "currency": str, "metric": str, "year": int}]\n'
                    "}\n\n"
                    "Context: In Q4 2023, Microsoft Corporation in the tech sector, headed by CEO Satya Nadella, "
                    "reported cloud revenue of 25.9 billion USD. Meanwhile, Pfizer Inc in pharmaceuticals under CEO Albert Bourla "
                    "posted total annual revenue of 58.5 billion USD for 2023."
                ),
                "expected_keys": ["organizations", "people", "financials"],
            },
            {
                "task_id": "TASK-02-SEARCH-RERANK",
                "description": "Web Search Query & Ranked Result Schema",
                "system": "You are an AI search pipeline reranking component. Emit strict JSON matching the schema.",
                "prompt": (
                    "Format the search evaluation into this exact JSON schema:\n"
                    "{\n"
                    '  "query": str,\n'
                    '  "total_hits": int,\n'
                    '  "ranked_results": [\n'
                    '    {"rank": int, "url": str, "title": str, "relevance_score": float, "snippet_summary": str}\n'
                    "  ]\n"
                    "}\n\n"
                    "Data: Query 'CRISPR base editing therapeutic trials'. Hit count 2. First result rank 1: url 'https://nature.com/articles/crispr123', "
                    "title 'Clinical advances in base editing', relevance 0.96, summary 'Phase 1 trials demonstrate in vivo efficacy'. "
                    "Second result rank 2: url 'https://nih.gov/news/crispr-trial', title 'NIH launches gene editing study', relevance 0.88, "
                    "summary 'Safety study for sickle cell disease patient cohort'."
                ),
                "expected_keys": ["query", "total_hits", "ranked_results"],
            },
            {
                "task_id": "TASK-03-FACT-VERIFICATION",
                "description": "Deep Research Claim Verification & Fact Checking",
                "system": "You are an epistemological audit agent for automated research. Output strict JSON.",
                "prompt": (
                    "Verify the following claim against evidence into this JSON schema:\n"
                    "{\n"
                    '  "claim": str,\n'
                    '  "verdict": "SUPPORTED" | "REFUTED" | "INCONCLUSIVE",\n'
                    '  "confidence": float,\n'
                    '  "evidence_points": [{"source": str, "finding": str, "credibility": float}],\n'
                    '  "caveats": [str]\n'
                    "}\n\n"
                    "Claim: 'Sodium-ion batteries have reached commercial passenger EV mass production in 2023.'\n"
                    "Evidence: In December 2023, JAC Motors and Yiwei launched the first mass-produced EV powered by sodium-ion cylindrical cells in Anhui, China. "
                    "However, energy density remains at 120-140 Wh/kg, limiting range to subcompact city vehicles."
                ),
                "expected_keys": ["claim", "verdict", "confidence", "evidence_points", "caveats"],
            },
            {
                "task_id": "TASK-04-SECURITY-INCIDENT",
                "description": "Cyber Threat & SSRF Incident Audit Struct",
                "system": "You are a cyber security auditor evaluating MCP network security. Respond strictly in valid JSON.",
                "prompt": (
                    "Extract the security incident report into this JSON schema:\n"
                    "{\n"
                    '  "incident_id": str,\n'
                    '  "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",\n'
                    '  "threat_vector": str,\n'
                    '  "target_asset": str,\n'
                    '  "indicators_of_compromise": [str],\n'
                    '  "remediation_actions": [str],\n'
                    '  "mitigated": bool\n'
                    "}\n\n"
                    "Log report: INC-88219 detected CRITICAL SSRF attempt against internal cloud metadata 169.254.169.254 via tool fetch_url. "
                    "IOCs identified: request payload 'http://169.254.169.254/latest/meta-data/', source IP 198.51.100.42. "
                    "Actions taken: Blocked by SSRF filter, IP rate-limited, firewall rule applied. Mitigated: True."
                ),
                "expected_keys": ["incident_id", "severity", "threat_vector", "target_asset", "indicators_of_compromise", "remediation_actions", "mitigated"],
            },
        ]

        task_results = []
        for task in tasks:
            print(f"\nRunning {task['task_id']} ({task['description']})...")
            res = await run_query(
                client=client,
                key=key,
                prompt=task["prompt"],
                system_prompt=task["system"],
                temperature=0.0,
                max_tokens=1500,
            )

            # Evaluate schema adherence
            parsed = res.get("parsed_json")
            parse_ok = parsed is not None
            keys_present = []
            keys_missing = []
            schema_adherence = False
            if parse_ok and isinstance(parsed, dict):
                for k in task["expected_keys"]:
                    if k in parsed:
                        keys_present.append(k)
                    else:
                        keys_missing.append(k)
                schema_adherence = (len(keys_missing) == 0)

            task_metric = {
                "task_id": task["task_id"],
                "description": task["description"],
                "status_code": res["status_code"],
                "latency_ms": res["latency_ms"],
                "json_parsed": parse_ok,
                "parse_error": res.get("parse_error"),
                "schema_adherence": schema_adherence,
                "keys_present": keys_present,
                "keys_missing": keys_missing,
                "has_reasoning_content": bool(res.get("reasoning_content")),
                "reasoning_token_count": res.get("usage", {}).get("reasoning_tokens", 0),
                "content_token_count": res.get("usage", {}).get("content_tokens", 0),
                "prompt_token_count": res.get("usage", {}).get("prompt_tokens", 0),
                "total_token_count": res.get("usage", {}).get("total_tokens", 0),
                "reasoning_sample": res.get("reasoning_content", "")[:250],
                "parsed_data": parsed,
            }
            task_results.append(task_metric)
            print(f"Result for {task['task_id']}: Parsed={parse_ok} | Adherence={schema_adherence} | Latency={res['latency_ms']} ms | Reasoning={task_metric['reasoning_token_count']} toks")
            await asyncio.sleep(1.0)

        # Output Summary JSON
        output_file = ROOT / "weblens-lab" / "model_eval" / "mistral_large_benchmark_results.json"
        full_summary = {
            "model": MODEL_ID,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "warm_latency_runs": latency_runs,
            "schema_extraction_tasks": task_results,
        }
        output_file.write_text(json.dumps(full_summary, indent=2), encoding="utf-8")
        print(f"\nSaved benchmark results to {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
