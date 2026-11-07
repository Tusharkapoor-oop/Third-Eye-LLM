import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "weblens" / "src"))
from weblens.search.router import clean_query
from weblens.urls import official_source_urls

for q in [
    "In JavaScript, what is the difference between let and const?",
    "Extract the exact license terms of the MIT License text.",
    "What is the canonical sitemap and robots.txt specification format according to sitemaps.org?",
    "How does BM25 scoring calculate term frequency saturation and document length normalization?",
]:
    c = clean_query(q)
    print(repr(q), "->", repr(c), official_source_urls(c))
