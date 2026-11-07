"""Diagnose Task 1 and token behavior on Mistral Large 4."""

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from config import CONFIG


async def inspect_calls():
    raw = (CONFIG.nvidia_mistral_large_key or CONFIG.nvidia_gpt_oss_20b_key).strip()
    key = raw[7:].strip() if raw.lower().startswith("bearer ") else raw

    prompt = (
        "Extract all organizations, people, and monetary figures into this exact JSON schema:\n"
        "{\n"
        '  "organizations": [{"name": str, "industry": str}],\n'
        '  "people": [{"name": str, "role": str, "organization": str}],\n'
        '  "financials": [{"amount_billions": float, "currency": str, "metric": str, "year": int}]\n'
        "}\n\n"
        "Context: In Q4 2023, Microsoft Corporation in the tech sector, headed by CEO Satya Nadella, "
        "reported cloud revenue of 25.9 billion USD. Meanwhile, Pfizer Inc in pharmaceuticals under CEO Albert Bourla "
        "posted total annual revenue of 58.5 billion USD for 2023."
    )

    # Let's test with max_tokens=2500 and timeout=120.0
    print("Testing with max_tokens=2500...")
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{CONFIG.nvidia_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "mistralai/mistral-large-4-1t-a52b",
                "messages": [
                    {"role": "system", "content": "You are a concise structured extraction engine. Keep chain of thought minimal and output the exact JSON object."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 2500,
            },
        )
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    data = resp.json()
    choice = data["choices"][0]
    finish_reason = choice.get("finish_reason")
    msg = choice["message"]
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    usage = data.get("usage", {})

    print(json.dumps({
        "status_code": resp.status_code,
        "finish_reason": finish_reason,
        "latency_ms": latency_ms,
        "content_len": len(content),
        "content": content,
        "reasoning_len": len(reasoning),
        "reasoning_snippet": reasoning[:300] + " ... " + reasoning[-300:],
        "usage": usage,
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(inspect_calls())
