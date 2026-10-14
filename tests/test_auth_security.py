import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import init_db, get_connection
from backend.cli import create_initial_admin
from backend.security import hash_password, reset_rate_limits

@pytest.fixture(scope="function")
def test_env():
    """Create an isolated temporary SQLite database for tests."""
    reset_rate_limits()
    temp_dir = tempfile.TemporaryDirectory()
    temp_db_path = os.path.join(temp_dir.name, "test_documind.db")
    os.environ["DOCUMIND_DB_PATH"] = temp_db_path
    
    # Initialize schema
    init_db(temp_db_path)
    
    yield temp_db_path
    
    reset_rate_limits()
    temp_dir.cleanup()

@pytest.fixture(scope="function")
def client(test_env):
    """Test client bound to isolated test environment."""
    with TestClient(app, base_url="http://testserver") as c:
        yield c

def test_1_login_with_valid_credentials(test_env, client):
    """Test 1: Login with valid credentials returns session and profile."""
    conn = get_connection(test_env)
    pw_hash = hash_password("ValidPassword123!")
    conn.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
        VALUES ('u1', 'user1@example.com', 'user1', ?, 'user', 'approved', '2026-01-01', '2026-01-01')
        """,
        (pw_hash,)
    )
    conn.commit()
    conn.close()

    res = client.post("/api/auth/login", json={"identifier": "user1", "password": "ValidPassword123!"})
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["username"] == "user1"
    assert data["user"]["role"] == "user"
    assert data["user"]["status"] == "approved"
    assert "session_token" in data
    assert "documind_session" in res.cookies

def test_2_login_with_invalid_credentials(test_env, client):
    """Test 2: Login with invalid password or non-existent user returns 401."""
    conn = get_connection(test_env)
    pw_hash = hash_password("CorrectPassword123!")
    conn.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
        VALUES ('u2', 'user2@example.com', 'user2', ?, 'user', 'approved', '2026-01-01', '2026-01-01')
        """,
        (pw_hash,)
    )
    conn.commit()
    conn.close()

    # Wrong password
    res = client.post("/api/auth/login", json={"identifier": "user2", "password": "WrongPassword999"})
    assert res.status_code == 401
    assert "Invalid username or password" in res.json()["detail"]

    # Non-existent user
    res2 = client.post("/api/auth/login", json={"identifier": "nonexistent", "password": "AnyPassword123"})
    assert res2.status_code == 401

def test_3_pending_account_restrictions(test_env, client):
    """Test 3: Pending user account cannot access protected resources."""
    conn = get_connection(test_env)
    pw_hash = hash_password("PendingPass123!")
    conn.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
        VALUES ('u-pending', 'pending@example.com', 'pending_user', ?, 'user', 'pending', '2026-01-01', '2026-01-01')
        """,
        (pw_hash,)
    )
    conn.commit()
    conn.close()

    # Login succeeds but status is pending
    login_res = client.post("/api/auth/login", json={"identifier": "pending_user", "password": "PendingPass123!"})
    assert login_res.status_code == 200
    assert login_res.json()["user"]["status"] == "pending"

    # Attempt to access protected conversation resource
    conv_res = client.get("/api/conversations")
    assert conv_res.status_code == 403
    assert "pending administrator approval" in conv_res.json()["detail"]

def test_4_rejected_account_restrictions(test_env, client):
    """Test 4: Rejected user account cannot log in or access resources."""
    conn = get_connection(test_env)
    pw_hash = hash_password("RejectedPass123!")
    conn.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
        VALUES ('u-rejected', 'rejected@example.com', 'rejected_user', ?, 'user', 'rejected', '2026-01-01', '2026-01-01')
        """,
        (pw_hash,)
    )
    conn.commit()
    conn.close()

    res = client.post("/api/auth/login", json={"identifier": "rejected_user", "password": "RejectedPass123!"})
    assert res.status_code == 403
    assert "rejected" in res.json()["detail"]

def test_5_deactivated_account_restrictions(test_env, client):
    """Test 5: Deactivated account cannot log in or access endpoints."""
    conn = get_connection(test_env)
    pw_hash = hash_password("DeactivatedPass123!")
    conn.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
        VALUES ('u-deact', 'deact@example.com', 'deact_user', ?, 'user', 'deactivated', '2026-01-01', '2026-01-01')
        """,
        (pw_hash,)
    )
    conn.commit()
    conn.close()

    res = client.post("/api/auth/login", json={"identifier": "deact_user", "password": "DeactivatedPass123!"})
    assert res.status_code == 403
    assert "deactivated" in res.json()["detail"]

def test_6_role_based_access_control(test_env, client):
    """Test 6: Regular approved user cannot access administrator endpoints."""
    conn = get_connection(test_env)
    pw_hash = hash_password("UserPass123!")
    conn.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
        VALUES ('u6', 'u6@example.com', 'regular_user', ?, 'user', 'approved', '2026-01-01', '2026-01-01')
        """,
        (pw_hash,)
    )
    conn.commit()
    conn.close()

    # Login as regular user
    client.post("/api/auth/login", json={"identifier": "regular_user", "password": "UserPass123!"})

    # Attempt to list users on admin endpoint
    admin_res = client.get("/api/admin/users")
    assert admin_res.status_code == 403
    assert "Administrator privileges required" in admin_res.json()["detail"]

def test_7_secure_first_administrator_provisioning(test_env):
    """Test 7: CLI creates initial admin; repeated bootstrap attempt is blocked."""
    # First provisioning succeeds
    success1 = create_initial_admin(
        username="primary_admin",
        email="admin@example.com",
        password="SecureAdminPassword2026!",
        db_path=test_env
    )
    assert success1 is True

    # Repeated bootstrap fails and protects system
    success2 = create_initial_admin(
        username="attacker_admin",
        email="attacker@example.com",
        password="AnotherPassword2026!",
        db_path=test_env
    )
    assert success2 is False

def test_8_logout_and_session_invalidation(test_env, client):
    """Test 8: Logout invalidates session on server so it can no longer be used."""
    conn = get_connection(test_env)
    pw_hash = hash_password("LogoutTestPass123!")
    conn.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
        VALUES ('u8', 'u8@example.com', 'logout_user', ?, 'user', 'approved', '2026-01-01', '2026-01-01')
        """,
        (pw_hash,)
    )
    conn.commit()
    conn.close()

    # Login
    login_res = client.post("/api/auth/login", json={"identifier": "logout_user", "password": "LogoutTestPass123!"})
    assert login_res.status_code == 200

    # User can access conversations
    assert client.get("/api/conversations").status_code == 200

    # Logout
    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 200

    # Request after logout is rejected with 401
    post_logout_res = client.get("/api/conversations")
    assert post_logout_res.status_code == 401

def test_9_session_expiration_and_csrf_protection(test_env, client):
    """Test 9: Expired session is rejected; state-changing requests validate CSRF."""
    conn = get_connection(test_env)
    pw_hash = hash_password("CsrfTestPass123!")
    conn.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
        VALUES ('u9', 'u9@example.com', 'csrf_user', ?, 'user', 'approved', '2026-01-01', '2026-01-01')
        """,
        (pw_hash,)
    )
    # Insert an already-expired session
    conn.execute(
        """
        INSERT INTO sessions (id, user_id, csrf_token, expires_at, created_at, is_active)
        VALUES ('expired_session_token', 'u9', 'valid_csrf_token', '2020-01-01T00:00:00Z', '2020-01-01T00:00:00Z', 1)
        """
    )
    conn.commit()
    conn.close()

    # Attempt to use expired session via Bearer header
    headers = {"Authorization": "Bearer expired_session_token"}
    res = client.get("/api/conversations", headers=headers)
    assert res.status_code == 401

    # Now login with valid session to test CSRF on state-changing POST
    login_res = client.post("/api/auth/login", json={"identifier": "csrf_user", "password": "CsrfTestPass123!"})
    csrf_token = login_res.json()["csrf_token"]

    # POST without CSRF token fails with 403
    post_no_csrf = client.post(
        "/api/conversations",
        json={"document_id": "doc1", "title": "Test Title"}
    )
    assert post_no_csrf.status_code == 403

    # POST with correct X-CSRF-Token header succeeds with 201
    post_with_csrf = client.post(
        "/api/conversations",
        json={"document_id": "doc1", "title": "Test Title"},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert post_with_csrf.status_code == 201

def test_10_unauthorized_access_to_admin_endpoints(test_env, client):
    """Test 10: Unauthenticated requests to admin endpoints return 401."""
    res = client.get("/api/admin/users")
    assert res.status_code == 401

    res2 = client.get("/api/admin/audit-logs")
    assert res2.status_code == 401

def test_11_attempts_to_manipulate_roles_through_registration(test_env, client):
    """Test 11: Registration ignores any role passed by client; always sets 'user' and 'pending'."""
    res = client.post(
        "/api/auth/register",
        json={
            "username": "sneaky_user",
            "email": "sneaky@example.com",
            "password": "StrongPassword123!",
            "role": "admin",
            "status": "approved"
        }
    )
    assert res.status_code == 201
    assert res.json()["status"] == "pending"

    # Verify directly in database that role is 'user' and status is 'pending'
    conn = get_connection(test_env)
    user = conn.execute("SELECT role, status FROM users WHERE username = 'sneaky_user'").fetchone()
    assert user["role"] == "user"
    assert user["status"] == "pending"
    conn.close()

def test_12_user_a_attempting_to_access_user_b_resource(test_env, client):
    """Test 12: User A attempting to access User B's conversation receives 403 Forbidden."""
    conn = get_connection(test_env)
    pw_hash_a = hash_password("UserPassA123!")
    pw_hash_b = hash_password("UserPassB123!")
    conn.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
        VALUES ('user-a', 'usera@example.com', 'user_a', ?, 'user', 'approved', '2026-01-01', '2026-01-01')
        """,
        (pw_hash_a,)
    )
    conn.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
        VALUES ('user-b', 'userb@example.com', 'user_b', ?, 'user', 'approved', '2026-01-01', '2026-01-01')
        """,
        (pw_hash_b,)
    )
    # User B creates a private conversation
    conn.execute(
        """
        INSERT INTO conversations (id, user_id, document_id, title, created_at, updated_at)
        VALUES ('conv-b', 'user-b', 'doc-quantum', 'User B Confidential Research', '2026-01-01', '2026-01-01')
        """
    )
    conn.commit()
    conn.close()

    # Login as User A
    login_a = client.post("/api/auth/login", json={"identifier": "user_a", "password": "UserPassA123!"})
    assert login_a.status_code == 200

    # User A tries to read User B's conversation
    res = client.get("/api/conversations/conv-b")
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]

def test_13_admin_attempting_to_retrieve_another_users_conversation(test_env, client):
    """Test 13: Administrator CANNOT access another user's conversation directly through the API."""
    conn = get_connection(test_env)
    pw_admin = hash_password("AdminPass123!")
    pw_user = hash_password("UserPass123!")
    conn.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
        VALUES ('admin-id', 'admin@example.com', 'admin_user', ?, 'admin', 'approved', '2026-01-01', '2026-01-01')
        """,
        (pw_admin,)
    )
    conn.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
        VALUES ('victim-id', 'victim@example.com', 'victim_user', ?, 'user', 'approved', '2026-01-01', '2026-01-01')
        """,
        (pw_user,)
    )
    conn.execute(
        """
        INSERT INTO conversations (id, user_id, document_id, title, created_at, updated_at)
        VALUES ('victim-conv', 'victim-id', 'doc-quantum', 'Victim Private Thoughts', '2026-01-01', '2026-01-01')
        """
    )
    conn.commit()
    conn.close()

    # Login as Administrator
    login_admin = client.post("/api/auth/login", json={"identifier": "admin_user", "password": "AdminPass123!"})
    assert login_admin.status_code == 200

    # Administrator attempts to fetch victim's conversation
    res = client.get("/api/conversations/victim-conv")
    # Must be 403 Forbidden! Administrator privileges do NOT bypass conversation privacy!
    assert res.status_code == 403
    assert "Access denied. You do not own this conversation." in res.json()["detail"]

def test_14_admin_accessing_their_own_conversation(test_env, client):
    """Test 14: Administrator CAN access their own conversations through standard user context."""
    conn = get_connection(test_env)
    pw_admin = hash_password("AdminPass123!")
    conn.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
        VALUES ('admin-own', 'adminown@example.com', 'admin_own', ?, 'admin', 'approved', '2026-01-01', '2026-01-01')
        """,
        (pw_admin,)
    )
    conn.execute(
        """
        INSERT INTO conversations (id, user_id, document_id, title, created_at, updated_at)
        VALUES ('admin-conv-1', 'admin-own', 'doc-quantum', 'Admin Own Research Notes', '2026-01-01', '2026-01-01')
        """
    )
    conn.commit()
    conn.close()

    # Login as Administrator
    login_admin = client.post("/api/auth/login", json={"identifier": "admin_own", "password": "AdminPass123!"})
    assert login_admin.status_code == 200

    res = client.get("/api/conversations/admin-conv-1")
    assert res.status_code == 200
    assert res.json()["title"] == "Admin Own Research Notes"

def test_15_deactivation_prevents_further_protected_access(test_env):
    """Test 15: Deactivating an active user terminates session immediately."""
    conn = get_connection(test_env)
    pw_admin = hash_password("AdminPass123!")
    pw_user = hash_password("UserPass123!")
    conn.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
        VALUES ('admin-killer', 'adminkiller@example.com', 'admin_killer', ?, 'admin', 'approved', '2026-01-01', '2026-01-01')
        """,
        (pw_admin,)
    )
    conn.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
        VALUES ('user-victim', 'victim2@example.com', 'user_victim', ?, 'user', 'approved', '2026-01-01', '2026-01-01')
        """,
        (pw_user,)
    )
    conn.commit()
    conn.close()

    # 1. Login as user_victim
    with TestClient(app, base_url="http://testserver") as user_client:
        u_login = user_client.post("/api/auth/login", json={"identifier": "user_victim", "password": "UserPass123!"})
        assert u_login.status_code == 200
        assert user_client.get("/api/conversations").status_code == 200

        # 2. Login as admin and deactivate user_victim
        with TestClient(app, base_url="http://testserver") as admin_client:
            a_login = admin_client.post("/api/auth/login", json={"identifier": "admin_killer", "password": "AdminPass123!"})
            assert a_login.status_code == 200
            csrf_token = a_login.json()["csrf_token"]

            deact_res = admin_client.patch(
                "/api/admin/users/user-victim/status",
                json={"status": "deactivated"},
                headers={"X-CSRF-Token": csrf_token}
            )
            assert deact_res.status_code == 200
            assert deact_res.json()["status"] == "deactivated"

        # 3. User victim attempts request with their existing session cookie
        blocked_res = user_client.get("/api/conversations")
        assert blocked_res.status_code in (401, 403)

def test_16_backend_foundation_health_check(test_env, client):
    """Test 16: Backend foundation health check endpoint operates smoothly."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert data["database"] == "healthy"
