"""
Page-aware text chunker.

Design decisions:
- Chunks never cross page boundaries ambiguously: a chunk is assigned the
  page range [start_page, end_page] derived from the actual pages it spans.
- Within a single page the text is split by character count with configurable
  overlap so that boundary sentences are not cut off completely.
- Overlap is implemented by including the last CHUNK_OVERLAP characters from
  the previous chunk at the start of the next chunk.
- Empty pages and pages with only whitespace are skipped rather than indexed.
- Repeated headers / footers (same content across many pages) are not
  deduplicated here — callers may opt to do so at index time.
- Returns Chunk objects that include all metadata needed for citations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from backend.config import CHUNK_SIZE, CHUNK_OVERLAP
from backend.services.pdf_extractor import PageContent


@dataclass
class Chunk:
    """A single indexable text chunk with page-provenance metadata."""
    chunk_index: int           # sequential 0-based index within the document
    content: str               # the actual text to embed
    start_page: int            # first PDF page this chunk draws from (1-indexed)
    end_page: int              # last  PDF page this chunk draws from (1-indexed)
    char_start: int            # character offset within the per-document stream
    char_end: int

    # Set by the caller after DB insertion
    document_id: str = ""
    conversation_id: str = ""
    user_id: str = ""
    chunk_db_id: str = ""      # UUID assigned in the database


def chunk_pages(
    pages: List[PageContent],
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[Chunk]:
    """
    Produce an ordered list of Chunk objects from a list of PageContent items.

    Strategy:
    1. Accumulate page texts one at a time, tagging each character with its
       source page number.
    2. Slide a window of `chunk_size` characters across the character stream,
       advancing by `chunk_size - overlap` characters each step.
    3. For every window record the min/max page numbers touched.

    This gives accurate multi-page spans when a single page is longer than
    chunk_size, and accurate single-page attribution when text is short.
    """
    if overlap >= chunk_size:
        overlap = chunk_size // 4  # guard against misconfiguration

    # ── 1. Build a flat character stream with page tags ───────────────────────
    char_stream: List[str] = []
    page_tags: List[int] = []    # page_tags[i] = page number of char i

    for page in pages:
        text = page.text
        if not text.strip():
            continue  # skip empty / whitespace-only pages
        # Ensure pages are separated by a newline so chunks don't bleed across
        # pages without any boundary signal
        if char_stream and char_stream[-1] != "\n":
            char_stream.append("\n")
            page_tags.append(page.page_number)
        for ch in text:
            char_stream.append(ch)
            page_tags.append(page.page_number)

    total_chars = len(char_stream)
    if total_chars == 0:
        return []

    # ── 2. Slide window ───────────────────────────────────────────────────────
    step = max(1, chunk_size - overlap)
    chunks: List[Chunk] = []
    idx = 0
    chunk_index = 0

    while idx < total_chars:
        end = min(idx + chunk_size, total_chars)
        window_chars = char_stream[idx:end]
        window_pages = page_tags[idx:end]

        content = "".join(window_chars).strip()
        if content:
            chunks.append(
                Chunk(
                    chunk_index=chunk_index,
                    content=content,
                    start_page=min(window_pages),
                    end_page=max(window_pages),
                    char_start=idx,
                    char_end=end,
                )
            )
            chunk_index += 1

        idx += step

    return chunks
