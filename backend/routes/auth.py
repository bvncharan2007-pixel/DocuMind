import uuid
import datetime
from fastapi import APIRouter, Request, Response, HTTPException, status, Depends
from backend.models import UserRegisterRequest, UserLoginRequest, UserResponse, AuthStatusResponse
from backend.security import (
    hash_password,
    verify_password,
    generate_session_token,
    generate_csrf_token,
    is_strong_password,
    record_failed_login,
    clear_failed_logins,
    is_rate_limited
)
from backend.config import (
    SESSION_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    SESSION_LIFETIME_SECONDS,
    COOKIE_SECURE,
    COOKIE_SAMESITE
)
from backend.database import get_db
from backend.audit import log_security_event
from backend.dependencies import get_current_session

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(req: UserRegisterRequest, request: Request):
    """Public registration for new users. Accounts always default to pending status."""
    ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    # Validate password strength
    valid_pw, pw_msg = is_strong_password(req.password)
    if not valid_pw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=pw_msg)

    user_id = str(uuid.uuid4())
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    pw_hash = hash_password(req.password)

    with get_db() as conn:
        # Check uniqueness
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ? OR username = ?",
            (req.email.lower().strip(), req.username.strip())
        ).fetchone()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username or email is already registered."
            )

        # Strictly enforce role='user' and status='pending'
        conn.execute(
            """
            INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'user', 'pending', ?, ?)
            """,
            (user_id, req.email.lower().strip(), req.username.strip(), pw_hash, now_iso, now_iso)
        )

    log_security_event(
        event_type="ACCOUNT_REGISTERED",
        actor_id=user_id,
        target_user_id=user_id,
        ip_address=ip,
        user_agent=user_agent,
        details={"username": req.username, "email": req.email.lower().strip()}
    )

    return {
        "message": "Registration submitted successfully. Your account is pending administrator approval.",
        "user_id": user_id,
        "status": "pending"
    }

@router.post("/login")
async def login(req: UserLoginRequest, request: Request, response: Response):
    """Unified login for administrators and users. Authenticates and sets secure HttpOnly cookie."""
    ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    ident = req.identifier.strip().lower()

    # Rate limiting protection
    if is_rate_limited(ip) or is_rate_limited(ident):
        log_security_event(
            event_type="LOGIN_RATE_LIMITED",
            ip_address=ip,
            user_agent=user_agent,
            details={"identifier": ident}
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again in 5 minutes."
        )

    now_dt = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now_dt.isoformat()

    with get_db() as conn:
        user_row = conn.execute(
            "SELECT * FROM users WHERE LOWER(email) = ? OR LOWER(username) = ?",
            (ident, ident)
        ).fetchone()

        if not user_row or not verify_password(req.password, user_row["password_hash"]):
            record_failed_login(ip)
            record_failed_login(ident)
            log_security_event(
                event_type="LOGIN_FAILURE",
                ip_address=ip,
                user_agent=user_agent,
                details={"identifier": ident}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password."
            )

        # Clear failed login counter upon valid password
        clear_failed_logins(ip)
        clear_failed_logins(ident)

        user_status = user_row["status"]
        user_id = user_row["id"]

        # Check account statuses
        if user_status == "rejected":
            log_security_event(
                event_type="LOGIN_REJECTED_ATTEMPT",
                actor_id=user_id,
                ip_address=ip,
                user_agent=user_agent
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account registration was rejected. Please contact an administrator."
            )

        if user_status == "deactivated":
            log_security_event(
                event_type="LOGIN_DEACTIVATED_ATTEMPT",
                actor_id=user_id,
                ip_address=ip,
                user_agent=user_agent
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account has been deactivated. Access denied."
            )

        # Create session (even for pending users, so frontend can display pending screen securely)
        session_token = generate_session_token()
        csrf_token = generate_csrf_token()
        expires_dt = now_dt + datetime.timedelta(seconds=SESSION_LIFETIME_SECONDS)
        expires_iso = expires_dt.isoformat()

        # Update last login and insert session
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now_iso, user_id))
        conn.execute(
            """
            INSERT INTO sessions (id, user_id, csrf_token, ip_address, user_agent, expires_at, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (session_token, user_id, csrf_token, ip, user_agent, expires_iso, now_iso)
        )

    # Set secure HttpOnly cookie for session token
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_LIFETIME_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/"
    )

    # Set CSRF cookie (readable by frontend script for double-submit header)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=SESSION_LIFETIME_SECONDS,
        httponly=False,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/"
    )

    log_security_event(
        event_type="LOGIN_SUCCESS",
        actor_id=user_id,
        target_user_id=user_id,
        ip_address=ip,
        user_agent=user_agent,
        details={"role": user_row["role"], "status": user_status}
    )

    return {
        "message": "Authentication successful.",
        "user": {
            "id": user_row["id"],
            "email": user_row["email"],
            "username": user_row["username"],
            "role": user_row["role"],
            "status": user_status,
            "created_at": user_row["created_at"],
            "last_login_at": now_iso
        },
        "session_token": session_token,
        "csrf_token": csrf_token
    }

@router.post("/logout")
async def logout(request: Request, response: Response, session_data = Depends(get_current_session)):
    """Log out user and invalidate session on server."""
    ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    if session_data:
        token = session_data.get("session_id")
        user = session_data.get("user")
        user_id = user["id"] if user else None

        with get_db() as conn:
            conn.execute("UPDATE sessions SET is_active = 0 WHERE id = ?", (token,))

        log_security_event(
            event_type="LOGOUT",
            actor_id=user_id,
            ip_address=ip,
            user_agent=user_agent
        )

    # Clear cookies
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")

    return {"message": "Logged out successfully."}

@router.get("/me", response_model=AuthStatusResponse)
async def get_current_user_profile(session_data = Depends(get_current_session)):
    """Safe current-user profile endpoint for frontend initialization."""
    if not session_data or not session_data.get("user"):
        return AuthStatusResponse(authenticated=False, user=None, csrf_token=None)

    u = session_data["user"]
    return AuthStatusResponse(
        authenticated=True,
        user=UserResponse(
            id=u["id"],
            email=u["email"],
            username=u["username"],
            role=u["role"],
            status=u["status"],
            created_at=u["created_at"],
            last_login_at=u.get("last_login_at")
        ),
        csrf_token=session_data.get("csrf_token")
    )
