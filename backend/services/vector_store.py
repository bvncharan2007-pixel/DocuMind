"""
FAISS vector index manager — per-conversation, user-scoped.

Index isolation model:
- One FAISS index per conversation.
- An index is only created/opened for a conversation that belongs to the
  requesting user. Authorization is enforced by the route layer BEFORE this
  service is called, and re-checked here before returning any content.
- Index files and metadata files are stored in DOCUMIND_INDEX_DIR with
  server-generated filenames derived from conversation UUID — not user-supplied paths.

Security:
- Path traversal is prevented by building index paths from sanitised UUIDs only.
- Index files and metadata files are stored outside public web-server directories.
- Pickle-based numpy/faiss serialisation is NOT used for the chunk metadata
  (which could be exploited via untrusted deserialization); JSON is used instead.
- The FAISS binary index itself is loaded via faiss.read_index(), which reads
  a purpose-built binary format — not an arbitrary serialised Python object.

Persistence:
- Each conversation's FAISS index is stored as:
    <INDEX_DIR>/<conversation_id>.faiss       — the binary FAISS IndexFlatL2
    <INDEX_DIR>/<conversation_id>.meta.json   — JSON mapping vector_id → chunk metadata
- The index_metadata DB table tracks which model/dims were used for each index
  to detect incompatible rebuilds.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import faiss
import numpy as np

from backend.config import (
    INDEX_DIR,
    GEMINI_EMBEDDING_MODEL,
    GEMINI_EMBEDDING_DIMENSIONS,
)

logger = logging.getLogger(__name__)

# ── Path helpers ──────────────────────────────────────────────────────────────

_SAFE_ID_RE = re.compile(r"^[a-f0-9\-]{36}$")  # UUID v4


def _safe_conversation_id(conversation_id: str) -> str:
    """
    Validate that the conversation_id is a well-formed UUID before using it
    to build a filesystem path. Raises ValueError on invalid input.
    """
    if not _SAFE_ID_RE.match(conversation_id.lower()):
        raise ValueError(f"Invalid conversation_id format: {conversation_id!r}")
    return conversation_id.lower()


def _index_file_path(conversation_id: str) -> Path:
    cid = _safe_conversation_id(conversation_id)
    # Read INDEX_DIR dynamically so test fixtures that change env vars take effect
    from backend.config import INDEX_DIR as _IDX
    return _IDX / f"{cid}.faiss"


def _meta_file_path(conversation_id: str) -> Path:
    cid = _safe_conversation_id(conversation_id)
    from backend.config import INDEX_DIR as _IDX
    return _IDX / f"{cid}.meta.json"


# ── Metadata file ─────────────────────────────────────────────────────────────

def _load_meta(conversation_id: str) -> Dict[str, dict]:
    """
    Load the JSON metadata file for a conversation index.
    Returns an empty dict if the file does not exist or is corrupted.
    Keys are stringified integer vector IDs.
    """
    path = _meta_file_path(conversation_id)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning("Meta file for %s is not a JSON object; resetting.", conversation_id)
            return {}
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load meta file for %s: %s; resetting.", conversation_id, exc)
        return {}


def _save_meta(conversation_id: str, meta: Dict[str, dict]) -> None:
    path = _meta_file_path(conversation_id)
    path.parent.mkdir(parents=True, exist_ok=True)  # ensure dir exists
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=None)


# ── FAISS index helpers ───────────────────────────────────────────────────────

def _load_faiss_index(conversation_id: str) -> Optional[faiss.IndexFlatL2]:
    """Load a persisted FAISS index. Returns None if missing or corrupt."""
    path = _index_file_path(conversation_id)
    if not path.exists():
        return None
    try:
        index = faiss.read_index(str(path))
        return index
    except Exception as exc:
        logger.warning("Failed to load FAISS index for %s: %s", conversation_id, exc)
        return None


def _save_faiss_index(conversation_id: str, index: faiss.IndexFlatL2) -> None:
    path = _index_file_path(conversation_id)
    path.parent.mkdir(parents=True, exist_ok=True)  # ensure dir exists
    faiss.write_index(index, str(path))


def _create_new_index(dimensions: int) -> faiss.IndexFlatL2:
    """Create a brand-new L2 flat index with the given vector dimensions."""
    return faiss.IndexFlatL2(dimensions)


# ── Public API ────────────────────────────────────────────────────────────────

def add_vectors(
    conversation_id: str,
    user_id: str,
    vectors: List[List[float]],
    chunk_metas: List[dict],
    db_conn=None,
) -> int:
    """
    Add vectors and their metadata to the conversation's FAISS index.

    Each entry in chunk_metas must be a dict with at minimum:
        chunk_db_id, document_id, user_id, conversation_id,
        original_filename, chunk_index, start_page, end_page, content

    Returns the total number of vectors now in the index.

    Idempotency: if a chunk_db_id already exists in the meta, it is skipped
    to prevent duplicate indexing on retry.
    """
    if not vectors:
        return 0

    _safe_conversation_id(conversation_id)   # validate

    from backend.config import GEMINI_EMBEDDING_DIMENSIONS as dims
    index = _load_faiss_index(conversation_id)
    meta = _load_meta(conversation_id)

    if index is None:
        index = _create_new_index(dims)

    # Build a set of already-indexed chunk IDs for dedup check
    already_indexed = {v["chunk_db_id"] for v in meta.values() if "chunk_db_id" in v}

    new_vectors: List[List[float]] = []
    new_metas: List[dict] = []

    for vec, cm in zip(vectors, chunk_metas):
        cid = cm.get("chunk_db_id", "")
        if cid in already_indexed:
            logger.debug("Chunk %s already indexed; skipping.", cid)
            continue
        # Validate vector dimension
        if len(vec) != dims:
            raise ValueError(
                f"Vector dimension mismatch: expected {dims}, got {len(vec)} "
                f"for chunk {cid}. Re-embed with the same model/dimension settings."
            )
        new_vectors.append(vec)
        new_metas.append(cm)

    if not new_vectors:
        return index.ntotal

    # Current total is the starting vector ID for the new batch
    start_id = index.ntotal

    arr = np.array(new_vectors, dtype=np.float32)
    index.add(arr)

    for offset, cm in enumerate(new_metas):
        vector_id = str(start_id + offset)
        meta[vector_id] = {
            "chunk_db_id": cm.get("chunk_db_id", ""),
            "document_id": cm.get("document_id", ""),
            "user_id": cm.get("user_id", ""),
            "conversation_id": cm.get("conversation_id", ""),
            "original_filename": cm.get("original_filename", ""),
            "chunk_index": cm.get("chunk_index", 0),
            "start_page": cm.get("start_page", 1),
            "end_page": cm.get("end_page", 1),
            "content": cm.get("content", ""),
        }

    _save_faiss_index(conversation_id, index)
    _save_meta(conversation_id, meta)

    # Update index_metadata DB record if a connection was provided
    if db_conn is not None:
        _upsert_index_metadata(db_conn, conversation_id, user_id, index.ntotal)

    logger.info(
        "Added %d vectors to conversation %s index (total: %d).",
        len(new_vectors), conversation_id, index.ntotal
    )
    return index.ntotal


def search(
    conversation_id: str,
    query_vector: List[float],
    authorized_document_ids: List[str],
    top_k: int = 6,
) -> List[dict]:
    """
    Search the conversation's FAISS index for the nearest neighbours.

    Authorization re-check: only returns chunks whose document_id is in
    authorized_document_ids. This ensures that even if the index contained
    stale entries, only currently-authorized documents are surfaced.

    Returns a list of dicts ordered by ascending L2 distance:
        chunk_db_id, document_id, original_filename, start_page, end_page,
        content, chunk_index, l2_distance
    """
    if not authorized_document_ids:
        return []

    index = _load_faiss_index(conversation_id)
    if index is None or index.ntotal == 0:
        return []

    from backend.config import GEMINI_EMBEDDING_DIMENSIONS as dims
    if len(query_vector) != dims:
        raise ValueError(
            f"Query vector dimension {len(query_vector)} does not match index dimension {dims}."
        )

    meta = _load_meta(conversation_id)
    if not meta:
        return []

    auth_set = set(authorized_document_ids)

    # Search for more than top_k to account for post-filtering
    search_k = min(index.ntotal, max(top_k * 3, top_k + 20))
    query_arr = np.array([query_vector], dtype=np.float32)

    try:
        distances, indices = index.search(query_arr, search_k)
    except Exception as exc:
        logger.error("FAISS search failed for conversation %s: %s", conversation_id, exc)
        return []

    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx == -1:
            continue
        entry = meta.get(str(idx))
        if entry is None:
            continue
        # Authorization re-check
        if entry.get("document_id") not in auth_set:
            continue
        results.append({
            **entry,
            "l2_distance": float(dist),
        })
        if len(results) >= top_k:
            break

    return results


def delete_conversation_index(conversation_id: str) -> None:
    """Remove FAISS index and metadata files for a conversation."""
    try:
        _safe_conversation_id(conversation_id)
    except ValueError:
        return

    for path in [_index_file_path(conversation_id), _meta_file_path(conversation_id)]:
        if path.exists():
            path.unlink(missing_ok=True)


def get_index_stats(conversation_id: str) -> dict:
    """Return basic stats about the current index (for diagnostics)."""
    index = _load_faiss_index(conversation_id)
    meta = _load_meta(conversation_id)
    return {
        "total_vectors": index.ntotal if index else 0,
        "total_meta_entries": len(meta),
        "index_file_exists": _index_file_path(conversation_id).exists(),
        "meta_file_exists": _meta_file_path(conversation_id).exists(),
    }


# ── DB helper ─────────────────────────────────────────────────────────────────

def _upsert_index_metadata(conn, conversation_id: str, user_id: str, total_vectors: int) -> None:
    from backend.config import GEMINI_EMBEDDING_MODEL as _model, GEMINI_EMBEDDING_DIMENSIONS as _dims
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    existing = conn.execute(
        "SELECT id FROM index_metadata WHERE conversation_id = ?",
        (conversation_id,)
    ).fetchone()

    idx_file = str(_index_file_path(conversation_id))
    meta_file = str(_meta_file_path(conversation_id))

    if existing:
        conn.execute(
            """
            UPDATE index_metadata
            SET total_vectors = ?, updated_at = ?
            WHERE conversation_id = ?
            """,
            (total_vectors, now, conversation_id)
        )
    else:
        conn.execute(
            """
            INSERT INTO index_metadata
            (id, conversation_id, user_id, embedding_model, embedding_dimensions,
             index_version, total_vectors, index_file, meta_file, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                conversation_id,
                user_id,
                _model,
                _dims,
                total_vectors,
                idx_file,
                meta_file,
                now,
                now,
            )
        )
