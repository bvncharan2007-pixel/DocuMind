import datetime
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status, Depends
from backend.config import SESSION_COOKIE_NAME, CSRF_COOKIE_NAME
from backend.database import get_db

async def get_current_session(request: Request) -> Optional[Dict[str, Any]]:
    """Extract and validate the active server-managed session from cookies or Bearer header."""
    # 1. Try HttpOnly session cookie
    token = request.cookies.get(SESSION_COOKIE_NAME)
    
    # 2. Fallback to Authorization: Bearer <token>
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            
    if not token:
        return None

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT s.id as session_id, s.user_id, s.csrf_token, s.expires_at, s.is_active,
                   u.id, u.email, u.username, u.role, u.status, u.created_at, u.last_login_at
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = ? AND s.is_active = 1
            """,
            (token,)
        ).fetchone()

        if not row:
            return None

        # Check session expiration
        if row["expires_at"] <= now_iso:
            # Mark session expired
            conn.execute("UPDATE sessions SET is_active = 0 WHERE id = ?", (token,))
            return None

        # If user is deactivated or rejected, reject immediately
        if row["status"] in ("deactivated", "rejected"):
            return {
                "session_id": row["session_id"],
                "csrf_token": row["csrf_token"],
                "user": dict(row)
            }

        return {
            "session_id": row["session_id"],
            "csrf_token": row["csrf_token"],
            "user": dict(row)
        }

async def require_authenticated_user(
    request: Request,
    session_data: Optional[Dict[str, Any]] = Depends(get_current_session)
) -> Dict[str, Any]:
    """Ensure request has a valid, active session."""
    if not session_data or not session_data.get("user"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required."
        )
    user = session_data["user"]
    # Immediate check for deactivated account
    if user.get("status") == "deactivated":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Access denied."
        )
    return user

async def require_approved_user(
    user: Dict[str, Any] = Depends(require_authenticated_user)
) -> Dict[str, Any]:
    """Ensure user account is approved and active."""
    account_status = user.get("status")
    if account_status == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is pending administrator approval."
        )
    if account_status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account registration was rejected."
        )
    if account_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active."
        )
    return user

async def require_admin(
    user: Dict[str, Any] = Depends(require_approved_user)
) -> Dict[str, Any]:
    """Ensure user is an approved administrator."""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required."
        )
    return user

async def verify_csrf_token(
    request: Request,
    session_data: Optional[Dict[str, Any]] = Depends(get_current_session)
) -> None:
    """Validate CSRF token for state-changing browser requests."""
    # Only enforce for mutating HTTP methods
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    # If authenticated via Bearer token, CSRF is not required (API client)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return

    # For cookie-based sessions, require CSRF token match
    if session_data:
        csrf_header = request.headers.get("X-CSRF-Token")
        csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
        session_csrf = session_data.get("csrf_token")

        if not csrf_header or (csrf_header != csrf_cookie and csrf_header != session_csrf):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed."
            )
