import os
import sqlite3
import datetime
from pathlib import Path
from typing import Optional, Generator
from contextlib import contextmanager

from backend.config import DATABASE_PATH

def get_db_path() -> str:
  """Get current database path dynamically from environment or config."""
  return os.environ.get("DOCUMIND_DB_PATH", DATABASE_PATH)

def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
  """Get SQLite database connection with row factory and foreign keys enabled."""
  path = db_path or get_db_path()
  Path(path).parent.mkdir(parents=True, exist_ok=True)
  conn = sqlite3.connect(path, timeout=10.0, check_same_thread=False)
  conn.row_factory = sqlite3.Row
  conn.execute("PRAGMA foreign_keys = ON;")
  conn.execute("PRAGMA journal_mode = WAL;")
  return conn

@contextmanager
def get_db(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
  """Context manager for database transaction management."""
  conn = get_connection(db_path)
  try:
    yield conn
    conn.commit()
  except Exception:
    conn.rollback()
    raise
  finally:
    conn.close()

def init_db(db_path: Optional[str] = None) -> None:
  """Initialize database tables, constraints, and indexes."""
  with get_db(db_path) as conn:
    # 1. Users table
    conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user')) DEFAULT 'user',
                status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected', 'deactivated')) DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT
            );
        """)

    # 2. Server-managed Sessions table
    conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                csrf_token TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );
        """)

    # 3. Security Audit Logs table
    conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                actor_id TEXT,
                target_user_id TEXT,
                ip_address TEXT,
                user_agent TEXT,
                details TEXT,
                created_at TEXT NOT NULL
            );
        """)

    # 4. Conversations table (private per user)
    conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                document_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)

    # 5. Messages table (private per user and conversation)
    conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)

    # Indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON"
        " sessions(expires_at);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON"
        " audit_logs(event_type);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON"
        " audit_logs(created_at);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON"
        " conversations(user_id);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON"
        " messages(conversation_id);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);"
    )

    # ── Phase 3: RAG Engine tables ────────────────────────────────────────────

    # 6. Documents table — one row per uploaded PDF file
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            file_size_bytes INTEGER NOT NULL,
            page_count INTEGER,
            status TEXT NOT NULL CHECK(status IN ('pending','processing','completed','failed')) DEFAULT 'pending',
            error_message TEXT,
            uploaded_at TEXT NOT NULL,
            processed_at TEXT
        );
    """)

    # 7. Chunks table — one row per text chunk extracted from a document
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            conversation_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            start_page INTEGER NOT NULL,
            end_page INTEGER NOT NULL,
            char_start INTEGER,
            char_end INTEGER,
            created_at TEXT NOT NULL
        );
    """)

    # 8. Index metadata — one row per FAISS index scope (one index per conversation)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS index_metadata (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            embedding_dimensions INTEGER NOT NULL,
            index_version INTEGER NOT NULL DEFAULT 1,
            total_vectors INTEGER NOT NULL DEFAULT 0,
            index_file TEXT NOT NULL,
            meta_file TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)

    # Additional indexes for Phase 3
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_conversation_id ON documents(conversation_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_conversation_id ON chunks(conversation_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_index_metadata_conversation_id ON index_metadata(conversation_id);")

    # ── Phase 4: Additive migrations (safe — ALTER TABLE ADD COLUMN is idempotent via try/except) ──

    # Add citations JSON column to messages (stores validated source citations per assistant turn)
    _add_column_if_missing(conn, "messages", "citations", "TEXT")

    # conversations.document_id was a legacy required field; make it nullable by adding
    # a new column since SQLite cannot ALTER column constraints.
    # We keep document_id for backward compatibility but use a separate flag column
    # to know if the conversation was created before Phase 4 (no migration needed for data).

    # Add message_count and document_count as view-friendly columns is not needed —
    # counts are computed on query. No schema change required for those.


def _add_column_if_missing(conn, table: str, column: str, col_type: str) -> None:
    """Add a column to an existing table only if it does not already exist."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type};")
    except Exception:
        pass  # Column already exists — SQLite raises OperationalError, not a specific type
