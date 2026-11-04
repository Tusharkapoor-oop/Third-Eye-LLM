"""Deterministic Document Generation and Validation Subsystem.

Produces structurally validated document artifacts from research synthesis and tabular data:
- DOCX: Microsoft Word documents (.docx) via python-docx
- PDF: Formatted report documents (.pdf) via reportlab
- PPTX: Multi-slide presentations (.pptx) via python-pptx
- XLSX: Structured spreadsheets (.xlsx) via openpyxl
- CSV: Delimited data tables (.csv) via stdlib csv
- Markdown: Structured Markdown reports (.md)
- TXT: Plain text documents (.txt)

Every generated file is strictly validated for:
1. File existence and non-zero byte size
2. Magic bytes and archive signatures
3. Native engine parseability and non-empty structural elements
"""

from __future__ import annotations

import csv
import zipfile
from pathlib import Path
from typing import Any

import docx
import openpyxl
import pptx
import pypdf
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from schemas import ResearchResponse


class DocumentValidationError(Exception):
    """Raised when generated document fails structural or magic-byte verification."""


def validate_document(file_path: str | Path, expected_format: str) -> dict[str, Any]:
    """Validate file integrity, magic bytes, and native structural parseability.

    Args:
        file_path: Path to target document file.
        expected_format: Lowercase format tag: 'docx', 'pdf', 'pptx', 'xlsx', 'csv', 'md', 'txt'.

    Returns:
        dict with verification metadata: valid, format, size_bytes, structural_elements.

    Raises:
        DocumentValidationError: If file does not exist, is empty, has invalid header, or cannot be parsed.
    """
    path = Path(file_path)
    if not path.is_file():
        raise DocumentValidationError(f"File does not exist: {path}")

    size = path.stat().st_size
    if size == 0:
        raise DocumentValidationError(f"File is empty (0 bytes): {path}")

    fmt = expected_format.lower().lstrip(".")

    with open(path, "rb") as f:
        header = f.read(16)

    # 1. Archive-based OpenXML formats: DOCX, PPTX, XLSX
    if fmt in ("docx", "pptx", "xlsx"):
        if not header.startswith(b"PK\x03\x04"):
            raise DocumentValidationError(
                f"Invalid magic bytes for {fmt.upper()}: expected PK\\x03\\x04, got {header[:4]!r}"
            )
        try:
            with zipfile.ZipFile(path, "r") as z:
                namelist = z.namelist()
                if "[Content_Types].xml" not in namelist:
                    raise DocumentValidationError(f"Missing [Content_Types].xml in {fmt.upper()} container")

                if fmt == "docx":
                    if "word/document.xml" not in namelist:
                        raise DocumentValidationError("Missing word/document.xml in DOCX container")
                    doc = docx.Document(str(path))
                    elements_count = len(doc.paragraphs)
                    if elements_count == 0:
                        raise DocumentValidationError("DOCX document has zero paragraphs")
                    return {
                        "valid": True,
                        "format": "docx",
                        "size_bytes": size,
                        "elements_count": elements_count,
                    }

                elif fmt == "pptx":
                    if "ppt/presentation.xml" not in namelist:
                        raise DocumentValidationError("Missing ppt/presentation.xml in PPTX container")
                    prs = pptx.Presentation(str(path))
                    slides_count = len(prs.slides)
                    if slides_count == 0:
                        raise DocumentValidationError("PPTX presentation has zero slides")
                    return {
                        "valid": True,
                        "format": "pptx",
                        "size_bytes": size,
                        "elements_count": slides_count,
                    }

                elif fmt == "xlsx":
                    if "xl/workbook.xml" not in namelist:
                        raise DocumentValidationError("Missing xl/workbook.xml in XLSX container")
                    wb = openpyxl.load_workbook(str(path), data_only=True)
                    sheets_count = len(wb.sheetnames)
                    if sheets_count == 0:
                        raise DocumentValidationError("XLSX workbook has zero sheets")
                    return {
                        "valid": True,
                        "format": "xlsx",
                        "size_bytes": size,
                        "elements_count": sheets_count,
                    }
        except Exception as e:
            if isinstance(e, DocumentValidationError):
                raise
            raise DocumentValidationError(f"Failed to inspect OpenXML {fmt.upper()}: {e}") from e

    # 2. PDF Format
    elif fmt == "pdf":
        if not header.startswith(b"%PDF-"):
            raise DocumentValidationError(
                f"Invalid PDF magic bytes: expected %PDF-, got {header[:5]!r}"
            )
        try:
            reader = pypdf.PdfReader(str(path))
            pages_count = len(reader.pages)
            if pages_count == 0:
                raise DocumentValidationError("PDF document has 0 pages")
            return {
                "valid": True,
                "format": "pdf",
                "size_bytes": size,
                "elements_count": pages_count,
            }
        except Exception as e:
            if isinstance(e, DocumentValidationError):
                raise
            raise DocumentValidationError(f"Failed to parse PDF document: {e}") from e

    # 3. CSV Format
    elif fmt == "csv":
        try:
            with open(path, encoding="utf-8") as f:
                reader = list(csv.reader(f))
                if len(reader) == 0:
                    raise DocumentValidationError("CSV file has zero rows")
                return {
                    "valid": True,
                    "format": "csv",
                    "size_bytes": size,
                    "elements_count": len(reader),
                }
        except UnicodeDecodeError as e:
            raise DocumentValidationError(f"CSV file is not valid UTF-8: {e}") from e

    # 4. Markdown and TXT formats
    elif fmt in ("md", "markdown", "txt"):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
                if not text.strip():
                    raise DocumentValidationError(f"{fmt.upper()} file content is empty")
                return {
                    "valid": True,
                    "format": fmt,
                    "size_bytes": size,
                    "elements_count": len(text.splitlines()),
                }
        except UnicodeDecodeError as e:
            raise DocumentValidationError(f"{fmt.upper()} file is not valid UTF-8: {e}") from e

    raise DocumentValidationError(f"Unsupported document format: {expected_format}")


class DocumentGenerator:
    """Enterprise document generator producing valid DOCX, PDF, PPTX, XLSX, CSV, and MD artifacts."""

    @staticmethod
    def generate_docx(
        title: str,
        sections: list[dict[str, str]],
        output_path: str | Path,
    ) -> Path:
        """Create a Microsoft Word (.docx) document with styled headings and sections."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        doc = docx.Document()
        doc.add_heading(title, level=0)

        for sec in sections:
            heading = sec.get("heading")
            if heading:
                doc.add_heading(heading, level=1)
            body = sec.get("body")
            if body:
                doc.add_paragraph(body)

        doc.save(str(path))
        validate_document(path, "docx")
        return path

    @staticmethod
    def generate_pdf(
        title: str,
        sections: list[dict[str, str]],
        output_path: str | Path,
    ) -> Path:
        """Create a PDF report using ReportLab with clean typography and layout."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(str(path), pagesize=letter)
        styles = getSampleStyleSheet()

        story: list[Any] = []
        # Title
        story.append(Paragraph(title, styles["Title"]))
        story.append(Spacer(1, 14))

        for sec in sections:
            heading = sec.get("heading")
            if heading:
                story.append(Paragraph(heading, styles["Heading2"]))
                story.append(Spacer(1, 6))
            body = sec.get("body")
            if body:
                # Wrap multi-paragraph text
                paragraphs = body.split("\n\n")
                for p in paragraphs:
                    if p.strip():
                        # Escape XML characters for ReportLab Paragraph
                        escaped = p.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        story.append(Paragraph(escaped, styles["Normal"]))
                        story.append(Spacer(1, 6))

        doc.build(story)
        validate_document(path, "pdf")
        return path

    @staticmethod
    def generate_pptx(
        title: str,
        slides_data: list[dict[str, Any]],
        output_path: str | Path,
        subtitle: str = "WebLens Intelligence Brief",
    ) -> Path:
        """Create a PowerPoint (.pptx) presentation with title and content slides."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        prs = pptx.Presentation()

        # Slide 0: Title Slide
        title_layout = prs.slide_layouts[0]
        title_slide = prs.slides.add_slide(title_layout)
        title_slide.shapes.title.text = title
        if len(title_slide.placeholders) > 1:
            title_slide.placeholders[1].text = subtitle

        # Content Slides
        bullet_layout = prs.slide_layouts[1]
        for sdata in slides_data:
            slide = prs.slides.add_slide(bullet_layout)
            slide.shapes.title.text = sdata.get("title", "Key Findings")
            bullets = sdata.get("bullets", [])
            if bullets and len(slide.placeholders) > 1:
                tf = slide.placeholders[1].text_frame
                tf.text = str(bullets[0])
                for b in bullets[1:]:
                    p = tf.add_paragraph()
                    p.text = str(b)

        prs.save(str(path))
        validate_document(path, "pptx")
        return path

    @staticmethod
    def generate_xlsx(
        sheet_name: str,
        headers: list[str],
        rows: list[list[Any]],
        output_path: str | Path,
    ) -> Path:
        """Create an Excel spreadsheet (.xlsx) with styled header row."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = (sheet_name or "Data")[:31]

        if headers:
            ws.append(headers)
        for r in rows:
            ws.append(r)

        wb.save(str(path))
        validate_document(path, "xlsx")
        return path

    @staticmethod
    def generate_csv(
        headers: list[str],
        rows: list[list[Any]],
        output_path: str | Path,
    ) -> Path:
        """Create a comma-separated values file (.csv)."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if headers:
                writer.writerow(headers)
            for r in rows:
                writer.writerow(r)

        validate_document(path, "csv")
        return path

    @staticmethod
    def generate_markdown(
        title: str,
        content: str,
        output_path: str | Path,
    ) -> Path:
        """Create a Markdown document (.md)."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        text = f"# {title}\n\n{content}\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

        validate_document(path, "md")
        return path

    @classmethod
    def from_research_response(
        cls,
        response: ResearchResponse,
        format_type: str,
        output_path: str | Path,
    ) -> Path:
        """Compile a complete ResearchResponse into any supported document format."""
        fmt = format_type.lower().lstrip(".")
        path = Path(output_path)

        title = f"Deep Research: {response.query}"
        sections = [
            {"heading": "Executive Summary", "body": response.answer},
            {"heading": "Evidence Summary", "body": response.evidence_summary},
        ]
        if response.sub_queries:
            sub_q_body = "\n".join(f"- {sq}" for sq in response.sub_queries)
            sections.append({"heading": "Research Sub-queries", "body": sub_q_body})

        if fmt == "docx":
            return cls.generate_docx(title, sections, path)

        elif fmt == "pdf":
            return cls.generate_pdf(title, sections, path)

        elif fmt == "pptx":
            slides = [
                {
                    "title": "Executive Summary",
                    "bullets": [response.answer[:250] + "..." if len(response.answer) > 250 else response.answer],
                },
                {
                    "title": "Evidence Sources",
                    "bullets": [f"{s.title} ({s.url})" for s in response.sources[:5]],
                },
            ]
            return cls.generate_pptx(title, slides, path)

        elif fmt == "xlsx":
            headers = ["Title", "URL", "Score", "Passages Count"]
            rows = [
                [s.title, s.url, round(s.score, 3), len(s.chunks)]
                for s in response.sources
            ]
            return cls.generate_xlsx("Research Evidence", headers, rows, path)

        elif fmt == "csv":
            headers = ["Title", "URL", "Score", "Passages Count"]
            rows = [
                [s.title, s.url, round(s.score, 3), len(s.chunks)]
                for s in response.sources
            ]
            return cls.generate_csv(headers, rows, path)

        elif fmt in ("md", "markdown"):
            content = f"{response.answer}\n\n## Evidence Summary\n{response.evidence_summary}\n"
            return cls.generate_markdown(title, content, path)

        elif fmt == "txt":
            path.parent.mkdir(parents=True, exist_ok=True)
            text = f"{title}\n\n{response.answer}\n\n{response.evidence_summary}\n"
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            validate_document(path, "txt")
            return path

        else:
            raise ValueError(f"Unsupported format: {format_type}")
