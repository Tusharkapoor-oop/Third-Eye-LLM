"""Layer 5: Extraction & Reranker Unit Fidelity.

Verifies:
- Code blocks retain 100% of lines and indentation with intact markdown fences.
- HTML tables convert cleanly into valid GitHub-flavored Markdown tables.
- Two-Stage reranker (BM25 + Cross-Encoder) retrieves bottom-of-page target answer
  from a 25,000+ character document as chunk #1 (score > 0.7), discarding intro fluff.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from bs4 import BeautifulSoup

from extractor import (
    TieredExtractor,
    extract_markdown,
    html_table_to_markdown,
    protect_code_and_tables,
)
from schemas import SourceItem


def test_html_table_to_markdown_conversion():
    """Verify that complex HTML tables convert into clean GitHub-flavored Markdown."""
    html_table = (
        "<table>"
        "<thead>"
        "<tr><th>Model</th><th>Latency (ms)</th><th>Accuracy (%)</th></tr>"
        "</thead>"
        "<tbody>"
        "<tr><td>FlashRank-MiniLM</td><td>12.4</td><td>94.5</td></tr>"
        "<tr><td>BM25 Fast</td><td>1.8</td><td>81.2</td></tr>"
        "<tr><td>Hybrid Pipeline</td><td>14.2</td><td>98.1</td></tr>"
        "</tbody>"
        "</table>"
    )
    soup = BeautifulSoup(html_table, "html.parser")
    table_tag = soup.find("table")
    assert table_tag is not None

    md_table = html_table_to_markdown(table_tag)
    lines = [line.strip() for line in md_table.strip().splitlines() if line.strip()]

    assert len(lines) == 5  # header + separator + 3 data rows
    assert lines[0] == "| Model | Latency (ms) | Accuracy (%) |"
    assert "---" in lines[1]
    assert "| FlashRank-MiniLM | 12.4 | 94.5 |" in lines[2]
    assert "| BM25 Fast | 1.8 | 81.2 |" in lines[3]
    assert "| Hybrid Pipeline | 14.2 | 98.1 |" in lines[4]


def test_code_block_preservation_and_indentation():
    """Verify that multi-line code blocks retain lines, language tags, and exact indentation."""
    code_content = (
        "def compute_crc32(payload: bytes) -> int:\n"
        "    crc = 0xFFFFFFFF\n"
        "    for byte in payload:\n"
        "        crc ^= byte\n"
        "        for _ in range(8):\n"
        "            if crc & 1:\n"
        "                crc = (crc >> 1) ^ 0xEDB88320\n"
        "            else:\n"
        "                crc >>= 1\n"
        "    return crc ^ 0xFFFFFFFF"
    )

    html = (
        "<html><body>"
        "<article>"
        "<h1>Python Checksum Algorithm</h1>"
        f'<pre><code class="language-python">{code_content}</code></pre>'
        "</article>"
        "</body></html>"
    )

    protected_html = protect_code_and_tables(html)
    assert "```python" in protected_html
    assert "```" in protected_html
    assert "def compute_crc32" in protected_html
    assert "    return crc ^ 0xFFFFFFFF" in protected_html

    # Verify that Markdown extraction preserves full code block and indentation
    extracted_md = extract_markdown(html)
    assert "```python" in extracted_md
    assert "    crc = 0xFFFFFFFF" in extracted_md
    assert "            if crc & 1:" in extracted_md
    assert "    return crc ^ 0xFFFFFFFF" in extracted_md


@pytest.mark.asyncio
async def test_deep_document_bottom_answer_retrieval():
    """Verify reranker retrieves an answer buried at the bottom of a 25,000+ char document.

    Asserts:
    1. Chunks retrieved correctly from deep in the page past the old 16k character limit.
    2. The bottom answer paragraph is ranked as chunk #1 with score > 0.7.
    3. The 20,000+ chars of intro fluff are discarded from the top rank.
    """
    # Generate 25,000+ characters of generic background text across paragraphs
    fluff_paragraph = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor "
        "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
        "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure "
        "dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. "
        "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt "
        "mollit anim id est laborum.\n\n"
    )
    fluff_body = fluff_paragraph * 60  # ~27,000 characters of fluff

    target_secret = "OMNI_VAULT_RELOAD_9921_CRITICAL_TOKEN"
    target_answer = (
        f"The authoritative cluster recovery token is {target_secret}. "
        "This token authorizes emergency synchronization across distributed edge nodes."
    )

    full_html = (
        "<!DOCTYPE html>"
        "<html><head><title>Distributed Systems Architecture</title></head>"
        "<body>"
        "<article>"
        "<h1>Distributed Systems Architecture Overview</h1>"
        f"{fluff_body}"
        "<h2>Emergency Recovery Protocol</h2>"
        f"<p>{target_answer}</p>"
        "</article>"
        "</body></html>"
    )

    assert len(full_html) > 25000, f"HTML length {len(full_html)} should exceed 25,000 characters"

    target_url = "https://example.com/docs/architecture"

    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get(target_url).mock(
            return_value=httpx.Response(
                200,
                html=full_html,
                headers={"Content-Type": "text/html; charset=utf-8"},
            )
        )

        extractor = TieredExtractor()
        try:
            res = await extractor.extract_url(
                target_url,
                query="What is the authoritative cluster recovery token?",
                chunks_per_source=3,
            )

            assert isinstance(res, SourceItem)
            assert len(res.chunks) >= 1

            top_chunk = res.chunks[0]
            # Chunk #1 must contain the target secret buried at the bottom
            assert target_secret in top_chunk.content, (
                f"Expected target secret in top chunk, but got: {top_chunk.content[:200]}"
            )
            assert top_chunk.score > 0.70, f"Expected top chunk score > 0.70, got {top_chunk.score}"
        finally:
            await extractor.close()
