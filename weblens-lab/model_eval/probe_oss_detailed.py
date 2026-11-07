"""Empirical probe for GPT-OSS and small OSS models on NVIDIA NIM API."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
import httpx
from dotenv import dotenv_values

ENV_PATH = Path(".env")
env = dotenv_values(ENV_PATH)

MISTRAL_KEY = env.get("Mistral_Large_4_api_key_by_nividia", "").strip()
GPT_KEY = env.get("gpt-oss-20b_api_key_by_nividia", "").strip()

BASE_URL = "https://integrate.api.nvidia.com/v1"

CANDIDATE_MODELS = [
    # Primary target models mentioned in missions
    "openai/gpt-oss-20b",
    "openai/gpt-oss-12b",
    "gpt-oss-12b",
    "nv-mistralai/mistral-nemo-12b-instruct",
    "mistralai/mistral-large-4-1t-a52b",
    # Other small OSS models around ~7B-12B in the catalog
    "google/gemma-3-12b-it",
    "meta/llama-guard-4-12b",
    "meta/llama-3.2-11b-vision-instruct",
    "nvidia/mistral-nemo-minitron-8b-8k-instruct",
    "mistralai/mistral-7b-instruct-v0.3",
    "deepseek-ai/deepseek-v4.1-flash",
    "ibm/granite-3.0-8b-instruct",
]

PROMPT = "Reply with exactly one JSON object: {\"status\":\"ok\",\"model_verified\":true}"


async def test_endpoint(client: httpx.AsyncClient, model: str, key_label: str, key: str) -> dict:
    url = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0.0,
        "max_tokens": 150,
    }

    t0 = time.perf_counter()
    try:
        resp = await client.post(url, headers=headers, json=payload, timeout=30.0)
        dur_ms = round((time.perf_counter() - t0) * 1000, 1)

        body = {}
        try:
            body = resp.json()
        except Exception:
            pass

        content = ""
        reasoning = None
        usage = {}
        if isinstance(body, dict):
            choices = body.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                content = msg.get("content") or ""
                reasoning = msg.get("reasoning_content")
            usage = body.get("usage") or {}

        return {
            "model": model,
            "key_label": key_label,
            "http_status": resp.status_code,
            "ok": resp.status_code == 200,
            "latency_ms": dur_ms,
            "usage": usage,
            "content": content[:200],
            "reasoning": reasoning[:200] if reasoning else None,
            "error_body": "" if resp.status_code == 200 else resp.text[:400],
        }
    except Exception as exc:
        dur_ms = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "model": model,
            "key_label": key_label,
            "http_status": None,
            "ok": False,
            "latency_ms": dur_ms,
            "usage": {},
            "content": "",
            "reasoning": None,
            "error_body": f"{type(exc).__name__}: {str(exc)[:400]}",
        }


async def main():
    results = []
    keys = []
    if MISTRAL_KEY:
        keys.append(("Mistral_Key", MISTRAL_KEY))
    if GPT_KEY:
        keys.append(("GPT_OSS_Key", GPT_KEY))

    print(f"Loaded {len(keys)} API keys from .env")

    async with httpx.AsyncClient() as client:
        for key_label, key in keys:
            print(f"\n--- Testing with {key_label} ---")
            for model in CANDIDATE_MODELS:
                res = await test_endpoint(client, model, key_label, key)
                results.append(res)
                print(f"[{res['key_label']}] {res['model']}: HTTP {res['http_status']} in {res['latency_ms']}ms - OK={res['ok']}")
                if not res["ok"]:
                    print(f"    Error: {res['error_body'][:150]}")
                else:
                    print(f"    Content: {res['content'][:100]}")

    out_file = Path("weblens-lab/model_eval/probe_oss_detailed_results.json")
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote full probe results to {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
