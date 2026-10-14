import sys
import uuid
import datetime
import argparse
import getpass
from backend.database import get_db, init_db
from backend.security import hash_password, is_strong_password
from backend.audit import log_security_event

def create_initial_admin(username: str, email: str, password: str, db_path: str = None) -> bool:
    """
    Secure one-time initial administrator bootstrap command.
    Enforces password strength and blocks repeated execution if an admin already exists.
    """
    init_db(db_path)

    with get_db(db_path) as conn:
        # Check if an active administrator already exists
        existing_admin = conn.execute(
            "SELECT id, username FROM users WHERE role = 'admin' AND status = 'approved'"
        ).fetchone()

        if existing_admin:
            print(f"[SECURITY REJECTION] Administrator already exists (User: {existing_admin['username']}).")
            print("Repeated bootstrap operations are strictly blocked to prevent account takeover.")
            return False

        # Validate password
        is_valid, msg = is_strong_password(password)
        if not is_valid:
            print(f"[ERROR] Password does not meet security requirements: {msg}")
            return False

        # Check username / email uniqueness
        existing_user = conn.execute(
            "SELECT id FROM users WHERE email = ? OR username = ?",
            (email.lower().strip(), username.strip())
        ).fetchone()

        if existing_user:
            print("[ERROR] A user with this username or email already exists.")
            return False

        user_id = str(uuid.uuid4())
        pw_hash = hash_password(password)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        conn.execute(
            """
            INSERT INTO users (id, email, username, password_hash, role, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'admin', 'approved', ?, ?)
            """,
            (user_id, email.lower().strip(), username.strip(), pw_hash, now_iso, now_iso)
        )

    log_security_event(
        event_type="INITIAL_ADMIN_BOOTSTRAP",
        actor_id=user_id,
        target_user_id=user_id,
        ip_address="CLI_LOCAL",
        details={"username": username, "email": email.lower().strip()},
        db_path=db_path
    )

    print("=====================================================")
    print("SUCCESS: Initial Administrator Account Provisioned")
    print(f"Username : {username}")
    print(f"Email    : {email}")
    print("Status   : approved")
    print("Role     : admin")
    print("=====================================================")
    return True

def main():
    parser = argparse.ArgumentParser(description="DocuMind Security CLI - Admin Provisioning")
    subparsers = parser.add_subparsers(dest="command")

    admin_parser = subparsers.add_parser("create-admin", help="Provision the initial administrator")
    admin_parser.add_argument("--username", help="Admin username")
    admin_parser.add_argument("--email", help="Admin email address")
    admin_parser.add_argument("--password", help="Admin password (will prompt securely if omitted)")

    args = parser.parse_args()

    if args.command == "create-admin":
        username = args.username or input("Enter administrator username: ").strip()
        email = args.email or input("Enter administrator email: ").strip()
        password = args.password or getpass.getpass("Enter administrator password: ").strip()

        success = create_initial_admin(username=username, email=email, password=password)
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
