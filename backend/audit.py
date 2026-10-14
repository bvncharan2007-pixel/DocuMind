import json
import datetime
from typing import Optional, Dict, Any
from backend.database import get_db

def log_security_event(
    event_type: str,
    actor_id: Optional[str] = None,
    target_user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None
) -> None:
    """
    Record an immutable security audit event.
    NEVER logs passwords, session tokens, API keys, document text, or chat contents.
    """
    # Sanitize details to guarantee sensitive fields are never saved
    safe_details = {}
    if details:
        for k, v in details.items():
            if k.lower() in ("password", "token", "secret", "cookie", "api_key", "prompt", "content", "transcript"):
                continue
            safe_details[k] = str(v)

    details_str = json.dumps(safe_details) if safe_details else None
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        with get_db(db_path) as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (event_type, actor_id, target_user_id, ip_address, user_agent, details, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_type, actor_id, target_user_id, ip_address, user_agent, details_str, now_iso)
            )
    except Exception as e:
        # Logging failure should not crash core authentication, but log to stderr
        print(f"[SECURITY AUDIT ERROR] Failed to record {event_type}: {e}")
