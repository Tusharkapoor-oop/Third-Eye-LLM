"""Probe real model access for the three requested model options.

Reads keys from the existing config module (which loads .env). Never prints
key values. Writes one JSON record per model to stdout.

Run:
    python weblens-lab/model_eval/probe_model_access.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from config import CONFIG  # noqa: E402

MODELS = [
    ("mistralai/mistral-large-4-1t-a52b", "Mistral Large 4"),
    ("openai/gpt-oss-20b", "GPT-OSS 20B"),
    ("nv-mistralai/mistral-nemo-12b-instruct", "Mistral NeMo 12B"),
]

PROMPT = (
    "Reply with exactly one JSON object and nothing else: "
    '{"city":"Paris","country":"France","confidence":0.9}'
)


async def probe(model: str, key: str, timeout: float = 60.0) -> dict:
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{CONFIG.nvidia_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": PROMPT}],
                    "temperature": 0.0,
                    "max_tokens": 800,
                },
            )
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        content = ""
        reasoning_content = ""
        usage = {}
        if isinstance(body, dict):
            choices = body.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                content = msg.get("content") or ""
                reasoning_content = msg.get("reasoning_content") or ""
            usage = body.get("usage") or {}
        reasoning_tokens = (
            (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
            if isinstance(usage, dict)
            else None
        )
        return {
            "model": model,
            "http_status": resp.status_code,
            "ok": resp.status_code == 200 and bool(content),
            "latency_ms": latency_ms,
            "usage": usage,
            "reasoning_tokens": reasoning_tokens,
            "content_prefix": content[:200],
            "reasoning_content_prefix": reasoning_content[:200],
            "error_prefix": "" if resp.status_code == 200 else resp.text[:300],
        }
    except Exception as exc:
        return {
            "model": model,
            "http_status": None,
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "usage": {},
            "reasoning_tokens": None,
            "content_prefix": "",
            "reasoning_content_prefix": "",
            "error_prefix": f"{type(exc).__name__}: {str(exc)[:300]}",
        }


async def main() -> int:
    raw = CONFIG.nvidia_mistral_large_key or CONFIG.nvidia_gpt_oss_20b_key
    key = raw.strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    print(json.dumps({"base_url": CONFIG.nvidia_base_url, "key_present": bool(key)}, indent=2))
    if not key:
        for model, _label in MODELS:
            print(json.dumps({"model": model, "ok": False, "error_prefix": "no NVIDIA key in config"}, indent=2))
        return 1

    models_to_probe = MODELS
    if len(sys.argv) > 1:
        filter_str = sys.argv[1].lower()
        matched = [(m, label) for m, label in MODELS if filter_str in m.lower() or filter_str in label.lower()]
        if matched:
            models_to_probe = matched

    for model, _label in models_to_probe:
        print(json.dumps(await probe(model, key), indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
