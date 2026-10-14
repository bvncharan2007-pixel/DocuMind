"""
Conversation management routes — Phase 4.

Endpoints (all require approved session + CSRF on mutations):
  GET    /api/conversations                        — list user's own conversations
  POST   /api/conversations                        — create a new conversation
  GET    /api/conversations/{conv_id}              — get one owned conversation
  PATCH  /api/conversations/{conv_id}              — rename an owned conversation  [NEW]
  DELETE /api/conversations/{conv_id}              — delete an owned conversation  [NEW]
  GET    /api/conversations/{conv_id}/messages     — list messages in an owned conversation
  POST   /api/conversations/{conv_id}/messages     — manually append a message

Privacy rules (unchanged from Phase 2):
- Every query filters by BOTH conversation id AND current user id.
- Admins cannot access another user's conversations — the ownership check is not
  bypassed for any role.
- Conversation list never exposes message content, only counts.
"""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from backend.database import get_db
from backend.dependencies import require_approved_user, verify_csrf_token
from backend.models import (
    CitationResponse,
    ConversationCreateRequest,
    ConversationRenameRequest,
    ConversationResponse,
    MessageCreateRequest,
    MessageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/conversations",
    tags=["Conversations"],
    dependencies=[Depends(require_approved_user), Depends(verify_csrf_token)],
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_owner(conv_id: str, user_id: str, conn) -> dict:
    """Fetch conversation row and verify ownership. Raises 404/403 as appropriate."""
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


def _conv_response(row: dict, conn) -> ConversationResponse:
    """Build a ConversationResponse with summary counts."""
    msg_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM messages WHERE conversation_id = ?",
        (row["id"],)
    ).fetchone()["cnt"]
    doc_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM documents WHERE conversation_id = ?",
        (row["id"],)
    ).fetchone()["cnt"]
    return ConversationResponse(
        id=row["id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        message_count=msg_count,
        document_count=doc_count,
    )


def _parse_citations(raw: str | None) -> List[CitationResponse]:
    """Deserialise the JSON citations column; returns empty list on any error."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [CitationResponse(**c) for c in data]
    except Exception:
        return []


# ── List conversations ────────────────────────────────────────────────────────

@router.get("", response_model=List[ConversationResponse])
async def list_user_conversations(
    current_user: dict = Depends(require_approved_user),
):
    """
    List conversations belonging to the authenticated user only.
    Ordered by most-recent activity (updated_at DESC).
    Message content is never included in this list.
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (current_user["id"],),
        ).fetchall()
        return [_conv_response(dict(r), conn) for r in rows]


# ── Create conversation ───────────────────────────────────────────────────────

@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    req: ConversationCreateRequest,
    current_user: dict = Depends(require_approved_user),
):
    """
    Create a new private conversation for the current user.

    - title is optional; defaults to 'New conversation' (auto-updated when the
      first question is asked via /ask).
    - document_id is legacy/optional; it is stored as-is for backward
      compatibility but is no longer required.
    """
    conv_id = str(uuid.uuid4())
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    title = (req.title or "New conversation").strip() or "New conversation"
    doc_id = req.document_id or ""

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO conversations (id, user_id, document_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (conv_id, current_user["id"], doc_id, title, now_iso, now_iso),
        )
        row = {"id": conv_id, "title": title, "created_at": now_iso, "updated_at": now_iso}
        return ConversationResponse(
            id=conv_id,
            title=title,
            created_at=now_iso,
            updated_at=now_iso,
            message_count=0,
            document_count=0,
        )


# ── Get single conversation ───────────────────────────────────────────────────

@router.get("/{conv_id}", response_model=ConversationResponse)
async def get_conversation(
    conv_id: str,
    current_user: dict = Depends(require_approved_user),
):
    """Retrieve a single owned conversation with summary counts."""
    with get_db() as conn:
        row = _require_owner(conv_id, current_user["id"], conn)
        return _conv_response(row, conn)


# ── Rename conversation ───────────────────────────────────────────────────────

@router.patch("/{conv_id}", response_model=ConversationResponse)
async def rename_conversation(
    conv_id: str,
    req: ConversationRenameRequest,
    current_user: dict = Depends(require_approved_user),
):
    """Rename an owned conversation. Only the title is updated; messages and documents are untouched."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with get_db() as conn:
        _require_owner(conv_id, current_user["id"], conn)
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (req.title.strip(), now_iso, conv_id),
        )
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        return _conv_response(dict(row), conn)


# ── Delete conversation ───────────────────────────────────────────────────────

@router.delete("/{conv_id}", status_code=status.HTTP_200_OK)
async def delete_conversation(
    conv_id: str,
    current_user: dict = Depends(require_approved_user),
):
    """
    Permanently delete an owned conversation.

    Cascade behaviour (in order):
    1. Delete physical PDF files for every document in this conversation.
    2. Remove FAISS index and metadata files for this conversation.
    3. Delete the conversation row from DB — cascades to messages, documents,
       chunks, and index_metadata via FK ON DELETE CASCADE.

    This only removes the calling user's conversation — it cannot affect
    other users' data.
    """
    user_id = current_user["id"]

    with get_db() as conn:
        _require_owner(conv_id, user_id, conn)

        # Collect stored filenames before deleting rows
        doc_rows = conn.execute(
            "SELECT stored_filename FROM documents WHERE conversation_id = ? AND user_id = ?",
            (conv_id, user_id),
        ).fetchall()

        # Delete conversation row — FK CASCADE removes messages, documents, chunks, index_metadata
        conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))

    # Delete physical files after the DB transaction commits
    from backend.config import UPLOAD_DIR as _UPLOAD_DIR
    for dr in doc_rows:
        fp = _UPLOAD_DIR / dr["stored_filename"]
        if fp.exists():
            try:
                fp.unlink(missing_ok=True)
            except Exception as exc:
                logger.warning("Failed to delete file %s: %s", dr["stored_filename"], exc)

    # Delete FAISS index files
    from backend.services import vector_store
    vector_store.delete_conversation_index(conv_id)

    return {"message": "Conversation deleted.", "conversation_id": conv_id}


# ── List messages ─────────────────────────────────────────────────────────────

@router.get("/{conv_id}/messages", response_model=List[MessageResponse])
async def list_conversation_messages(
    conv_id: str,
    current_user: dict = Depends(require_approved_user),
):
    """
    Return all messages in a conversation in chronological order.
    Assistant messages include persisted citations where available.
    """
    with get_db() as conn:
        _require_owner(conv_id, current_user["id"], conn)

        rows = conn.execute(
            """
            SELECT id, conversation_id, role, content, created_at, citations
            FROM messages
            WHERE conversation_id = ? AND user_id = ?
            ORDER BY created_at ASC
            """,
            (conv_id, current_user["id"]),
        ).fetchall()

        return [
            MessageResponse(
                id=r["id"],
                conversation_id=r["conversation_id"],
                role=r["role"],
                content=r["content"],
                created_at=r["created_at"],
                citations=_parse_citations(r["citations"]),
            )
            for r in rows
        ]


# ── Manually append message ───────────────────────────────────────────────────

@router.post("/{conv_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def add_message(
    conv_id: str,
    req: MessageCreateRequest,
    current_user: dict = Depends(require_approved_user),
):
    """
    Manually append a message to an owned conversation.
    This is for direct message insertion; normal Q&A goes through /ask.
    Citations are not applicable to manually added messages.
    """
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    msg_id = str(uuid.uuid4())

    with get_db() as conn:
        _require_owner(conv_id, current_user["id"], conn)
        conn.execute(
            """
            INSERT INTO messages (id, conversation_id, user_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (msg_id, conv_id, current_user["id"], req.role, req.content, now_iso),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now_iso, conv_id),
        )

    return MessageResponse(
        id=msg_id,
        conversation_id=conv_id,
        role=req.role,
        content=req.content,
        created_at=now_iso,
        citations=[],
    )
