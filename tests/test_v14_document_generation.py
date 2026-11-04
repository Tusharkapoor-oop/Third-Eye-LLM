"""Verification of Document Generation and Validation Subsystem (V14 Section 13).

Validates:
1. Generation of DOCX, PDF, PPTX, XLSX, CSV, MD, TXT
2. Structural integrity, magic byte verification, and element count validation
3. Synthesis from ResearchResponse objects
4. Error handling on invalid/empty/corrupted files
"""

from __future__ import annotations

from pathlib import Path
import pytest

from document_generator import DocumentGenerator, DocumentValidationError, validate_document
from schemas import ChunkResult, ResearchResponse, SourceItem


@pytest.fixture
def tmp_doc_dir(tmp_path: Path) -> Path:
    doc_dir = tmp_path / "generated_docs"
    doc_dir.mkdir(parents=True, exist_ok=True)
    return doc_dir


@pytest.fixture
def sample_research_response() -> ResearchResponse:
    return ResearchResponse(
        query="Quantum Computing Roadmap 2026",
        answer="Quantum computing has achieved fault-tolerant logical qubit demonstrations.",
        sources=[
            SourceItem(
                url="https://example.com/quantum1",
                title="Fault-Tolerant Architecture Report",
                score=0.95,
                content="Demonstration of 1000 physical qubits with error suppression.",
                chunks=[
                    ChunkResult(content="Demonstration of 1000 physical qubits.", score=0.95)
                ],
            ),
            SourceItem(
                url="https://example.com/quantum2",
                title="Qubit Coherence Metrics",
                score=0.88,
                content="T1 and T2 coherence times improved by 4x.",
                chunks=[
                    ChunkResult(content="T1 and T2 coherence times improved.", score=0.88)
                ],
            ),
        ],
        sub_queries=["quantum roadmap", "fault-tolerant qubits"],
        evidence_summary="Synthesized across 2 authoritative sources.",
        response_time=1.25,
    )


def test_generate_and_validate_docx(tmp_doc_dir: Path):
    out = tmp_doc_dir / "report.docx"
    sections = [
        {"heading": "Executive Summary", "body": "Overview of results."},
        {"heading": "Findings", "body": "Detailed findings and data."},
    ]
    path = DocumentGenerator.generate_docx("Quantum Roadmap", sections, out)
    assert path.exists()
    assert path.stat().st_size > 0

    meta = validate_document(path, "docx")
    assert meta["valid"] is True
    assert meta["format"] == "docx"
    assert meta["elements_count"] >= 3


def test_generate_and_validate_pdf(tmp_doc_dir: Path):
    out = tmp_doc_dir / "report.pdf"
    sections = [
        {"heading": "Section 1", "body": "First paragraph.\n\nSecond paragraph."},
        {"heading": "Section 2", "body": "Summary & <escaped> metrics."},
    ]
    path = DocumentGenerator.generate_pdf("PDF Executive Brief", sections, out)
    assert path.exists()
    assert path.stat().st_size > 0

    meta = validate_document(path, "pdf")
    assert meta["valid"] is True
    assert meta["format"] == "pdf"
    assert meta["elements_count"] >= 1


def test_generate_and_validate_pptx(tmp_doc_dir: Path):
    out = tmp_doc_dir / "brief.pptx"
    slides = [
        {"title": "Key Objectives", "bullets": ["Objective 1", "Objective 2"]},
        {"title": "Timeline", "bullets": ["Q1: Alpha", "Q2: Production"]},
    ]
    path = DocumentGenerator.generate_pptx("Quarterly Strategy", slides, out)
    assert path.exists()

    meta = validate_document(path, "pptx")
    assert meta["valid"] is True
    assert meta["format"] == "pptx"
    assert meta["elements_count"] >= 3  # Title slide + 2 content slides


def test_generate_and_validate_xlsx(tmp_doc_dir: Path):
    out = tmp_doc_dir / "data.xlsx"
    headers = ["Metric", "Value", "Status"]
    rows = [["Latency", "2.1ms", "Pass"], ["Accuracy", "98.4%", "Pass"]]
    path = DocumentGenerator.generate_xlsx("MetricsSheet", headers, rows, out)
    assert path.exists()

    meta = validate_document(path, "xlsx")
    assert meta["valid"] is True
    assert meta["format"] == "xlsx"
    assert meta["elements_count"] >= 1


def test_generate_and_validate_csv(tmp_doc_dir: Path):
    out = tmp_doc_dir / "data.csv"
    headers = ["ID", "Name", "Score"]
    rows = [["1", "Alice", 99], ["2", "Bob", 95]]
    path = DocumentGenerator.generate_csv(headers, rows, out)
    assert path.exists()

    meta = validate_document(path, "csv")
    assert meta["valid"] is True
    assert meta["format"] == "csv"
    assert meta["elements_count"] == 3


def test_generate_from_research_response(tmp_doc_dir: Path, sample_research_response: ResearchResponse):
    formats = ["docx", "pdf", "pptx", "xlsx", "csv", "md", "txt"]
    for fmt in formats:
        out = tmp_doc_dir / f"research_output.{fmt}"
        path = DocumentGenerator.from_research_response(sample_research_response, fmt, out)
        assert path.exists()
        meta = validate_document(path, fmt)
        assert meta["valid"] is True


def test_validate_document_error_handling(tmp_doc_dir: Path):
    # Non-existent file
    with pytest.raises(DocumentValidationError, match="does not exist"):
        validate_document(tmp_doc_dir / "non_existent.pdf", "pdf")

    # Empty file
    empty_file = tmp_doc_dir / "empty.pdf"
    empty_file.write_bytes(b"")
    with pytest.raises(DocumentValidationError, match="empty"):
        validate_document(empty_file, "pdf")

    # Corrupt PDF magic bytes
    fake_pdf = tmp_doc_dir / "fake.pdf"
    fake_pdf.write_bytes(b"NOT A REAL PDF FILE")
    with pytest.raises(DocumentValidationError, match="Invalid PDF magic bytes"):
        validate_document(fake_pdf, "pdf")

    # Corrupt DOCX magic bytes
    fake_docx = tmp_doc_dir / "fake.docx"
    fake_docx.write_bytes(b"NOT A ZIP CONTAINER")
    with pytest.raises(DocumentValidationError, match="Invalid magic bytes for DOCX"):
        validate_document(fake_docx, "docx")
