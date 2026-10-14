"""
Question-answering route — Phase 4.

POST /api/conversations/{conv_id}/ask

Security flow (unchanged from Phase 3):
1. require_approved_user  → authenticated + approved session
2. Conversation ownership check (user_id must match)
3. Only completed documents belonging to that conversation and user are searched
4. The answer and citations are derived from trusted backend metadata
5. Message persistence now includes serialised citations on the assistant row

Phase 4 additions:
- Citations are serialised to JSON and stored in messages.citations column.
- If the conversation title is still the default "New conversation", it is
  automatically updated to a trimmed version of the first user question.
- If RAG generation fails, the user message is still persisted but the
  assistant message content clearly records the error — no silent fake answer.
- conversation_title is echoed back in AnswerResponse for the frontend sidebar.
"""

from __future__ import annotations

import datetime
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from backend.database import get_db
from backend.dependencies import require_approved_user, verify_csrf_token
from backend.models import AnswerResponse, CitationResponse, QuestionRequest
from backend.services.rag_pipeline import run_rag_query

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/conversations",
    tags=["Question Answering"],
    dependencies=[Depends(require_approved_user), Depends(verify_csrf_token)],
)

_AUTO_TITLE_MAX_CHARS = 80   # truncate auto-generated title at this length


@router.post("/{conv_id}/ask", response_model=AnswerResponse)
async def ask_question(
    conv_id: str,
    req: QuestionRequest,
    current_user: dict = Depends(require_approved_user),
):
    """
    Ask a question against the PDF documents in an owned conversation.

    Flow:
    1. Verify conversation ownership.
    2. Collect completed document IDs for this conversation and user.
    3. Run RAG pipeline (embed query → FAISS search → Gemini generation).
    4. Persist user question and assistant answer (with citations) as messages.
    5. Auto-title the conversation from the first question if still default.
    6. Return structured answer with source citations.
    """
    user_id = current_user["id"]

    # ── 1. Verify ownership and load conversation ─────────────────────────────
    with get_db() as conn:
        conv = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()

        if not conv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

        if conv["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You do not own this conversation.",
            )

        # ── 2. Get authorized completed documents ─────────────────────────────
        doc_rows = conn.execute(
            """
            SELECT id FROM documents
            WHERE conversation_id = ? AND user_id = ? AND status = 'completed'
            """,
            (conv_id, user_id),
        ).fetchall()

        # Check if this is the first message (for auto-title)
        is_first_message = conn.execute(
            "SELECT COUNT(*) AS cnt FROM messages WHERE conversation_id = ?",
            (conv_id,),
        ).fetchone()["cnt"] == 0

    authorized_doc_ids = [r["id"] for r in doc_rows]
    current_title = conv["title"]

    # ── 3. Run RAG pipeline ───────────────────────────────────────────────────
    rag_result = run_rag_query(
        question=req.question,
        conversation_id=conv_id,
        user_id=user_id,
        authorized_document_ids=authorized_doc_ids,
    )

    # ── 4. Determine what to persist ─────────────────────────────────────────
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    assistant_msg_id = str(uuid.uuid4())
    user_msg_id = str(uuid.uuid4())

    # If generation failed, persist error text; never persist an empty string
    if rag_result.error and not rag_result.answer:
        answer_to_persist = f"[Error] {rag_result.error}"
    else:
        answer_to_persist = rag_result.answer or ""

    # Serialise citations to JSON for the assistant message row
    citations_json: str | None = None
    if rag_result.citations:
        try:
            citations_json = json.dumps([
                {
                    "document_id": c["document_id"],
                    "filename": c["filename"],
                    "page_range": c["page_range"],
                    "start_page": c["start_page"],
                    "end_page": c["end_page"],
                    "excerpt": c["excerpt"],
                }
                for c in rag_result.citations
            ])
        except Exception:
            citations_json = None

    # ── 5. Auto-title from first question ────────────────────────────────────
    new_title = current_title
    should_auto_title = is_first_message and current_title in ("New conversation", "")
    if should_auto_title:
        raw = req.question.strip()
        new_title = (raw[:_AUTO_TITLE_MAX_CHARS] + "…") if len(raw) > _AUTO_TITLE_MAX_CHARS else raw

    # ── 6. Persist everything in one transaction ──────────────────────────────
    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO messages (id, conversation_id, user_id, role, content, created_at)
                VALUES (?, ?, ?, 'user', ?, ?)
                """,
                (user_msg_id, conv_id, user_id, req.question, now_iso),
            )
            conn.execute(
                """
                INSERT INTO messages (id, conversation_id, user_id, role, content, created_at, citations)
                VALUES (?, ?, ?, 'assistant', ?, ?, ?)
                """,
                (assistant_msg_id, conv_id, user_id, answer_to_persist, now_iso, citations_json),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ?, title = ? WHERE id = ?",
                (now_iso, new_title, conv_id),
            )
    except Exception as exc:
        logger.error("Failed to persist conversation messages for %s: %s", conv_id, exc)
        # Non-fatal: answer is returned even if persistence fails; title stays unchanged
        new_title = current_title

    # ── 7. Build response ─────────────────────────────────────────────────────
    citation_responses = [
        CitationResponse(
            document_id=c["document_id"],
            filename=c["filename"],
            page_range=c["page_range"],
            start_page=c["start_page"],
            end_page=c["end_page"],
            excerpt=c["excerpt"],
        )
        for c in rag_result.citations
    ]

    return AnswerResponse(
        answer=rag_result.answer,
        citations=citation_responses,
        retrieved_chunks=rag_result.retrieved_chunks,
        insufficient_evidence=rag_result.insufficient_evidence,
        error=rag_result.error,
        conversation_id=conv_id,
        message_id=assistant_msg_id,
        conversation_title=new_title,
    )
