import contextlib
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.database import init_db, get_db
from backend.routes import auth, admin, conversations
from backend.routes import documents, qa

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database and schemas
    init_db()
    yield

app = FastAPI(
    title="DocuMind API",
    description="DocuMind AI Document Intelligence & Research Assistant API",
    version="2.0.0",
    lifespan=lifespan
)

# CORS configuration for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Mount routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(conversations.router)
app.include_router(documents.router)
app.include_router(qa.router)

@app.get("/api/health")
async def health_check():
    """Service health and database readiness check."""
    try:
        with get_db() as conn:
            conn.execute("SELECT 1").fetchone()
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {e}"

    return {
        "status": "online",
        "service": "DocuMind Security & Auth API",
        "version": "2.0.0",
        "database": db_status
    }
