"""
PDF text extraction service using PyMuPDF (fitz).

Responsibilities:
- Validate that the uploaded bytes are a real, readable PDF.
- Reject encrypted PDFs that cannot be opened without a password.
- Extract text page by page, preserving exact page numbers.
- Report pages that are genuinely textless (e.g. pure scans) without fabricating OCR output.
- Return a structured list of PageContent objects and a summary.

Security:
- Never executes content from PDFs.
- All file bytes are treated as untrusted data.
- Does not follow embedded links, run scripts, or honour embedded instructions.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PageContent:
    """Extracted text for one PDF page (1-indexed)."""
    page_number: int        # 1-indexed, matches the physical PDF page number
    text: str               # raw extracted text; empty string if page has no text layer
    char_count: int = 0

    def __post_init__(self) -> None:
        self.char_count = len(self.text)


@dataclass
class ExtractionResult:
    """Full result from a PDF extraction attempt."""
    success: bool
    pages: List[PageContent] = field(default_factory=list)
    page_count: int = 0
    total_chars: int = 0
    textless_pages: List[int] = field(default_factory=list)   # pages with no extractable text
    error: Optional[str] = None
    is_encrypted: bool = False
    is_empty: bool = False   # True when every page has no text layer (likely a scanned PDF)


def extract_pdf_pages(pdf_bytes: bytes, filename: str = "<upload>") -> ExtractionResult:
    """
    Extract text from PDF bytes, page by page.

    Returns an ExtractionResult. Sets success=False for:
    - Files that are not valid PDFs.
    - Encrypted/password-protected PDFs.
    - Zero-page PDFs.
    - Any other fitz error.

    OCR is NOT performed. Pages without a text layer are reported as textless;
    a PDF is flagged as is_empty when *all* pages are textless.
    """
    try:
        import fitz  # PyMuPDF — imported here to keep service importable even without fitz
    except ImportError:
        return ExtractionResult(
            success=False,
            error="PyMuPDF (fitz) is not installed. Run: pip install PyMuPDF"
        )

    # ── 1. Validate magic bytes ────────────────────────────────────────────────
    if not pdf_bytes or len(pdf_bytes) < 5:
        return ExtractionResult(success=False, error="File is empty or too small to be a PDF.")

    if not pdf_bytes[:4] == b"%PDF":
        return ExtractionResult(success=False, error="File does not appear to be a valid PDF (wrong magic bytes).")

    # ── 2. Open with fitz ─────────────────────────────────────────────────────
    try:
        doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    except fitz.FileDataError as exc:
        return ExtractionResult(success=False, error=f"Corrupted or unreadable PDF: {exc}")
    except Exception as exc:
        return ExtractionResult(success=False, error=f"Failed to open PDF: {exc}")

    # ── 3. Encryption check ───────────────────────────────────────────────────
    if doc.is_encrypted:
        doc.close()
        return ExtractionResult(
            success=False,
            is_encrypted=True,
            error="PDF is encrypted or password-protected. Cannot extract text."
        )

    # ── 4. Page count check ───────────────────────────────────────────────────
    page_count = doc.page_count
    if page_count == 0:
        doc.close()
        return ExtractionResult(success=False, error="PDF contains no pages.")

    # ── 5. Extract page-by-page ───────────────────────────────────────────────
    pages: List[PageContent] = []
    textless: List[int] = []
    total_chars = 0

    for page_idx in range(page_count):
        page_num = page_idx + 1  # 1-indexed
        try:
            page = doc.load_page(page_idx)
            raw_text = page.get_text("text")  # plain text extraction
        except Exception:
            raw_text = ""

        # Strip control characters that could cause issues but preserve whitespace
        text = _sanitize_text(raw_text)
        pages.append(PageContent(page_number=page_num, text=text))
        total_chars += len(text)

        if not text.strip():
            textless.append(page_num)

    doc.close()

    is_empty = len(textless) == page_count

    return ExtractionResult(
        success=True,
        pages=pages,
        page_count=page_count,
        total_chars=total_chars,
        textless_pages=textless,
        is_empty=is_empty,
    )


def _sanitize_text(text: str) -> str:
    """
    Remove null bytes and other binary noise while keeping printable text and whitespace.
    Does NOT strip newlines — they are meaningful for paragraph detection.
    """
    if not text:
        return ""
    # Replace null bytes
    text = text.replace("\x00", "")
    # Remove non-printable control chars (keep \n \r \t)
    cleaned = "".join(
        ch for ch in text
        if ch >= " " or ch in ("\n", "\r", "\t")
    )
    return cleaned
