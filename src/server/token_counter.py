"""
Schema Token Counter & Reporter
Measures exact token footprints for MCP tools using real model tokenizers.
"""

from __future__ import annotations

import json
from typing import Any

import tiktoken

from src.server.tools import TOOL_DEFINITIONS


def measure_tool_schema_tokens() -> dict[str, Any]:
    tokenizer_o200k = tiktoken.get_encoding("o200k_base")
    tokenizer_cl100k = tiktoken.get_encoding("cl100k_base")

    report: dict[str, Any] = {
        "per_tool": {},
        "total_o200k": 0,
        "total_cl100k": 0
    }

    total_o200k = 0
    total_cl100k = 0

    for tool in TOOL_DEFINITIONS:
        serialized = json.dumps(tool, separators=(",", ":"))
        t_o200k = len(tokenizer_o200k.encode(serialized))
        t_cl100k = len(tokenizer_cl100k.encode(serialized))

        report["per_tool"][tool["name"]] = {
            "o200k_tokens": t_o200k,
            "cl100k_tokens": t_cl100k,
            "char_length": len(serialized)
        }
        total_o200k += t_o200k
        total_cl100k += t_cl100k

    report["total_o200k"] = total_o200k
    report["total_cl100k"] = total_cl100k
    return report

if __name__ == "__main__":
    rep = measure_tool_schema_tokens()
    print("=== MCP Tool Schema Token Measurements ===")
    for tool_name, metrics in rep["per_tool"].items():
        print(f"Tool '{tool_name}': {metrics['o200k_tokens']} tokens (o200k) | {metrics['cl100k_tokens']} tokens (cl100k)")
    print("------------------------------------------")
    print(f"TOTAL SCHEMA OVERHEAD: {rep['total_o200k']} tokens (o200k) | {rep['total_cl100k']} tokens (cl100k)")
