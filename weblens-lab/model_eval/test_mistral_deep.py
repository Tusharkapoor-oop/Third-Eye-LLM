"""Deep inspection and empirical benchmark of mistralai/mistral-large-4-1t-a52b."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from config import CONFIG


async def test_single_call():
    raw = CONFIG.nvidia_mistral_large_key or CONFIG.nvidia_gpt_oss_20b_key
    key = raw.strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()

    prompt = (
        "Extract the following entities as a valid JSON object matching this schema:\n"
        '{"company_name": str, "ceo": str, "revenue_billions": float, "founded_year": int, "headquarters": str}\n\n'
        "Text: Acme Corp was established in 1984 in Zurich, Switzerland. Under CEO Jane Doe, "
        "the firm reported annual revenue of 14.5 billion dollars in 2023."
    )

    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{CONFIG.nvidia_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "mistralai/mistral-large-4-1t-a52b",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 1000,
            },
        )
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    data = resp.json()
    choice = data["choices"][0]
    msg = choice["message"]
    usage = data.get("usage", {})

    print(json.dumps({
        "status_code": resp.status_code,
        "latency_ms": latency_ms,
        "message_keys": list(msg.keys()),
        "role": msg.get("role"),
        "content": msg.get("content"),
        "has_reasoning_content": "reasoning_content" in msg,
        "reasoning_content": msg.get("reasoning_content"),
        "usage": usage,
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(test_single_call())
