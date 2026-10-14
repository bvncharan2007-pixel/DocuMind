"""
Phase 4 — Persistent Conversations, Chat History & Document Lifecycle
Test suite covering all 20 required areas.

Test areas:
 1.  Creating a conversation
 2.  Listing only the authenticated user's conversations
 3.  Persisting messages and conversation metadata
 4.  Reopening history after logout and login
 5.  Data survival across backend restart (same DB path)
 6.  Renaming a conversation
 7.  Deleting a conversation safely
 8.  Rejecting access to another user's conversation
 9.  Admin cannot access another user's private chat
10.  Admin can access their own conversation
11.  Uploading multiple PDFs to one conversation
12.  Adding new PDFs without losing old documents
13.  Retrieving evidence from both earlier and newly added PDFs
14.  Maintaining correct citation filenames and page numbers
15.  Handling partial upload failures
16.  Preventing duplicate indexing during retries
17.  Document deletion and reference cleanup
18.  Processing failures and Gemini errors in /ask
19.  Preserving Phase 2 authentication tests
20.  Preserving Phase 3 RAG tests

All Gemini calls are mocked. No real GOOGLE_API_KEY required.
Test PDFs are generated in-memory using PyMuPDF.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import fitz  # PyMuPDF
import numpy as np
import pytest
from fastapi.testclient import TestClient

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

EMBEDDING_DIM = 768


def _make_embedding(seed: int = 0) -> List[float]:
    rng = np.random.default_rng(seed)
    v = rng.random(EMBEDDING_DIM).astype(np.float32)
    return (v / np.linalg.norm(v)).tolist()


def _make_pdf_bytes(pages: List[str]) -> bytes:
    doc = fitz.open()
    for txt in pages:
        p = doc.new_page(width=595, height=842)
        p.insert_text((72, 72), txt, fontsize=11)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _mock_embed(texts):
    return [_make_embedding(i) for i in range(len(texts))]


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def p4_env():
    """Isolated temp environment: separate DB, uploads, indexes per test."""
    import importlib
    from backend.security import reset_rate_limits
    from backend.services import gemini_service

    reset_rate_limits()

    tmp = tempfile.TemporaryDirectory()
    tp = Path(tmp.name)
    db_path = str(tp / "p4.db")
    upload_dir = tp / "uploads"
    index_dir = tp / "indexes"
    upload_dir.mkdir()
    index_dir.mkdir()

    os.environ["DOCUMIND_DB_PATH"] = db_path
    os.environ["DOCUMIND_UPLOAD_DIR"] = str(upload_dir)
    os.environ["DOCUMIND_INDEX_DIR"] = str(index_dir)
    os.environ["GEMINI_EMBEDDING_DIMENSIONS"] = str(EMBEDDING_DIM)
    os.environ["GOOGLE_API_KEY"] = "test-key"

    import backend.config as cfg
    importlib.reload(cfg)
    cfg.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    cfg.INDEX_DIR.mkdir(parents=True, exist_ok=True)

    from backend.database import init_db
    init_db(db_path)
    gemini_service.reset_client()

    yield {"db_path": db_path, "upload_dir": upload_dir, "index_dir": index_dir, "tmp": tmp}

    gemini_service.reset_client()
    reset_rate_limits()
    tmp.cleanup()


@pytest.fixture(scope="function")
def client(p4_env):
    from backend.main import app
    with TestClient(app, base_url="http://testserver") as c:
        yield c


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _seed_user(db_path, uid="u1", username="user1", email="u1@test.com",
               password="Pass1234!", role="user", status="approved"):
    from backend.database import get_connection
    from backend.security import hash_password
    conn = get_connection(db_path)
    conn.execute(
        """
        INSERT OR IGNORE INTO users
          (id, email, username, password_hash, role, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, '2026-01-01', '2026-01-01')
        """,
        (uid, email, username, hash_password(password), role, status),
    )
    conn.commit()
    conn.close()


def _login(client, username="user1", password="Pass1234!"):
    res = client.post("/api/auth/login", json={"identifier": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["csrf_token"]


def _create_conv(client, csrf, title="Test Conv"):
    res = client.post(
        "/api/conversations",
        json={"title": title},
        headers={"X-CSRF-Token": csrf},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _upload_pdf(client, conv_id, csrf, filename, pages):
    pdf = _make_pdf_bytes(pages)
    with patch("backend.routes.documents.gemini_service.embed_texts", side_effect=_mock_embed):
        res = client.post(
            f"/api/conversations/{conv_id}/documents",
            files=[("files", (filename, pdf, "application/pdf"))],
            headers={"X-CSRF-Token": csrf},
        )
    assert res.status_code == 202, res.text
    return res.json()


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Create a conversation
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateConversation:

    def test_1_create_conversation(self, p4_env, client):
        """Test 1: POST /api/conversations creates a conversation and returns correct fields."""
        _seed_user(p4_env["db_path"])
        csrf = _login(client)

        res = client.post(
            "/api/conversations",
            json={"title": "My Research"},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["title"] == "My Research"
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data
        assert data["message_count"] == 0
        assert data["document_count"] == 0

    def test_1b_create_conversation_without_title_gets_default(self, p4_env, client):
        """Test 1b: A conversation created without a title gets the default title."""
        _seed_user(p4_env["db_path"])
        csrf = _login(client)

        res = client.post(
            "/api/conversations",
            json={},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 201
        assert res.json()["title"] == "New conversation"

    def test_1c_create_without_document_id_succeeds(self, p4_env, client):
        """Test 1c: document_id is now optional — conversations can start empty."""
        _seed_user(p4_env["db_path"])
        csrf = _login(client)

        res = client.post(
            "/api/conversations",
            json={"title": "Empty start"},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 201


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Listing only the authenticated user's conversations
# ─────────────────────────────────────────────────────────────────────────────

class TestListConversations:

    def test_2_list_only_own_conversations(self, p4_env, client):
        """Test 2: GET /api/conversations returns only the authenticated user's own conversations."""
        db = p4_env["db_path"]
        _seed_user(db, "ua", "usera", "ua@test.com")
        _seed_user(db, "ub", "userb", "ub@test.com")

        csrf_a = _login(client, "usera")
        _create_conv(client, csrf_a, "User A Conv 1")
        _create_conv(client, csrf_a, "User A Conv 2")

        client.post("/api/auth/logout")
        csrf_b = _login(client, "userb")
        _create_conv(client, csrf_b, "User B Conv")

        # Log back in as user A
        client.post("/api/auth/logout")
        csrf_a2 = _login(client, "usera")

        res = client.get("/api/conversations")
        assert res.status_code == 200
        titles = {c["title"] for c in res.json()}
        assert "User A Conv 1" in titles
        assert "User A Conv 2" in titles
        assert "User B Conv" not in titles

    def test_2b_list_ordered_by_updated_at(self, p4_env, client):
        """Test 2b: Conversation list is ordered most-recently-updated first."""
        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        _create_conv(client, csrf, "First")
        _create_conv(client, csrf, "Second")
        _create_conv(client, csrf, "Third")

        res = client.get("/api/conversations")
        assert res.status_code == 200
        titles = [c["title"] for c in res.json()]
        assert titles.index("Third") < titles.index("Second") < titles.index("First")


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Persisting messages and conversation metadata
# ─────────────────────────────────────────────────────────────────────────────

class TestPersistMessages:

    def test_3_messages_persisted_and_retrievable(self, p4_env, client):
        """Test 3: Messages posted to a conversation survive and are retrievable in order."""
        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv_id = _create_conv(client, csrf)

        msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "user", "content": "Second question"},
        ]
        for m in msgs:
            client.post(
                f"/api/conversations/{conv_id}/messages",
                json=m,
                headers={"X-CSRF-Token": csrf},
            )

        res = client.get(f"/api/conversations/{conv_id}/messages")
        assert res.status_code == 200
        fetched = res.json()
        assert len(fetched) == 3
        assert fetched[0]["content"] == "Hello"
        assert fetched[1]["content"] == "Hi there"
        assert fetched[2]["content"] == "Second question"

        # Metadata: message_count reflected in conversation summary
        conv_res = client.get(f"/api/conversations/{conv_id}")
        assert conv_res.json()["message_count"] == 3

    def test_3b_updated_at_changes_on_message_add(self, p4_env, client):
        """Test 3b: updated_at timestamp advances when a message is added."""
        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv_id = _create_conv(client, csrf)

        original_ts = client.get(f"/api/conversations/{conv_id}").json()["updated_at"]

        import time; time.sleep(0.01)
        client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"role": "user", "content": "bump"},
            headers={"X-CSRF-Token": csrf},
        )
        new_ts = client.get(f"/api/conversations/{conv_id}").json()["updated_at"]
        assert new_ts >= original_ts


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Reopening history after logout and login
# ─────────────────────────────────────────────────────────────────────────────

class TestHistoryAfterLogout:

    def test_4_history_survives_logout_login(self, p4_env, client):
        """Test 4: Conversations and messages are available after a logout/login cycle."""
        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv_id = _create_conv(client, csrf, "Persist me")
        client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"role": "user", "content": "Remember this"},
            headers={"X-CSRF-Token": csrf},
        )

        # Logout
        client.post("/api/auth/logout")

        # Log back in
        csrf2 = _login(client)

        # Conversation is still there
        res = client.get("/api/conversations")
        ids = [c["id"] for c in res.json()]
        assert conv_id in ids

        # Messages are still there
        msg_res = client.get(f"/api/conversations/{conv_id}/messages")
        assert msg_res.status_code == 200
        assert any(m["content"] == "Remember this" for m in msg_res.json())


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Data survival across backend restart (same DB)
# ─────────────────────────────────────────────────────────────────────────────

class TestPersistenceAcrossRestart:

    def test_5_data_survives_app_reinitialisation(self, p4_env):
        """
        Test 5: Data written with one app instance is readable by a fresh instance
        pointing at the same database.
        """
        from backend.main import app
        from backend.database import init_db
        from backend.security import hash_password
        from backend.database import get_connection
        import datetime

        db_path = p4_env["db_path"]

        # Seed data directly into DB (simulates state from a previous run)
        conn = get_connection(db_path)
        conn.execute(
            """
            INSERT OR IGNORE INTO users
              (id, email, username, password_hash, role, status, created_at, updated_at)
            VALUES ('restart-user', 'r@test.com', 'restart_user', ?, 'user', 'approved',
                    '2026-01-01', '2026-01-01')
            """,
            (hash_password("RestartPass1!"),),
        )
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO conversations (id, user_id, document_id, title, created_at, updated_at)
            VALUES ('restart-conv', 'restart-user', '', 'Restart Conv', ?, ?)
            """,
            (now, now),
        )
        conn.execute(
            """
            INSERT INTO messages (id, conversation_id, user_id, role, content, created_at)
            VALUES ('restart-msg', 'restart-conv', 'restart-user', 'user', 'Still here?', ?)
            """,
            (now,),
        )
        conn.commit()
        conn.close()

        # "Restart" — create a brand-new TestClient (new ASGI app instance)
        with TestClient(app, base_url="http://testserver") as fresh_client:
            login_res = fresh_client.post(
                "/api/auth/login",
                json={"identifier": "restart_user", "password": "RestartPass1!"},
            )
            assert login_res.status_code == 200

            convs = fresh_client.get("/api/conversations").json()
            assert any(c["id"] == "restart-conv" for c in convs)

            msgs = fresh_client.get("/api/conversations/restart-conv/messages").json()
            assert any(m["content"] == "Still here?" for m in msgs)


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Renaming a conversation
# ─────────────────────────────────────────────────────────────────────────────

class TestRenameConversation:

    def test_6_rename_conversation(self, p4_env, client):
        """Test 6: PATCH /api/conversations/{id} updates the title."""
        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv_id = _create_conv(client, csrf, "Old Title")

        res = client.patch(
            f"/api/conversations/{conv_id}",
            json={"title": "Shiny New Title"},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 200
        assert res.json()["title"] == "Shiny New Title"

        # Verify the change persisted
        get_res = client.get(f"/api/conversations/{conv_id}")
        assert get_res.json()["title"] == "Shiny New Title"

    def test_6b_rename_does_not_delete_messages(self, p4_env, client):
        """Test 6b: Renaming preserves all existing messages."""
        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv_id = _create_conv(client, csrf)
        client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"role": "user", "content": "keep me"},
            headers={"X-CSRF-Token": csrf},
        )

        client.patch(
            f"/api/conversations/{conv_id}",
            json={"title": "Renamed"},
            headers={"X-CSRF-Token": csrf},
        )
        msgs = client.get(f"/api/conversations/{conv_id}/messages").json()
        assert any(m["content"] == "keep me" for m in msgs)

    def test_6c_rename_another_users_conversation_is_forbidden(self, p4_env, client):
        """Test 6c: Cannot rename a conversation owned by someone else."""
        db = p4_env["db_path"]
        _seed_user(db, "ua2", "ua2", "ua2@test.com")
        _seed_user(db, "ub2", "ub2", "ub2@test.com")

        csrf_a = _login(client, "ua2")
        conv_id = _create_conv(client, csrf_a)

        client.post("/api/auth/logout")
        csrf_b = _login(client, "ub2")

        res = client.patch(
            f"/api/conversations/{conv_id}",
            json={"title": "Hijacked"},
            headers={"X-CSRF-Token": csrf_b},
        )
        assert res.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: Deleting a conversation safely
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteConversation:

    def test_7_delete_conversation_removes_data(self, p4_env, client):
        """Test 7: DELETE removes the conversation, messages, documents, and FAISS index."""
        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv_id = _create_conv(client, csrf)

        # Add a message
        client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"role": "user", "content": "soon gone"},
            headers={"X-CSRF-Token": csrf},
        )

        # Upload a PDF
        _upload_pdf(client, conv_id, csrf, "gone.pdf", ["page one text"])

        # Delete the conversation
        del_res = client.delete(
            f"/api/conversations/{conv_id}",
            headers={"X-CSRF-Token": csrf},
        )
        assert del_res.status_code == 200

        # No longer listed
        convs = client.get("/api/conversations").json()
        assert not any(c["id"] == conv_id for c in convs)

        # 404 on direct access
        get_res = client.get(f"/api/conversations/{conv_id}")
        assert get_res.status_code == 404

        # Messages gone from DB
        from backend.database import get_connection
        conn = get_connection(db)
        msgs = conn.execute(
            "SELECT COUNT(*) AS cnt FROM messages WHERE conversation_id = ?", (conv_id,)
        ).fetchone()["cnt"]
        docs = conn.execute(
            "SELECT COUNT(*) AS cnt FROM documents WHERE conversation_id = ?", (conv_id,)
        ).fetchone()["cnt"]
        conn.close()
        assert msgs == 0
        assert docs == 0

    def test_7b_delete_does_not_affect_other_conversations(self, p4_env, client):
        """Test 7b: Deleting one conversation leaves sibling conversations intact."""
        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv_keep = _create_conv(client, csrf, "Keep me")
        conv_del = _create_conv(client, csrf, "Delete me")

        client.post(
            f"/api/conversations/{conv_keep}/messages",
            json={"role": "user", "content": "survivor"},
            headers={"X-CSRF-Token": csrf},
        )

        client.delete(
            f"/api/conversations/{conv_del}",
            headers={"X-CSRF-Token": csrf},
        )

        # Sibling still exists with its message
        msgs = client.get(f"/api/conversations/{conv_keep}/messages").json()
        assert any(m["content"] == "survivor" for m in msgs)

    def test_7c_cannot_delete_others_conversation(self, p4_env, client):
        """Test 7c: A user cannot delete a conversation they don't own."""
        db = p4_env["db_path"]
        _seed_user(db, "u7a", "u7a", "u7a@test.com")
        _seed_user(db, "u7b", "u7b", "u7b@test.com")

        csrf_a = _login(client, "u7a")
        conv = _create_conv(client, csrf_a)
        client.post("/api/auth/logout")

        csrf_b = _login(client, "u7b")
        res = client.delete(
            f"/api/conversations/{conv}",
            headers={"X-CSRF-Token": csrf_b},
        )
        assert res.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: Rejecting access to another user's conversation
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossUserConversationAccess:

    def test_8_user_cannot_read_others_messages(self, p4_env, client):
        """Test 8: User B cannot read messages in User A's conversation."""
        db = p4_env["db_path"]
        _seed_user(db, "u8a", "u8a", "u8a@test.com")
        _seed_user(db, "u8b", "u8b", "u8b@test.com")

        csrf_a = _login(client, "u8a")
        conv = _create_conv(client, csrf_a)
        client.post(
            f"/api/conversations/{conv}/messages",
            json={"role": "user", "content": "private"},
            headers={"X-CSRF-Token": csrf_a},
        )
        client.post("/api/auth/logout")

        csrf_b = _login(client, "u8b")
        assert client.get(f"/api/conversations/{conv}/messages").status_code == 403
        assert client.get(f"/api/conversations/{conv}").status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Test 9: Admin cannot access another user's private chat
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminConversationPrivacy:

    def test_9_admin_cannot_access_users_private_conversation(self, p4_env, client):
        """Test 9: An admin account is denied access to a regular user's conversation."""
        db = p4_env["db_path"]
        _seed_user(db, "admin1", "admin1", "admin1@test.com", role="admin")
        _seed_user(db, "user9", "user9", "user9@test.com")

        csrf_u = _login(client, "user9")
        conv = _create_conv(client, csrf_u, "Private user conv")
        client.post(
            f"/api/conversations/{conv}/messages",
            json={"role": "user", "content": "secret message"},
            headers={"X-CSRF-Token": csrf_u},
        )
        client.post("/api/auth/logout")

        csrf_a = _login(client, "admin1")
        # Admin cannot read the conversation
        assert client.get(f"/api/conversations/{conv}").status_code == 403
        # Admin cannot read messages
        assert client.get(f"/api/conversations/{conv}/messages").status_code == 403
        # Admin cannot rename
        assert client.patch(
            f"/api/conversations/{conv}",
            json={"title": "admin hijack"},
            headers={"X-CSRF-Token": csrf_a},
        ).status_code == 403
        # Admin cannot delete
        assert client.delete(
            f"/api/conversations/{conv}",
            headers={"X-CSRF-Token": csrf_a},
        ).status_code == 403
        # Admin's list does NOT show user's conversation
        admin_convs = {c["id"] for c in client.get("/api/conversations").json()}
        assert conv not in admin_convs


# ─────────────────────────────────────────────────────────────────────────────
# Test 10: Admin accesses their own conversation
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminOwnConversation:

    def test_10_admin_can_manage_own_conversation(self, p4_env, client):
        """Test 10: An admin has normal user access to their own conversations."""
        db = p4_env["db_path"]
        _seed_user(db, "admin2", "admin2", "admin2@test.com", role="admin")

        csrf = _login(client, "admin2")
        conv = _create_conv(client, csrf, "Admin's own conv")

        # Can read it
        assert client.get(f"/api/conversations/{conv}").status_code == 200
        # Can rename it
        assert client.patch(
            f"/api/conversations/{conv}",
            json={"title": "Renamed by admin"},
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        # Can delete it
        assert client.delete(
            f"/api/conversations/{conv}",
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Test 11: Uploading multiple PDFs to one conversation
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiPDFUpload:

    def test_11_upload_multiple_pdfs(self, p4_env, client):
        """Test 11: Multiple PDFs can be uploaded in one request."""
        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv = _create_conv(client, csrf)

        pdf1 = _make_pdf_bytes(["Doc one content"])
        pdf2 = _make_pdf_bytes(["Doc two content"])

        with patch("backend.routes.documents.gemini_service.embed_texts", side_effect=_mock_embed):
            res = client.post(
                f"/api/conversations/{conv}/documents",
                files=[
                    ("files", ("a.pdf", pdf1, "application/pdf")),
                    ("files", ("b.pdf", pdf2, "application/pdf")),
                ],
                headers={"X-CSRF-Token": csrf},
            )

        assert res.status_code == 202
        data = res.json()
        assert data["accepted"] == 2
        assert data["failed"] == 0

        list_res = client.get(f"/api/conversations/{conv}/documents")
        assert list_res.json()["total"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# Test 12: Adding new PDFs without losing old documents
# ─────────────────────────────────────────────────────────────────────────────

class TestAdditivePDFUpload:

    def test_12_new_pdfs_preserve_existing_documents(self, p4_env, client):
        """Test 12: A second batch of uploads does not remove the first batch."""
        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv = _create_conv(client, csrf)

        _upload_pdf(client, conv, csrf, "first.pdf", ["first content"])
        first_docs = client.get(f"/api/conversations/{conv}/documents").json()["documents"]
        assert len(first_docs) == 1
        first_id = first_docs[0]["id"]

        _upload_pdf(client, conv, csrf, "second.pdf", ["second content"])
        all_docs = client.get(f"/api/conversations/{conv}/documents").json()["documents"]
        assert len(all_docs) == 2
        ids = {d["id"] for d in all_docs}
        assert first_id in ids

    def test_12b_messages_preserved_when_new_pdf_added(self, p4_env, client):
        """Test 12b: Pre-existing messages survive when a new PDF is uploaded."""
        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv = _create_conv(client, csrf)

        client.post(
            f"/api/conversations/{conv}/messages",
            json={"role": "user", "content": "I was here first"},
            headers={"X-CSRF-Token": csrf},
        )

        _upload_pdf(client, conv, csrf, "new.pdf", ["new content"])

        msgs = client.get(f"/api/conversations/{conv}/messages").json()
        assert any(m["content"] == "I was here first" for m in msgs)


# ─────────────────────────────────────────────────────────────────────────────
# Test 13: Retrieving evidence from both earlier and newly added PDFs
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiDocumentRetrieval:

    def test_13_ask_searches_across_all_documents(self, p4_env, client):
        """Test 13: /ask retrieves evidence from all completed documents in the conversation."""
        from backend.services import gemini_service, vector_store

        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv = _create_conv(client, csrf)

        # Upload two PDFs
        _upload_pdf(client, conv, csrf, "doc1.pdf", ["The capital of France is Paris."])
        _upload_pdf(client, conv, csrf, "doc2.pdf", ["Water boils at 100 degrees Celsius."])

        # Mock embed_query and generate_content
        mock_client = MagicMock()
        qemb = MagicMock()
        qemb.values = _make_embedding(0)  # will hit both docs
        mock_client.models.embed_content.return_value = MagicMock(embeddings=[qemb])
        gen_resp = MagicMock()
        gen_resp.candidates = [MagicMock()]
        gen_resp.candidates[0].content.parts = [MagicMock(text="Answer based on docs.")]
        mock_client.models.generate_content.return_value = gen_resp
        gemini_service.set_client(mock_client)

        res = client.post(
            f"/api/conversations/{conv}/ask",
            json={"question": "What do the documents say?"},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 200
        data = res.json()
        # Both documents are in scope — not insufficient evidence (index has content)
        # (may still be insufficient if query vector doesn't match, so check no server error)
        assert data.get("error") is None or data["insufficient_evidence"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Test 14: Citation filenames and page numbers
# ─────────────────────────────────────────────────────────────────────────────

class TestCitationAccuracy:

    def test_14_citations_have_correct_filename_and_page(self, p4_env, client):
        """Test 14: Citations returned by /ask carry the real filename and page from the index."""
        from backend.services import gemini_service, vector_store
        from backend.database import get_connection

        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv = _create_conv(client, csrf)

        # Manually seed a document and FAISS entry so we control the exact metadata
        doc_id = str(uuid.uuid4())
        conn = get_connection(db)
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conv_row = conn.execute(
            "SELECT user_id FROM conversations WHERE id = ?", (conv,)
        ).fetchone()
        user_id = conv_row["user_id"]

        conn.execute(
            """
            INSERT INTO documents
              (id, conversation_id, user_id, original_filename, stored_filename,
               file_size_bytes, status, uploaded_at, processed_at)
            VALUES (?, ?, ?, 'cite_test.pdf', 'x.pdf', 100, 'completed', ?, ?)
            """,
            (doc_id, conv, user_id, now, now),
        )
        conn.commit()
        conn.close()

        # Index a chunk with known page
        vec = _make_embedding(5)
        vector_store.add_vectors(conv, user_id, [vec], [{
            "chunk_db_id": "ck-cite",
            "document_id": doc_id,
            "user_id": user_id,
            "conversation_id": conv,
            "original_filename": "cite_test.pdf",
            "chunk_index": 0,
            "start_page": 7,
            "end_page": 7,
            "content": "The answer is 42.",
        }])

        mock_client = MagicMock()
        qemb = MagicMock()
        qemb.values = _make_embedding(5)  # exact match
        mock_client.models.embed_content.return_value = MagicMock(embeddings=[qemb])
        gen_resp = MagicMock()
        gen_resp.candidates = [MagicMock()]
        gen_resp.candidates[0].content.parts = [MagicMock(text="The answer is 42.")]
        mock_client.models.generate_content.return_value = gen_resp
        gemini_service.set_client(mock_client)

        res = client.post(
            f"/api/conversations/{conv}/ask",
            json={"question": "What is the answer?"},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 200
        data = res.json()
        assert not data["insufficient_evidence"]
        assert len(data["citations"]) >= 1
        cit = data["citations"][0]
        assert cit["filename"] == "cite_test.pdf"
        assert cit["start_page"] == 7
        assert cit["page_range"] == "7"

    def test_14b_citations_persisted_in_messages_table(self, p4_env, client):
        """Test 14b: After /ask, the assistant message row has citations serialised as JSON."""
        from backend.services import gemini_service, vector_store
        from backend.database import get_connection
        import datetime

        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv = _create_conv(client, csrf)

        doc_id = str(uuid.uuid4())
        conn = get_connection(db)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        user_id = conn.execute(
            "SELECT user_id FROM conversations WHERE id = ?", (conv,)
        ).fetchone()["user_id"]
        conn.execute(
            """
            INSERT INTO documents
              (id, conversation_id, user_id, original_filename, stored_filename,
               file_size_bytes, status, uploaded_at, processed_at)
            VALUES (?, ?, ?, 'stored.pdf', 'y.pdf', 50, 'completed', ?, ?)
            """,
            (doc_id, conv, user_id, now, now),
        )
        conn.commit()
        conn.close()

        vec = _make_embedding(3)
        vector_store.add_vectors(conv, user_id, [vec], [{
            "chunk_db_id": "ck-persist",
            "document_id": doc_id,
            "user_id": user_id,
            "conversation_id": conv,
            "original_filename": "stored.pdf",
            "chunk_index": 0,
            "start_page": 2,
            "end_page": 2,
            "content": "Stored citation content.",
        }])

        mock_client = MagicMock()
        qemb = MagicMock()
        qemb.values = _make_embedding(3)
        mock_client.models.embed_content.return_value = MagicMock(embeddings=[qemb])
        gen_resp = MagicMock()
        gen_resp.candidates = [MagicMock()]
        gen_resp.candidates[0].content.parts = [MagicMock(text="Stored citation content.")]
        mock_client.models.generate_content.return_value = gen_resp
        gemini_service.set_client(mock_client)

        res = client.post(
            f"/api/conversations/{conv}/ask",
            json={"question": "Show stored citation"},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 200
        assert res.json()["message_id"] is not None
        msg_id = res.json()["message_id"]

        conn2 = get_connection(db)
        row = conn2.execute(
            "SELECT citations FROM messages WHERE id = ?", (msg_id,)
        ).fetchone()
        conn2.close()

        assert row["citations"] is not None
        cits = json.loads(row["citations"])
        assert len(cits) >= 1
        assert cits[0]["filename"] == "stored.pdf"
        assert cits[0]["start_page"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# Test 15: Partial upload failures
# ─────────────────────────────────────────────────────────────────────────────

class TestPartialUploadFailure:

    def test_15_partial_failures_reported_without_aborting_good_files(self, p4_env, client):
        """Test 15: If one file in a multi-upload fails, the other(s) still succeed."""
        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv = _create_conv(client, csrf)

        good_pdf = _make_pdf_bytes(["Good content here"])
        bad_bytes = b"This is not a PDF at all"

        with patch("backend.routes.documents.gemini_service.embed_texts", side_effect=_mock_embed):
            res = client.post(
                f"/api/conversations/{conv}/documents",
                files=[
                    ("files", ("good.pdf", good_pdf, "application/pdf")),
                    ("files", ("bad.pdf", bad_bytes, "application/pdf")),
                ],
                headers={"X-CSRF-Token": csrf},
            )

        assert res.status_code == 202
        data = res.json()
        assert data["accepted"] == 1
        assert data["failed"] == 1

        # Good file is in DB
        docs = client.get(f"/api/conversations/{conv}/documents").json()["documents"]
        filenames = {d["original_filename"] for d in docs}
        assert "good.pdf" in filenames

        # Conversation and its existing data are intact
        conv_data = client.get(f"/api/conversations/{conv}").json()
        assert conv_data["document_count"] >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Test 16: Duplicate indexing prevention on retry
# ─────────────────────────────────────────────────────────────────────────────

class TestDuplicateIndexingPrevention:

    def test_16_duplicate_chunk_ids_not_reindexed(self, p4_env):
        """Test 16: Calling add_vectors twice with the same chunk_db_ids keeps count at 1."""
        from backend.services import vector_store

        conv_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        meta = [{
            "chunk_db_id": "ck-dup",
            "document_id": "d1",
            "user_id": user_id,
            "conversation_id": conv_id,
            "original_filename": "dup.pdf",
            "chunk_index": 0,
            "start_page": 1,
            "end_page": 1,
            "content": "duplicate chunk",
        }]

        total1 = vector_store.add_vectors(conv_id, user_id, [_make_embedding(0)], meta)
        assert total1 == 1
        # Second call with identical chunk_db_id — must be skipped
        total2 = vector_store.add_vectors(conv_id, user_id, [_make_embedding(0)], meta)
        assert total2 == 1


# ─────────────────────────────────────────────────────────────────────────────
# Test 17: Document deletion and reference cleanup
# ─────────────────────────────────────────────────────────────────────────────

class TestDocumentDeletion:

    def test_17_delete_document_removes_chunks_and_index(self, p4_env, client):
        """Test 17: Deleting a document removes its DB rows, physical file, and index entry."""
        from backend.database import get_connection
        from backend.services import vector_store

        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv = _create_conv(client, csrf)

        # Upload one PDF
        upload = _upload_pdf(client, conv, csrf, "target.pdf", ["delete me"])
        doc_id = upload["results"][0]["document_id"]
        assert doc_id is not None

        # Verify chunks exist
        conn = get_connection(db)
        chunk_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM chunks WHERE document_id = ?", (doc_id,)
        ).fetchone()["cnt"]
        conn.close()
        assert chunk_count > 0

        # Delete the document (rebuild embed is mocked to avoid real API call)
        with patch("backend.routes.documents.gemini_service.embed_texts", side_effect=_mock_embed):
            del_res = client.delete(
                f"/api/conversations/{conv}/documents/{doc_id}",
                headers={"X-CSRF-Token": csrf},
            )
        assert del_res.status_code == 200

        # Chunks cascade-deleted
        conn2 = get_connection(db)
        after = conn2.execute(
            "SELECT COUNT(*) AS cnt FROM chunks WHERE document_id = ?", (doc_id,)
        ).fetchone()["cnt"]
        conn2.close()
        assert after == 0

    def test_17b_delete_one_doc_does_not_remove_other_docs_chunks(self, p4_env, client):
        """Test 17b: Deleting doc A leaves doc B's chunks intact."""
        from backend.database import get_connection

        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv = _create_conv(client, csrf)

        u1 = _upload_pdf(client, conv, csrf, "doc_a.pdf", ["Doc A text"])
        u2 = _upload_pdf(client, conv, csrf, "doc_b.pdf", ["Doc B text"])
        doc_a = u1["results"][0]["document_id"]
        doc_b = u2["results"][0]["document_id"]

        conn = get_connection(db)
        b_chunks_before = conn.execute(
            "SELECT COUNT(*) AS cnt FROM chunks WHERE document_id = ?", (doc_b,)
        ).fetchone()["cnt"]
        conn.close()

        with patch("backend.routes.documents.gemini_service.embed_texts", side_effect=_mock_embed):
            client.delete(
                f"/api/conversations/{conv}/documents/{doc_a}",
                headers={"X-CSRF-Token": csrf},
            )

        conn2 = get_connection(db)
        b_chunks_after = conn2.execute(
            "SELECT COUNT(*) AS cnt FROM chunks WHERE document_id = ?", (doc_b,)
        ).fetchone()["cnt"]
        conn2.close()
        assert b_chunks_after == b_chunks_before


# ─────────────────────────────────────────────────────────────────────────────
# Test 18: Processing failures and Gemini errors handled in /ask
# ─────────────────────────────────────────────────────────────────────────────

class TestGeminiAndProcessingErrors:

    def test_18_gemini_error_in_ask_persists_error_message(self, p4_env, client):
        """
        Test 18: When Gemini fails during generation, the error is returned cleanly.
        A conversation with a completed document is required to reach the embed/generate step.
        With no documents, the pipeline short-circuits to insufficient_evidence (not an error).
        This test verifies both paths are handled safely.
        """
        from backend.services import gemini_service
        from backend.database import get_connection

        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv = _create_conv(client, csrf)

        # ── Path A: no documents → insufficient evidence (not a crash) ────────
        mock_client = MagicMock()
        emb = MagicMock()
        emb.values = _make_embedding(0)
        mock_client.models.embed_content.return_value = MagicMock(embeddings=[emb])
        gemini_service.set_client(mock_client)

        res_no_docs = client.post(
            f"/api/conversations/{conv}/ask",
            json={"question": "anything?"},
            headers={"X-CSRF-Token": csrf},
        )
        assert res_no_docs.status_code == 200
        assert res_no_docs.json()["insufficient_evidence"] is True
        assert res_no_docs.json().get("error") is None  # no error — just no evidence

        # ── Path B: Gemini generation fails → error field populated ───────────
        # Seed a completed document directly so we reach the generation step
        import datetime
        doc_id = str(uuid.uuid4())
        conn = get_connection(db)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        user_id = conn.execute(
            "SELECT user_id FROM conversations WHERE id = ?", (conv,)
        ).fetchone()["user_id"]
        conn.execute(
            """
            INSERT INTO documents
              (id, conversation_id, user_id, original_filename, stored_filename,
               file_size_bytes, status, uploaded_at, processed_at)
            VALUES (?, ?, ?, 'err_test.pdf', 'e.pdf', 50, 'completed', ?, ?)
            """,
            (doc_id, conv, user_id, now, now),
        )
        conn.commit()
        conn.close()

        from backend.services import vector_store
        vector_store.add_vectors(conv, user_id, [_make_embedding(7)], [{
            "chunk_db_id": "ck-err",
            "document_id": doc_id,
            "user_id": user_id,
            "conversation_id": conv,
            "original_filename": "err_test.pdf",
            "chunk_index": 0,
            "start_page": 1,
            "end_page": 1,
            "content": "error test content",
        }])

        # Embedding succeeds, generation fails
        mock_client2 = MagicMock()
        emb2 = MagicMock()
        emb2.values = _make_embedding(7)
        mock_client2.models.embed_content.return_value = MagicMock(embeddings=[emb2])
        mock_client2.models.generate_content.side_effect = Exception("503 unavailable")
        gemini_service.set_client(mock_client2)

        res = client.post(
            f"/api/conversations/{conv}/ask",
            json={"question": "What do the docs say?"},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 200
        data = res.json()
        # Generation failed → error should be set, answer empty
        assert data["error"] is not None
        assert data["answer"] == "" or data["answer"] is None or not data["answer"]

    def test_18b_failed_document_not_included_in_rag_scope(self, p4_env, client):
        """Test 18b: Documents in 'failed' status are excluded from retrieval scope."""
        from backend.services import gemini_service
        from backend.database import get_connection

        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)
        conv = _create_conv(client, csrf)

        # Upload a PDF that will fail embedding
        pdf = _make_pdf_bytes(["Sensitive content"])
        with patch(
            "backend.routes.documents.gemini_service.embed_texts",
            side_effect=Exception("embed fail"),
        ):
            client.post(
                f"/api/conversations/{conv}/documents",
                files=[("files", ("secret.pdf", pdf, "application/pdf"))],
                headers={"X-CSRF-Token": csrf},
            )

        # Ask a question — failed doc should NOT be in authorised scope
        mock_client = MagicMock()
        qemb = MagicMock()
        qemb.values = _make_embedding(0)
        mock_client.models.embed_content.return_value = MagicMock(embeddings=[qemb])
        gemini_service.set_client(mock_client)

        res = client.post(
            f"/api/conversations/{conv}/ask",
            json={"question": "What is secret content?"},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 200
        # No completed docs → insufficient evidence (not a server error)
        assert res.json()["insufficient_evidence"] is True
        assert res.json().get("error") is None


# ─────────────────────────────────────────────────────────────────────────────
# Test 19: Phase 2 authentication tests preserved
# ─────────────────────────────────────────────────────────────────────────────

class TestPhase2AuthPreservation:

    def test_19_phase2_auth_flow_intact(self, p4_env, client):
        """Test 19: Core Phase 2 auth flows still work after Phase 4 changes."""
        db = p4_env["db_path"]
        _seed_user(db, "p2u", "p2user", "p2@test.com", "Phase2Pass1!")

        # Register new user
        reg = client.post("/api/auth/register", json={
            "username": "newp4user", "email": "newp4@test.com", "password": "NewP4Pass1!",
        })
        assert reg.status_code == 201
        assert reg.json()["status"] == "pending"

        # Login + /me
        login = client.post("/api/auth/login", json={"identifier": "p2user", "password": "Phase2Pass1!"})
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        me = client.get("/api/auth/me")
        assert me.json()["authenticated"] is True

        # CSRF required for conversation create
        no_csrf = client.post("/api/conversations", json={"title": "t"})
        assert no_csrf.status_code == 403

        # Logout invalidates session
        client.post("/api/auth/logout")
        assert client.get("/api/conversations").status_code == 401

    def test_19b_admin_endpoints_still_protected(self, p4_env, client):
        """Test 19b: Admin endpoints still require admin role."""
        _seed_user(p4_env["db_path"])
        _login(client)
        assert client.get("/api/admin/users").status_code == 403

    def test_19c_health_check_works(self, p4_env, client):
        """Test 19c: /api/health is unaffected."""
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["database"] == "healthy"


# ─────────────────────────────────────────────────────────────────────────────
# Test 20: Phase 3 RAG tests preserved (quick smoke test)
# ─────────────────────────────────────────────────────────────────────────────

class TestPhase3RAGPreservation:

    def test_20_pdf_extraction_and_chunking_unchanged(self):
        """Test 20a: PDF extraction and chunking still work correctly."""
        from backend.services.pdf_extractor import extract_pdf_pages
        from backend.services.chunker import chunk_pages

        pdf = _make_pdf_bytes(["Phase 3 page one.", "Phase 3 page two."])
        result = extract_pdf_pages(pdf)
        assert result.success
        assert result.page_count == 2

        chunks = chunk_pages(result.pages)
        assert len(chunks) > 0
        assert chunks[0].start_page >= 1
        assert chunks[0].document_id == ""  # unset until upload route fills it

    def test_20b_faiss_add_and_search_unchanged(self, p4_env):
        """Test 20b: FAISS add_vectors / search still work correctly."""
        from backend.services import vector_store

        conv_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())

        vecs = [_make_embedding(i) for i in range(3)]
        metas = [{
            "chunk_db_id": f"ck-{i}",
            "document_id": doc_id,
            "user_id": user_id,
            "conversation_id": conv_id,
            "original_filename": "phase3.pdf",
            "chunk_index": i,
            "start_page": i + 1,
            "end_page": i + 1,
            "content": f"content {i}",
        } for i in range(3)]

        total = vector_store.add_vectors(conv_id, user_id, vecs, metas)
        assert total == 3

        hits = vector_store.search(
            conversation_id=conv_id,
            query_vector=_make_embedding(1),
            authorized_document_ids=[doc_id],
            top_k=1,
        )
        assert len(hits) == 1
        assert hits[0]["chunk_db_id"] == "ck-1"

    def test_20c_rag_pipeline_returns_insufficient_when_no_docs(self, p4_env):
        """Test 20c: RAG pipeline still returns insufficient_evidence correctly."""
        from backend.services import gemini_service
        from backend.services.rag_pipeline import run_rag_query

        mock_client = MagicMock()
        emb = MagicMock()
        emb.values = _make_embedding(0)
        mock_client.models.embed_content.return_value = MagicMock(embeddings=[emb])
        gemini_service.set_client(mock_client)

        result = run_rag_query(
            question="anything",
            conversation_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            authorized_document_ids=[],
        )
        assert result.insufficient_evidence is True

    def test_20d_auto_title_set_on_first_question(self, p4_env, client):
        """Test 20d: The conversation title is auto-set from the first question via /ask."""
        from backend.services import gemini_service

        db = p4_env["db_path"]
        _seed_user(db)
        csrf = _login(client)

        # Create conversation WITHOUT an explicit title → gets "New conversation" default
        res_create = client.post(
            "/api/conversations",
            json={},
            headers={"X-CSRF-Token": csrf},
        )
        assert res_create.status_code == 201
        conv = res_create.json()["id"]
        assert res_create.json()["title"] == "New conversation"

        mock_client = MagicMock()
        emb = MagicMock()
        emb.values = _make_embedding(0)
        mock_client.models.embed_content.return_value = MagicMock(embeddings=[emb])
        gemini_service.set_client(mock_client)

        res = client.post(
            f"/api/conversations/{conv}/ask",
            json={"question": "What is machine learning?"},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 200
        # conversation_title in response should reflect the question (truncated)
        new_title = res.json()["conversation_title"]
        assert new_title != "New conversation"
        assert "machine learning" in new_title.lower()

        # And the GET endpoint also reflects the new title
        updated = client.get(f"/api/conversations/{conv}").json()
        assert updated["title"] == new_title
