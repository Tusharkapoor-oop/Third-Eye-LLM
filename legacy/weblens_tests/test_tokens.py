from __future__ import annotations

from weblens.tokens import (
    TOKENIZER_NAME,
    compact_json,
    count_json_tokens,
    count_tokens,
    truncate_tokens,
)


def test_tokenizer_is_named_and_counts():
    assert TOKENIZER_NAME == "cl100k_base"
    assert count_tokens("hello world") > 0
    assert count_tokens("") == 0


def test_truncate_tokens_is_exact_prefix_and_bounded():
    text = "alpha beta gamma delta epsilon zeta eta theta"
    out, cut = truncate_tokens(text, 4)
    assert cut is True
    assert text.startswith(out)
    assert count_tokens(out) <= 4


def test_truncate_tokens_noop_when_fits():
    out, cut = truncate_tokens("short", 20)
    assert out == "short"
    assert cut is False


def test_truncate_tokens_zero():
    assert truncate_tokens("abc", 0) == ("", True)


def test_compact_json_and_count():
    obj = {"a": 1, "b": ["x", "y"]}
    assert compact_json(obj) == '{"a":1,"b":["x","y"]}'
    assert count_json_tokens(obj) == count_tokens(compact_json(obj))


def test_unicode_is_preserved():
    assert compact_json({"q": "café"}) == '{"q":"café"}'
