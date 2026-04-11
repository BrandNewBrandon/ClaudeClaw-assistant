from __future__ import annotations

import fitz  # pymupdf
from pathlib import Path

from app.pdf_utils import extract_pdf_text, PDF_INLINE_PAGE_LIMIT


def _create_test_pdf(tmp_path: Path, pages: list[str]) -> Path:
    """Helper: create a PDF with given page texts."""
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    path = tmp_path / "test.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_extract_single_page(tmp_path: Path) -> None:
    pdf_path = _create_test_pdf(tmp_path, ["Hello world"])
    text, page_count = extract_pdf_text(pdf_path)
    assert page_count == 1
    assert "Hello world" in text


def test_extract_multi_page(tmp_path: Path) -> None:
    pdf_path = _create_test_pdf(tmp_path, ["Page one", "Page two", "Page three"])
    text, page_count = extract_pdf_text(pdf_path)
    assert page_count == 3
    assert "Page one" in text
    assert "Page two" in text
    assert "Page three" in text
    assert "--- Page 1 ---" in text
    assert "--- Page 2 ---" in text
    assert "--- Page 3 ---" in text


def test_extract_empty_pdf(tmp_path: Path) -> None:
    """A PDF with pages but no text should return empty string."""
    doc = fitz.open()
    doc.new_page()
    path = tmp_path / "empty.pdf"
    doc.save(str(path))
    doc.close()
    text, page_count = extract_pdf_text(path)
    assert page_count == 1
    assert text.strip() == ""


def test_inline_page_limit_constant() -> None:
    assert PDF_INLINE_PAGE_LIMIT == 5
