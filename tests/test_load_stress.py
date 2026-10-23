"""
Load & Concurrency Stress Testing Suite
Verifies stability under concurrent load, burst traffic, and sustained requests.
"""
from __future__ import annotations

import asyncio
import time
import psutil
import pytest

from src.engine.search.aggregator import SearchAggregator
from src.engine.extract.extractor import DocumentExtractor


QUERIES = [
    "capital of France",
    "speed of light",
    "Python asyncio gather",
    "PEP 703 free threading",
    "HTTP/3 QUIC protocol",
    "largest mammal on Earth",
    "chemical formula for water",
    "fourth planet from Sun",
    "creator of Linux kernel",
    "author of Neuromancer",
]

URLS = [
    "https://www.python.org/about/",
    "https://en.wikipedia.org/wiki/Python_(programming_language)",
]