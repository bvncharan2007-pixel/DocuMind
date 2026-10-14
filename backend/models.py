from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# ── Authentication Models ──────────────────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=120)
    password: str = Field(..., min_length=8, max_length=128)

class UserLoginRequest(BaseModel):
    identifier: str = Field(..., min_length=3, max_length=100)  # username or email
    password: str = Field(..., min_length=1, max_length=128)

class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    role: str
    status: str
    created_at: str
    last_login_at: Optional[str] = None

class AuthStatusResponse(BaseModel):
    authenticated: bool
    user: Optional[UserResponse] = None
    csrf_token: Optional[str] = None

# ── Admin Management Models ───────────────────────────────────────────────────

class UserStatusUpdateRequest(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected|deactivated)$")

class UserRoleUpdateRequest(BaseModel):
    role: str = Field(..., pattern="^(admin|user)$")

class AdminCreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=120)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="user", pattern="^(admin|user)$")
    status: str = Field(default="approved", pattern="^(approved|pending)$")

class AuditLogResponse(BaseModel):
    id: int
    event_type: str
    actor_id: Optional[str] = None
    target_user_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details: Optional[str] = None
    created_at: str

# ── Conversation Models ───────────────────────────────────────────────────────

class ConversationCreateRequest(BaseModel):
    """
    Phase 4: document_id is now optional (conversations start empty; documents
    are added via the document-upload endpoint).  A title is also optional —
    if omitted, the server generates one from the first question asked.
    Both fields are kept for backward compatibility with Phase 2/3 tests that
    pass a dummy document_id and explicit title.
    """
    document_id: Optional[str] = None      # legacy field; kept for compatibility
    title: Optional[str] = Field(None, min_length=1, max_length=200)

class ConversationRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)

class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0       # summary count for sidebar — no message content exposed
    document_count: int = 0      # number of documents (any status)

class MessageCreateRequest(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1)

class CitationResponse(BaseModel):
    document_id: str
    filename: str
    page_range: str
    start_page: int
    end_page: int
    excerpt: str

class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: str
    citations: List[CitationResponse] = []  # populated for assistant messages; empty for user


# ── Phase 3: RAG Engine Models ────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    id: str
    conversation_id: str
    original_filename: str
    file_size_bytes: int
    page_count: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    uploaded_at: str
    processed_at: Optional[str] = None

class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int

class DocumentStatusResponse(BaseModel):
    id: str
    original_filename: str
    status: str
    error_message: Optional[str] = None
    page_count: Optional[int] = None
    processed_at: Optional[str] = None

class UploadResultItem(BaseModel):
    filename: str
    document_id: Optional[str] = None
    status: str             # 'processing' (accepted) or 'failed'
    error: Optional[str] = None

class UploadResponse(BaseModel):
    results: List[UploadResultItem]
    accepted: int
    failed: int

class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4096)

class AnswerResponse(BaseModel):
    answer: str
    citations: List[CitationResponse]
    retrieved_chunks: int
    insufficient_evidence: bool
    error: Optional[str] = None
    conversation_id: str
    message_id: Optional[str] = None       # persisted assistant message ID
    conversation_title: Optional[str] = None  # echoes the (possibly auto-set) title
