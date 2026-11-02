"""Heuristic prompt-injection flags for retrieved content.

This is a warning signal, not a classifier and not an authority. It never
changes instructions or permissions; callers decide what to do.
"""

from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "ignore_instructions",
        re.compile(
            r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|everything\s+)?"
            r"(?:previous|prior|above|earlier|system|developer)\s+"
            r"(?:instructions?|prompts?|rules?|messages?)|\bforget\s+everything\s+above\b",
            re.I,
        ),
    ),
    (
        "role_hijack",
        re.compile(
            r"\b(?:you are now|from now on you|act as (?:the|a)\s+(?:system|developer|hacker|admin|root)|"
            r"new (?:system )?instructions?:|system prompt:)",
            re.I,
        ),
    ),
    (
        "exfiltration",
        re.compile(
            r"\b(?:send|post|upload|transmit|forward|reveal|print|leak)\b.{0,80}"
            r"\b(?:api[ _-]?keys?|tokens?|passwords?|secrets?|credentials?|environment variables?|\.env)\b",
            re.I | re.S,
        ),
    ),
    (
        "tool_manipulation",
        re.compile(
            r"\b(?:call|invoke|execute|run)\s+(?:the\s+)?(?:tool|function|command)\b"
            r"|\b(?:rm\s+-rf|powershell\s+-|curl\s+[^|]{0,80}\|\s*(?:sh|bash))",
            re.I,
        ),
    ),
    (
        "concealment",
        re.compile(
            r"\b(?:do not|don't|never)\s+(?:tell|inform|mention|reveal)\b.{0,25}\b(?:user|human|operator)\b",
            re.I,
        ),
    ),
    (
        "encoded_payload",
        re.compile(r"\b(?:base64|rot13)\b.{0,40}\b(?:decode|execute|run)\b", re.I | re.S),
    ),
]

INVISIBLE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")


def scan_injection(text: str) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    for name, pattern in _PATTERNS:
        if pattern.search(text) and name not in found:
            found.append(name)
        if len(found) >= 4:
            break
    if INVISIBLE.search(text):
        found.append("invisible_unicode")
    return found


def has_instruction_smuggling(html: str) -> bool:
    """Check HTML comments for imperative text aimed at a model."""
    for match in re.finditer(r"<!--(.{0,600}?)-->", html, re.S):
        body = match.group(1)
        if re.search(r"\b(?:ignore|instruct|assistant|system|prompt|you must)\b", body, re.I):
            return True
    return False
