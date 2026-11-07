import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "weblens" / "src"))
from weblens.urls import official_source_urls

queries = [
    "In JavaScript, what is the difference between let and const?",
    "Extract the exact license terms of the MIT License text.",
    "How does BM25 scoring calculate term frequency saturation and document length normalization?",
    "Explain SQLite FTS5 porter tokenizer functionality and snippet generation.",
]
for q in queries:
    print(q)
    print(official_source_urls(q))
