"""Real tokenizer accounting and budget enforcement.

cl100k_base is used as the reference tokenizer because it is stable, local and
widely used. Other models tokenize differently; every reported number states
which tokenizer produced it.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

TOKENIZER_NAME = "cl100k_base"


@lru_cache(maxsize=1)
def _enc():
    import tiktoken

    return tiktoken.get_encoding(TOKENIZER_NAME)


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_enc().encode(text, disallowed_special=()))


def count_json_tokens(obj: Any) -> int:
    return count_tokens(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))


def truncate_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    if max_tokens <= 0:
        return "", bool(text)
    enc = _enc()
    ids = enc.encode(text, disallowed_special=())
    if len(ids) <= max_tokens:
        return text, False
    out = enc.decode(ids[:max_tokens])
    # Avoid leaving a dangling surrogate/partial token artifact.
    out = out.rstrip()
    return out, True


def compact_json(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
