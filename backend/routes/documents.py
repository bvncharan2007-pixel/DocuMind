"""
Document upload and management routes.

Endpoints:
  POST   /api/conversations/{conv_id}/documents        — upload 1-N PDFs
  GET    /api/conversations/{conv_id}/documents        — list documents
  GET    /api/conversations/{conv_id}/documents/{doc_id}  — get single document status
  DELETE /api/conversations/{conv_id}/documents/{doc_id}  — remove a document

Security:
- All endpoints require an approved, authenticated session.
- CSRF token is validated on mutating requests via the router-level dependency.
- Conversation ownership is verified on every request before any file or DB access.
- Uploaded files are saved with server-generated UUIDs as filenames; the
  original filename is stored only as metadata.
- File content is never executed.
- File size is capped at MAX_FILE_SIZE_BYTES.
- Only application/pdf MIME types and %PDF magic bytes are accepted.
- Processing status accurately reflects the real outcome — documents are not
  marked 'completed' until text, chunks, embeddings, and index updates succeed.
"""

from __future__ import annotations

import datetime
import logging
import os
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from backend.config import (
    GEMINI_EMBEDDING_MODEL,
    GEMINI_EMBEDDING_DIMENSIONS,
    MAX_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_MB,
    MAX_FILES_PER_REQUEST,
    MAX_TOTAL_DOCUMENTS_PER_CONVERSATION,
    UPLOAD_DIR,
)
from backend.database import get_db
from backend.dependencies import require_approved_user, verify_csrf_token
from backend.models import (
    DocumentListResponse,
    DocumentResponse,
    DocumentStatusResponse,
    UploadResponse,
    UploadResultItem,
)
from backend.services.pdf_extractor import extract_pdf_pages
from backend.services.chunker import chunk_pages
from backend.services import gemini_service
from backend.services import vector_store

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/conversations/{conv_id}/documents",
    tags=["Documents"],
    dependencies=[Depends(require_approved_user), Depends(verify_csrf_token)],
)


# ── Authorization helper ──────────────────────────────────────────────────────

def _require_conversation_owner(conv_id: str, user_id: str, conn) -> dict:
    """
    Verify conversation exists and belongs to the requesting user.
    Raises 404 or 403 as appropriate. Returns the conversation row.
    """
    row = conn.execute(
        "SELECT * FROM conversations WHERE id = ?", (conv_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    if row["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not own this conversation.",
        )
    return dict(row)


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_documents(
    conv_id: str,
    files: List[UploadFile] = File(..., description="One or more PDF files"),
    current_user: dict = Depends(require_approved_user),
):
    """
    Upload one or more PDF files to an owned conversation.

    Each file is validated, saved, extracted, chunked, embedded, and indexed.
    Individual file failures are reported without aborting successfully processed files.
    Adding new files does NOT affect previously uploaded documents or chat history.

    Processing is synchronous in this implementation. A task-queue background
    worker can be substituted by changing the call below to an async task.
    """
    user_id = current_user["id"]

    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided.")

    from backend.config import MAX_FILES_PER_REQUEST as _MAX_FILES, MAX_TOTAL_DOCUMENTS_PER_CONVERSATION as _MAX_DOCS
    if len(files) > _MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files in one request. Maximum is {_MAX_FILES}.",
        )

    with get_db() as conn:
        _require_conversation_owner(conv_id, user_id, conn)

        # Check document count ceiling
        existing_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM documents WHERE conversation_id = ? AND user_id = ?",
            (conv_id, user_id),
        ).fetchone()["cnt"]

        if existing_count + len(files) > _MAX_DOCS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"This conversation already has {existing_count} document(s). "
                    f"Maximum is {_MAX_DOCS} per conversation."
                ),
            )

    results: List[UploadResultItem] = []
    accepted = 0
    failed = 0

    for upload_file in files:
        original_filename = upload_file.filename or "upload.pdf"
        result = await _process_single_upload(
            upload_file=upload_file,
            original_filename=original_filename,
            conv_id=conv_id,
            user_id=user_id,
        )
        results.append(result)
        if result.status == "processing":
            accepted += 1
        else:
            failed += 1

    return UploadResponse(results=results, accepted=accepted, failed=failed)


async def _process_single_upload(
    upload_file: UploadFile,
    original_filename: str,
    conv_id: str,
    user_id: str,
) -> UploadResultItem:
    """
    Handle end-to-end processing for a single uploaded file.
    Returns an UploadResultItem indicating success ('processing') or failure.
    """
    doc_id = str(uuid.uuid4())
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # ── 1. Read bytes ─────────────────────────────────────────────────────────
    try:
        file_bytes = await upload_file.read()
    except Exception as exc:
        return UploadResultItem(filename=original_filename, status="failed", error=f"Read error: {exc}")

    file_size = len(file_bytes)

    # ── 2. Size check ─────────────────────────────────────────────────────────
    from backend.config import MAX_FILE_SIZE_BYTES as _MAX_BYTES, MAX_FILE_SIZE_MB as _MAX_MB
    if file_size == 0:
        return UploadResultItem(filename=original_filename, status="failed", error="File is empty.")

    if file_size > _MAX_BYTES:
        return UploadResultItem(
            filename=original_filename,
            status="failed",
            error=f"File exceeds the {_MAX_MB} MB size limit.",
        )

    # ── 3. MIME / magic bytes check ───────────────────────────────────────────
    content_type = upload_file.content_type or ""
    if not (content_type == "application/pdf" or file_bytes[:4] == b"%PDF"):
        return UploadResultItem(
            filename=original_filename, status="failed", error="Only PDF files are accepted."
        )

    # ── 4. Create DB record in 'pending' state ────────────────────────────────
    stored_filename = f"{doc_id}.pdf"
    from backend.config import UPLOAD_DIR as _UPLOAD_DIR
    file_path = _UPLOAD_DIR / stored_filename

    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO documents
                  (id, conversation_id, user_id, original_filename, stored_filename,
                   file_size_bytes, status, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (doc_id, conv_id, user_id, original_filename, stored_filename, file_size, now_iso),
            )
    except Exception as exc:
        return UploadResultItem(filename=original_filename, status="failed", error="Database error creating document record.")

    # ── 5. Save file to disk ──────────────────────────────────────────────────
    try:
        with open(file_path, "wb") as f:
            f.write(file_bytes)
    except Exception as exc:
        _set_document_status(doc_id, "failed", f"Storage write error: {exc}")
        return UploadResultItem(filename=original_filename, status="failed", error="Failed to store file.")

    # ── 6. Update to 'processing' ─────────────────────────────────────────────
    _set_document_status(doc_id, "processing")

    # ── 7. Process synchronously ──────────────────────────────────────────────
    error = _ingest_document(
        doc_id=doc_id,
        file_bytes=file_bytes,
        original_filename=original_filename,
        conv_id=conv_id,
        user_id=user_id,
    )

    if error:
        return UploadResultItem(
            filename=original_filename,
            document_id=doc_id,
            status="failed",
            error=error,
        )

    return UploadResultItem(
        filename=original_filename,
        document_id=doc_id,
        status="processing",   # actual status in DB is now 'completed'
    )


def _ingest_document(
    doc_id: str,
    file_bytes: bytes,
    original_filename: str,
    conv_id: str,
    user_id: str,
) -> str | None:
    """
    Full ingestion pipeline: extract → chunk → embed → index → DB.
    Returns None on success, or an error string on failure.
    Document status is updated in DB throughout.
    """
    # ── A. PDF extraction ─────────────────────────────────────────────────────
    extraction = extract_pdf_pages(file_bytes, filename=original_filename)
    if not extraction.success:
        _set_document_status(doc_id, "failed", extraction.error)
        return extraction.error

    if extraction.is_empty:
        msg = (
            "This PDF appears to be a scanned image. No text layer was found. "
            "OCR is not supported in this version."
        )
        _set_document_status(doc_id, "failed", msg, page_count=extraction.page_count)
        return msg

    # Update page count in DB
    _update_page_count(doc_id, extraction.page_count)

    # ── B. Chunking ───────────────────────────────────────────────────────────
    chunks = chunk_pages(extraction.pages)
    if not chunks:
        msg = "No text chunks could be extracted from this PDF."
        _set_document_status(doc_id, "failed", msg)
        return msg

    # ── C. Persist chunks in DB ───────────────────────────────────────────────
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    chunk_rows = []
    for ch in chunks:
        ch_id = str(uuid.uuid4())
        ch.chunk_db_id = ch_id
        ch.document_id = doc_id
        ch.conversation_id = conv_id
        ch.user_id = user_id
        chunk_rows.append((
            ch_id, doc_id, conv_id, user_id,
            ch.chunk_index, ch.content,
            ch.start_page, ch.end_page,
            ch.char_start, ch.char_end,
            now_iso,
        ))

    try:
        with get_db() as conn:
            conn.executemany(
                """
                INSERT INTO chunks
                  (id, document_id, conversation_id, user_id, chunk_index, content,
                   start_page, end_page, char_start, char_end, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                chunk_rows,
            )
    except Exception as exc:
        msg = "Failed to persist text chunks to database."
        _set_document_status(doc_id, "failed", msg)
        return msg

    # ── D. Embed chunks ───────────────────────────────────────────────────────
    texts = [ch.content for ch in chunks]
    try:
        vectors = gemini_service.embed_texts(texts)
    except Exception as exc:
        # Covers GeminiError subclasses, rate limits, and any unexpected error
        msg = f"Embedding failed: {type(exc).__name__}. Chunks saved but not indexed."
        _set_document_status(doc_id, "failed", msg)
        return msg

    if len(vectors) != len(chunks):
        msg = "Embedding returned unexpected number of vectors."
        _set_document_status(doc_id, "failed", msg)
        return msg

    # ── E. Build vector metadata ──────────────────────────────────────────────
    chunk_metas = [
        {
            "chunk_db_id": ch.chunk_db_id,
            "document_id": doc_id,
            "user_id": user_id,
            "conversation_id": conv_id,
            "original_filename": original_filename,
            "chunk_index": ch.chunk_index,
            "start_page": ch.start_page,
            "end_page": ch.end_page,
            "content": ch.content,
        }
        for ch in chunks
    ]

    # ── F. Add to FAISS index ─────────────────────────────────────────────────
    try:
        with get_db() as conn:
            vector_store.add_vectors(
                conversation_id=conv_id,
                user_id=user_id,
                vectors=vectors,
                chunk_metas=chunk_metas,
                db_conn=conn,
            )
    except Exception as exc:
        msg = f"Failed to add vectors to search index: {type(exc).__name__}"
        _set_document_status(doc_id, "failed", msg)
        return msg

    # ── G. Mark completed ─────────────────────────────────────────────────────
    processed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE documents SET status = 'completed', processed_at = ?, error_message = NULL WHERE id = ?",
            (processed_at, doc_id),
        )

    logger.info(
        "Document %s (%s) ingested: %d pages, %d chunks, %d vectors.",
        doc_id, original_filename, extraction.page_count, len(chunks), len(vectors),
    )
    return None


# ── Status helpers ────────────────────────────────────────────────────────────

def _set_document_status(
    doc_id: str,
    new_status: str,
    error_message: str | None = None,
    page_count: int | None = None,
) -> None:
    try:
        with get_db() as conn:
            if page_count is not None:
                conn.execute(
                    "UPDATE documents SET status = ?, error_message = ?, page_count = ? WHERE id = ?",
                    (new_status, error_message, page_count, doc_id),
                )
            else:
                conn.execute(
                    "UPDATE documents SET status = ?, error_message = ? WHERE id = ?",
                    (new_status, error_message, doc_id),
                )
    except Exception as exc:
        logger.error("Failed to update document status for %s: %s", doc_id, exc)


def _update_page_count(doc_id: str, page_count: int) -> None:
    try:
        with get_db() as conn:
            conn.execute(
                "UPDATE documents SET page_count = ? WHERE id = ?",
                (page_count, doc_id),
            )
    except Exception as exc:
        logger.error("Failed to update page_count for %s: %s", doc_id, exc)


# ── List documents ────────────────────────────────────────────────────────────

@router.get("", response_model=DocumentListResponse)
async def list_documents(
    conv_id: str,
    current_user: dict = Depends(require_approved_user),
):
    """List all documents in an owned conversation."""
    user_id = current_user["id"]
    with get_db() as conn:
        _require_conversation_owner(conv_id, user_id, conn)

        rows = conn.execute(
            """
            SELECT id, conversation_id, original_filename, file_size_bytes,
                   page_count, status, error_message, uploaded_at, processed_at
            FROM documents
            WHERE conversation_id = ? AND user_id = ?
            ORDER BY uploaded_at ASC
            """,
            (conv_id, user_id),
        ).fetchall()

    docs = [
        DocumentResponse(
            id=r["id"],
            conversation_id=r["conversation_id"],
            original_filename=r["original_filename"],
            file_size_bytes=r["file_size_bytes"],
            page_count=r["page_count"],
            status=r["status"],
            error_message=r["error_message"],
            uploaded_at=r["uploaded_at"],
            processed_at=r["processed_at"],
        )
        for r in rows
    ]
    return DocumentListResponse(documents=docs, total=len(docs))


# ── Get single document ───────────────────────────────────────────────────────

@router.get("/{doc_id}", response_model=DocumentStatusResponse)
async def get_document_status(
    conv_id: str,
    doc_id: str,
    current_user: dict = Depends(require_approved_user),
):
    """Get processing status of a single document."""
    user_id = current_user["id"]
    with get_db() as conn:
        _require_conversation_owner(conv_id, user_id, conn)

        row = conn.execute(
            """
            SELECT id, original_filename, status, error_message, page_count, processed_at
            FROM documents
            WHERE id = ? AND conversation_id = ? AND user_id = ?
            """,
            (doc_id, conv_id, user_id),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    return DocumentStatusResponse(
        id=row["id"],
        original_filename=row["original_filename"],
        status=row["status"],
        error_message=row["error_message"],
        page_count=row["page_count"],
        processed_at=row["processed_at"],
    )


# ── Delete document ───────────────────────────────────────────────────────────

@router.delete("/{doc_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    conv_id: str,
    doc_id: str,
    current_user: dict = Depends(require_approved_user),
):
    """
    Remove a document from a conversation.

    Deletes:
    - DB record (cascades to chunks via FK).
    - The stored PDF file from disk.

    The FAISS index is rebuilt from remaining chunks so orphaned vectors are
    purged. This is safe because the index_metadata table tracks which model
    and dimensions were used, and we re-embed only if necessary.

    Note: conversation history (messages) is NOT deleted.
    """
    user_id = current_user["id"]

    with get_db() as conn:
        _require_conversation_owner(conv_id, user_id, conn)

        row = conn.execute(
            "SELECT * FROM documents WHERE id = ? AND conversation_id = ? AND user_id = ?",
            (doc_id, conv_id, user_id),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        stored_filename = row["stored_filename"]
        # Delete from DB (cascades to chunks)
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    # Delete physical file
    from backend.config import UPLOAD_DIR as _UPLOAD_DIR
    file_path = _UPLOAD_DIR / stored_filename
    if file_path.exists():
        try:
            file_path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Failed to delete file %s: %s", stored_filename, exc)

    # Rebuild the FAISS index without this document's vectors
    _rebuild_index_for_conversation(conv_id, user_id)

    return {"message": "Document deleted successfully.", "document_id": doc_id}


def _rebuild_index_for_conversation(conv_id: str, user_id: str) -> None:
    """
    Rebuild the FAISS index for a conversation from the persisted chunks in DB.
    Called after a document deletion to purge orphaned vectors.
    """
    # Delete existing index files
    vector_store.delete_conversation_index(conv_id)

    # Load remaining chunks from DB
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.document_id, c.chunk_index, c.content,
                   c.start_page, c.end_page, d.original_filename
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.conversation_id = ? AND c.user_id = ?
              AND d.status = 'completed'
            ORDER BY c.document_id, c.chunk_index
            """,
            (conv_id, user_id),
        ).fetchall()

        # Clear old index_metadata entry
        conn.execute(
            "DELETE FROM index_metadata WHERE conversation_id = ?",
            (conv_id,)
        )

    if not rows:
        return  # No chunks left — index stays empty

    texts = [r["content"] for r in rows]
    try:
        vectors = gemini_service.embed_texts(texts)
    except gemini_service.GeminiError as exc:
        logger.error("Rebuild embed failed for conv %s: %s", conv_id, exc)
        return

    chunk_metas = [
        {
            "chunk_db_id": r["id"],
            "document_id": r["document_id"],
            "user_id": user_id,
            "conversation_id": conv_id,
            "original_filename": r["original_filename"],
            "chunk_index": r["chunk_index"],
            "start_page": r["start_page"],
            "end_page": r["end_page"],
            "content": r["content"],
        }
        for r in rows
    ]

    try:
        with get_db() as conn:
            vector_store.add_vectors(conv_id, user_id, vectors, chunk_metas, db_conn=conn)
    except Exception as exc:
        logger.error("Rebuild index failed for conv %s: %s", conv_id, exc)
