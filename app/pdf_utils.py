"""PDF text extraction utilities."""
from __future__ import annotations

from pathlib import Path

import fitz  # pymupdf

PDF_INLINE_PAGE_LIMIT = 5


def extract_pdf_text(path: Path) -> tuple[str, int]:
    """Extract text from a PDF file.

    Returns ``(text, page_count)``.  Each page is separated by a
    ``--- Page N ---`` marker.  Raises ``ValueError`` on encrypted or
    unreadable PDFs.
    """
    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        raise ValueError(f"Cannot open PDF: {exc}") from exc

    if doc.is_encrypted:
        doc.close()
        raise ValueError("PDF is encrypted")

    page_count = doc.page_count
    parts: list[str] = []
    for i, page in enumerate(doc, start=1):
        page_text = page.get_text().strip()
        if page_text:
            parts.append(f"--- Page {i} ---\n{page_text}")

    doc.close()
    return "\n\n".join(parts), page_count
