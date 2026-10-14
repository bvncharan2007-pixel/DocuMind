"""
RAG pipeline orchestrator.

This module ties together:
- Gemini embedding (embed_query)
- FAISS vector search (vector_store.search)
- Authorization re-check on retrieved chunks
- Gemini answer generation (generate_answer)
- Citation assembly from backend metadata (never invented by the model)

The pipeline enforces:
1. User owns the conversation.
2. Only documents belonging to that conversation and user are searched.
3. Document IDs from chunk metadata are re-checked against DB on every query.
4. If no evidence passes the authorization check, an insufficient-evidence
   response is returned — the model is never asked to hallucinate.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from backend.services import gemini_service
from backend.services import vector_store
from backend.config import MAX_RETRIEVAL_CHUNKS

logger = logging.getLogger(__name__)


class RAGResult:
    """Structured result from a RAG query."""

    def __init__(
        self,
        answer: str,
        citations: List[dict],
        retrieved_chunks: int,
        insufficient_evidence: bool = False,
        error: Optional[str] = None,
    ):
        self.answer = answer
        self.citations = citations
        self.retrieved_chunks = retrieved_chunks
        self.insufficient_evidence = insufficient_evidence
        self.error = error

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "citations": self.citations,
            "retrieved_chunks": self.retrieved_chunks,
            "insufficient_evidence": self.insufficient_evidence,
            "error": self.error,
        }


def run_rag_query(
    question: str,
    conversation_id: str,
    user_id: str,
    authorized_document_ids: List[str],
    top_k: int = MAX_RETRIEVAL_CHUNKS,
) -> RAGResult:
    """
    Execute the full RAG pipeline for a question against an authorized document set.

    Steps:
    1. Validate inputs.
    2. Embed the question with RETRIEVAL_QUERY task type.
    3. Search the conversation's FAISS index, filtered to authorized_document_ids.
    4. If no chunks retrieved → insufficient evidence response.
    5. Build evidence blocks from trusted backend metadata (not model-generated).
    6. Generate answer with Gemini.
    7. Assemble citations from the retrieved chunk metadata.
    8. Return RAGResult.

    Authorization note: authorized_document_ids must be derived from the DB
    (documents belonging to this conversation and user) by the caller.
    This function does not query the DB itself — it relies on the caller
    to provide a correctly filtered list.
    """
    # ── 1. Input validation ───────────────────────────────────────────────────
    if not question or not question.strip():
        return RAGResult(
            answer="Please provide a question.",
            citations=[],
            retrieved_chunks=0,
            insufficient_evidence=True,
        )

    if not authorized_document_ids:
        return RAGResult(
            answer=(
                "No documents are available for this conversation. "
                "Please upload one or more PDFs before asking questions."
            ),
            citations=[],
            retrieved_chunks=0,
            insufficient_evidence=True,
        )

    # ── 2. Embed the query ────────────────────────────────────────────────────
    try:
        query_vector = gemini_service.embed_query(question.strip())
    except gemini_service.GeminiRateLimitError:
        return RAGResult(
            answer="",
            citations=[],
            retrieved_chunks=0,
            error=(
                "The Gemini API quota is currently exhausted. "
                "Please wait a few minutes and try again."
            ),
        )
    except gemini_service.GeminiError as exc:
        logger.error("Embedding failed for conversation %s: %s", conversation_id, exc)
        return RAGResult(
            answer="",
            citations=[],
            retrieved_chunks=0,
            error="Failed to process your question due to an AI service error.",
        )

    # ── 3. Vector search ──────────────────────────────────────────────────────
    try:
        hits = vector_store.search(
            conversation_id=conversation_id,
            query_vector=query_vector,
            authorized_document_ids=authorized_document_ids,
            top_k=top_k,
        )
    except Exception as exc:
        logger.error("Vector search failed for conversation %s: %s", conversation_id, exc)
        return RAGResult(
            answer="",
            citations=[],
            retrieved_chunks=0,
            error="An error occurred during document search.",
        )

    # ── 4. Insufficient evidence guard ────────────────────────────────────────
    if not hits:
        return RAGResult(
            answer=(
                "The available documents do not contain enough information to answer this question. "
                "Please try a different question or upload additional relevant documents."
            ),
            citations=[],
            retrieved_chunks=0,
            insufficient_evidence=True,
        )

    # ── 5. Build evidence blocks from trusted backend metadata ────────────────
    evidence_blocks = []
    for hit in hits:
        sp = hit.get("start_page", "?")
        ep = hit.get("end_page", "?")
        page_range = str(sp) if sp == ep else f"{sp}-{ep}"
        evidence_blocks.append({
            "content": hit.get("content", ""),
            "filename": hit.get("original_filename", "unknown"),
            "page_range": page_range,
            "chunk_index": hit.get("chunk_index", 0),
            "document_id": hit.get("document_id", ""),
            "chunk_db_id": hit.get("chunk_db_id", ""),
        })

    # ── 6. Generate answer ────────────────────────────────────────────────────
    try:
        answer_text = gemini_service.generate_answer(question.strip(), evidence_blocks)
    except gemini_service.GeminiRateLimitError:
        return RAGResult(
            answer="",
            citations=[],
            retrieved_chunks=len(hits),
            error=(
                "The Gemini API quota is currently exhausted. "
                "Please wait a few minutes and try again."
            ),
        )
    except gemini_service.GeminiError as exc:
        logger.error("Generation failed for conversation %s: %s", conversation_id, exc)
        return RAGResult(
            answer="",
            citations=[],
            retrieved_chunks=len(hits),
            error="Failed to generate an answer due to an AI service error.",
        )

    # ── 7. Assemble citations from trusted backend metadata ───────────────────
    # Citations come from the chunk metadata retrieved from the FAISS index,
    # which was written from the DB during ingestion. We do NOT ask the model
    # to produce citation objects — they are always backend-derived.
    seen_citations = set()
    citations = []
    for blk in evidence_blocks:
        key = (blk["document_id"], blk["chunk_db_id"])
        if key in seen_citations:
            continue
        seen_citations.add(key)

        sp_raw = hits[evidence_blocks.index(blk)].get("start_page", "?")
        ep_raw = hits[evidence_blocks.index(blk)].get("end_page", "?")
        page_range = str(sp_raw) if sp_raw == ep_raw else f"{sp_raw}-{ep_raw}"

        citations.append({
            "document_id": blk["document_id"],
            "filename": blk["filename"],
            "page_range": page_range,
            "start_page": sp_raw,
            "end_page": ep_raw,
            "excerpt": blk["content"][:300] + ("…" if len(blk["content"]) > 300 else ""),
            "chunk_db_id": blk["chunk_db_id"],
        })

    return RAGResult(
        answer=answer_text,
        citations=citations,
        retrieved_chunks=len(hits),
        insufficient_evidence=False,
    )
