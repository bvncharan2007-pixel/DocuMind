import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Environment variables with safe defaults for development
DATABASE_PATH = os.environ.get("DOCUMIND_DB_PATH", str(DATA_DIR / "documind.db"))
SESSION_SECRET = os.environ.get("DOCUMIND_SESSION_SECRET", "change-this-in-production-use-a-strong-secret-key-32chars")
SESSION_COOKIE_NAME = "documind_session"
CSRF_COOKIE_NAME = "documind_csrf"
SESSION_LIFETIME_SECONDS = int(os.environ.get("DOCUMIND_SESSION_LIFETIME", 86400)) # 24 hours
COOKIE_SECURE = os.environ.get("DOCUMIND_COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.environ.get("DOCUMIND_COOKIE_SAMESITE", "lax")

# Rate limiting
MAX_FAILED_LOGIN_ATTEMPTS = int(os.environ.get("MAX_FAILED_LOGINS", 5))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW", 300)) # 5 minutes

# Allowed Roles and Statuses
VALID_ROLES = {"admin", "user"}
VALID_STATUSES = {"pending", "approved", "rejected", "deactivated"}

# ── Phase 3: RAG Engine ────────────────────────────────────────────────────────

# Google Gemini API
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

# Gemini model IDs — configurable, use current non-deprecated models (Oct 2026)
# Embedding: gemini-embedding-001 outputs 3072-dim vectors by default
# text-embedding-004 was shut down Jan 14 2026 — do NOT use it
GEMINI_EMBEDDING_MODEL = os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
GEMINI_EMBEDDING_DIMENSIONS = int(os.environ.get("GEMINI_EMBEDDING_DIMENSIONS", 768))  # truncated via MRL

# Generation: gemini-1.5-flash — free tier, fast, capable
GEMINI_GENERATION_MODEL = os.environ.get("GEMINI_GENERATION_MODEL", "gemini-3.8-flash")

# File upload constraints
UPLOAD_DIR = Path(os.environ.get("DOCUMIND_UPLOAD_DIR", str(DATA_DIR / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", 50))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_FILES_PER_REQUEST = int(os.environ.get("MAX_FILES_PER_REQUEST", 10))
MAX_TOTAL_DOCUMENTS_PER_CONVERSATION = int(os.environ.get("MAX_DOCS_PER_CONV", 20))

# FAISS index storage
INDEX_DIR = Path(os.environ.get("DOCUMIND_INDEX_DIR", str(DATA_DIR / "indexes")))
INDEX_DIR.mkdir(parents=True, exist_ok=True)

# Chunking configuration
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", 800))       # characters per chunk
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", 150)) # overlap between consecutive chunks

# Retrieval configuration
MAX_RETRIEVAL_CHUNKS = int(os.environ.get("MAX_RETRIEVAL_CHUNKS", 6))
MIN_SIMILARITY_SCORE = float(os.environ.get("MIN_SIMILARITY_SCORE", 0.0))  # L2 distance — lower is better

# Gemini retry settings
GEMINI_MAX_RETRIES = int(os.environ.get("GEMINI_MAX_RETRIES", 3))
GEMINI_RETRY_BACKOFF_SECONDS = float(os.environ.get("GEMINI_RETRY_BACKOFF", 2.0))
