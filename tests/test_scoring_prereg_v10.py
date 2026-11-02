# Regression expectations from PREREG-V10-001 (scoring correction).
# Items that were structurally incapable of scoring support under the old
# token-length>3 rule must now score correctly; benign adjacent text must not.

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "weblens-lab" / "evaluations"))

from run_three_system_benchmark import evaluate_precision  # noqa: E402


def _res(url: str = "https://wikipedia.org/Water", title: str = "Water", content: str = "Water molecule") -> SimpleNamespace:
    return SimpleNamespace(url=url, title=title, content=content)


def test_short_token_ground_truths_now_supported():
    cases = [
        ("H2O", "Water - Wikipedia", "The chemical formula for water is H2O."),
        ("405", "HTTP 405 - Method Not Allowed | MDN", "Status code 405 means Method Not Allowed."),
        ("Au", "Gold - Wikipedia", "The chemical symbol for gold is Au."),
        ("PEP 703", "PEP 703 - Making CPython free-threaded", "PEP 703 introduces optional free-threading."),
        ("@>", "PostgreSQL JSONB operators", "The @> operator tests JSONB containment."),
    ]
    for gt, title, content in cases:
        item = {"ground_truth_answer": gt, "acceptable_sources": []}
        result = SimpleNamespace(title=title, content=content, url="https://example.org/doc")
        _, supported = evaluate_precision([result], item)
        assert supported, f"ground truth {gt!r} must be countable"


def test_short_token_does_not_match_benign_substring():
    # "Au" must NOT match inside "auth"/"audio"/"augment" (word-boundary required).
    item = {"ground_truth_answer": "Au", "acceptable_sources": []}
    result = SimpleNamespace(title="Authorization guide", content="audio augment authority oauth", url="https://example.org")
    perc, supported = evaluate_precision([result], item)
    assert supported is False


def test_dynamic_not_measured_item_uses_acceptable_sources():
    item = {
        "ground_truth_answer": "NOT MEASURED - depends on current officeholder",
        "acceptable_sources": ["gov.uk", "wikipedia.org"],
    }
    hit = SimpleNamespace(title="UK government", content="prime minister", url="https://www.gov.uk/pm")
    miss = SimpleNamespace(title="random blog", content="prime minister", url="https://randomblog.example")
    _, supported_hit = evaluate_precision([hit], item)
    _, supported_miss = evaluate_precision([miss], item)
    assert supported_hit is True
    assert supported_miss is False


def test_long_token_substring_semantics_unchanged():
    item = {"ground_truth_answer": "unwrap_or_else", "acceptable_sources": []}
    result = SimpleNamespace(title="Result in Rust", content="Use unwrap_or_else to compute a default value.", url="https://doc.rust-lang.org/result")
    _, supported = evaluate_precision([result], item)
    assert supported is True
