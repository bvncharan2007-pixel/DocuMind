import uuid
import datetime
from typing import List, Optional
from fastapi import APIRouter, Request, HTTPException, status, Depends
from backend.models import (
    UserResponse,
    UserStatusUpdateRequest,
    UserRoleUpdateRequest,
    AdminCreateUserRequest,
    AuditLogResponse
)
from backend.dependencies import require_admin, verify_csrf_token
from backend.database import get_db
from backend.security import hash_password, is_strong_password
from backend.audit import log_security_event

router = APIRouter(
    prefix="/api/admin",
    tags=["Administrator Management"],
    dependencies=[Depends(require_admin), Depends(verify_csrf_token)]
)

@router.get("/users", response_model=List[UserResponse])
async def list_users():
    """List all user accounts and their authorization metadata. Admin only."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, email, username, role, status, created_at, last_login_at
            FROM users
            ORDER BY created_at DESC
            """
        ).fetchall()
        return [
            UserResponse(
                id=r["id"],
                email=r["email"],
                username=r["username"],
                role=r["role"],
                status=r["status"],
                created_at=r["created_at"],
                last_login_at=r["last_login_at"]
            )
            for r in rows
        ]

@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    req: AdminCreateUserRequest,
    request: Request,
    admin_user: dict = Depends(require_admin)
):
    """Admin provisions an account directly."""
    valid_pw, pw_msg = is_strong_password(req.password)
    if not valid_pw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=pw_msg)

    user_id = str(uuid.uuid4())
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    pw_hash = hash_password(req.password)

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ? OR username = ?",
            (req.email.lower().strip(), req.username.strip())
        ).fetchone()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email or username already exists."
            )

        conn.execute(
            """
            INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, req.email.lower().strip(), req.username.strip(), pw_hash, req.role, req.status, now_iso, now_iso)
        )

    log_security_event(
        event_type="ADMIN_USER_PROVISIONED",
        actor_id=admin_user["id"],
        target_user_id=user_id,
        ip_address=request.client.host if request.client else "unknown",
        details={"username": req.username, "role": req.role, "status": req.status}
    )

    return UserResponse(
        id=user_id,
        email=req.email.lower().strip(),
        username=req.username.strip(),
        role=req.role,
        status=req.status,
        created_at=now_iso,
        last_login_at=None
    )

@router.patch("/users/{user_id}/status", response_model=UserResponse)
async def update_user_status(
    user_id: str,
    req: UserStatusUpdateRequest,
    request: Request,
    admin_user: dict = Depends(require_admin)
):
    """Approve, reject, or deactivate user account. Deactivation revokes active sessions immediately."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    new_status = req.status

    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        # Prevent admin from deactivating their own account
        if user_id == admin_user["id"] and new_status == "deactivated":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate your own administrator account."
            )

        old_status = user["status"]
        conn.execute(
            "UPDATE users SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now_iso, user_id)
        )

        # Immediately invalidate active sessions if account is deactivated or rejected
        if new_status in ("deactivated", "rejected"):
            conn.execute("UPDATE sessions SET is_active = 0 WHERE user_id = ?", (user_id,))

        updated_user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    # Determine event type
    event_type = "ACCOUNT_STATUS_CHANGED"
    if new_status == "approved":
        event_type = "ACCOUNT_APPROVED" if old_status == "pending" else "ACCOUNT_REACTIVATED"
    elif new_status == "rejected":
        event_type = "ACCOUNT_REJECTED"
    elif new_status == "deactivated":
        event_type = "ACCOUNT_DEACTIVATED"

    log_security_event(
        event_type=event_type,
        actor_id=admin_user["id"],
        target_user_id=user_id,
        ip_address=request.client.host if request.client else "unknown",
        details={"previous_status": old_status, "new_status": new_status}
    )

    return UserResponse(
        id=updated_user["id"],
        email=updated_user["email"],
        username=updated_user["username"],
        role=updated_user["role"],
        status=updated_user["status"],
        created_at=updated_user["created_at"],
        last_login_at=updated_user["last_login_at"]
    )

@router.patch("/users/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: str,
    req: UserRoleUpdateRequest,
    request: Request,
    admin_user: dict = Depends(require_admin)
):
    """Change user role between admin and user."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    new_role = req.role

    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        # Prevent admin from demoting themselves if they are the only admin
        if user_id == admin_user["id"] and new_role != "admin":
            admin_count = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'admin' AND status = 'approved'").fetchone()["cnt"]
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot demote the sole active administrator."
                )

        old_role = user["role"]
        conn.execute(
            "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
            (new_role, now_iso, user_id)
        )
        updated_user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    log_security_event(
        event_type="ROLE_CHANGED",
        actor_id=admin_user["id"],
        target_user_id=user_id,
        ip_address=request.client.host if request.client else "unknown",
        details={"previous_role": old_role, "new_role": new_role}
    )

    return UserResponse(
        id=updated_user["id"],
        email=updated_user["email"],
        username=updated_user["username"],
        role=updated_user["role"],
        status=updated_user["status"],
        created_at=updated_user["created_at"],
        last_login_at=updated_user["last_login_at"]
    )

@router.get("/audit-logs", response_model=List[AuditLogResponse])
async def get_audit_logs(limit: int = 100):
    """Retrieve security audit logs. Strictly restricted to approved administrators."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, event_type, actor_id, target_user_id, ip_address, user_agent, details, created_at
            FROM audit_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(500, limit)),)
        ).fetchall()
        return [
            AuditLogResponse(
                id=r["id"],
                event_type=r["event_type"],
                actor_id=r["actor_id"],
                target_user_id=r["target_user_id"],
                ip_address=r["ip_address"],
                user_agent=r["user_agent"],
                details=r["details"],
                created_at=r["created_at"]
            )
            for r in rows
        ]
