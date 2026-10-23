
import pytest

from src.engine.extract.chunker import DocumentChunker
from src.engine.extract.extractor import DocumentExtractor
from src.engine.extract.passage_scorer import BM25PassageScorer


def test_chunker_exact_span_preservation():
    sample_text = (
        "# Python Overview\n\n"
        "Python is a high-level, general-purpose programming language. "
        "Its design philosophy emphasizes code readability with the use of significant indentation.\n\n"
        "## Memory Management\n\n"
        "Python dynamically types and uses garbage collection. It supports multiple programming paradigms."
    )
    chunker = DocumentChunker(target_tokens=50, overlap_tokens=10)
    chunks = chunker.chunk_document(sample_text)
    assert len(chunks) > 0

    # Verify exact character offset guarantee (R2: zero fake accuracy)
    for c in chunks:
        extracted_slice = sample_text[c.char_start:c.char_end]
        assert extracted_slice == c.text, f"Mismatch at [{c.char_start}:{c.char_end}]: '{extracted_slice}' vs '{c.text}'"

def test_bm25_passage_scoring():
    sample_text = (
        "Bananas are a great source of potassium and dietary fiber.\n\n"
        "Python is an interpreted, high-level, dynamically typed language.\n\n"
        "Apples contain vitamin C and various antioxidants."
    )
    chunker = DocumentChunker(target_tokens=30, overlap_tokens=5)
    chunks = chunker.chunk_document(sample_text)
    scorer = BM25PassageScorer()
    ranked = scorer.score_and_rank_passages(chunks, query="programming language Python dynamic", max_tokens=100)

    assert len(ranked) > 0
    # The top ranked passage should be the Python one
    assert "Python" in ranked[0].text

@pytest.mark.asyncio
async def test_extractor_live():
    extractor = DocumentExtractor()
    doc = await extractor.extract_url("https://www.python.org/about/", query="open source software mission", max_tokens=600)
    assert doc.status == "success"
    assert len(doc.passages) > 0
    assert doc.tokens_used <= 600
    assert doc.fetch_timestamp != ""

@pytest.mark.asyncio
async def test_extractor_blocked_ssrf():
    extractor = DocumentExtractor()
    doc = await extractor.extract_url("http://127.0.0.1:9090/admin")
    assert doc.status == "blocked"
    assert "Security block" in doc.metadata.get("error", "")
