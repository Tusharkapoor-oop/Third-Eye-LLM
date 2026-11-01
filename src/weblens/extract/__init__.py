from __future__ import annotations

from .html import ExtractedDoc, extract_html, extract_pdf, extract_plain
from .passages import Passage, select_passages
from .service import ExtractionService, ExtractOutcome

__all__ = [
    "ExtractOutcome",
    "ExtractedDoc",
    "ExtractionService",
    "Passage",
    "extract_html",
    "extract_pdf",
    "extract_plain",
    "select_passages",
]
