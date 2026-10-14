import hashlib
import hmac
import secrets
import time
from typing import Tuple, Dict

# PBKDF2 parameters aligned with OWASP recommendations
PBKDF2_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 600000
SALT_BYTES = 16

# In-memory rate limiting tracker for login attempts
# Format: key -> [(timestamp), ...]
_failed_login_attempts: Dict[str, list] = {}

def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with 600,000 iterations and a random salt."""
    salt = secrets.token_bytes(SALT_BYTES)
    key = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS
    )
    return f"pbkdf2:{PBKDF2_ALGORITHM}:{PBKDF2_ITERATIONS}${salt.hex()}${key.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against stored PBKDF2 hash using constant-time comparison."""
    try:
        header, salt_hex, key_hex = hashed_password.split("$")
        parts = header.split(":")
        if len(parts) != 3 or parts[0] != "pbkdf2":
            return False
        algo = parts[1]
        iterations = int(parts[2])
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        
        computed_key = hashlib.pbkdf2_hmac(
            algo,
            plain_password.encode("utf-8"),
            salt,
            iterations
        )
        return hmac.compare_digest(computed_key, expected_key)
    except Exception:
        return False

def generate_session_token() -> str:
    """Generate a high-entropy cryptographically secure session token."""
    return secrets.token_urlsafe(36)

def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_urlsafe(32)

def is_strong_password(password: str) -> Tuple[bool, str]:
    """Validate password strength."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not any(c.isupper() or c.islower() for c in password):
        return False, "Password must contain letters."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit."
    return True, ""

def record_failed_login(identifier: str) -> None:
    """Record a failed login attempt for rate limiting."""
    now = time.time()
    if identifier not in _failed_login_attempts:
        _failed_login_attempts[identifier] = []
    # Prune old entries outside 5 minutes
    _failed_login_attempts[identifier] = [
        t for t in _failed_login_attempts[identifier] if now - t < 300
    ]
    _failed_login_attempts[identifier].append(now)

def clear_failed_logins(identifier: str) -> None:
    """Clear failed login attempts on successful authentication."""
    if identifier in _failed_login_attempts:
        del _failed_login_attempts[identifier]

def reset_rate_limits() -> None:
    """Reset all in-memory rate limiting counters (used in testing and maintenance)."""
    _failed_login_attempts.clear()

def is_rate_limited(identifier: str, max_attempts: int = 5, window_seconds: int = 300) -> bool:
    """Check if identifier (IP or username) has exceeded failed attempt limits."""
    now = time.time()
    attempts = _failed_login_attempts.get(identifier, [])
    active_attempts = [t for t in attempts if now - t < window_seconds]
    _failed_login_attempts[identifier] = active_attempts
    return len(active_attempts) >= max_attempts
