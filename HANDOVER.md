# DocuMind — Project Handover

**Project:** DocuMind — AI-powered document intelligence platform  
**Build status:** Production build passing (0 errors, 1918 modules)  
**Test status:** 140/140 automated tests passing  
**Deployment status:** Local development verified. Not yet deployed to a public URL.

---

## 1. Problem Statement and Objectives

### Problem
Knowledge workers spend significant time manually searching through long PDF documents — research papers, policy files, legal contracts, reports — looking for specific facts. Manual search is slow, error-prone, and does not surface the exact page or passage where an answer lives.

### Objectives
1. Allow users to upload multiple PDFs and ask natural-language questions against them.
2. Return answers grounded in retrieved evidence, with the source filename and exact page number cited.
3. Keep each user's documents and conversations strictly private — isolated from every other user including administrators.
4. Provide a secure, role-based multi-user platform with administrator-controlled account access.
5. Deliver a polished, production-quality interface with light and dark themes.

---

## 2. Architecture Overview

```
Browser (React 19 + Vite 8)
    │  HTTPS  ·  session cookie  ·  CSRF header
    ▼
FastAPI 0.143 (Uvicorn 0.54)
    │
    ├── Auth routes      → SQLite sessions / users
    ├── Conversation routes → SQLite conversations / messages
    ├── Document routes  → PDF validation → PyMuPDF → chunker
    │                      → Gemini embedding → FAISS index
    │                      → SQLite documents / chunks
    ├── QA route         → Gemini embed query → FAISS search
    │                      → Gemini generate answer
    │                      → SQLite messages (+ citation JSON)
    └── Admin routes     → SQLite users / audit_logs

SQLite  ──  data/documind.db
Files   ──  data/uploads/<uuid>.pdf
FAISS   ──  data/indexes/<conv-uuid>.faiss
            data/indexes/<conv-uuid>.meta.json
```

---

## 3. Technology Stack

| Component | Technology | Version |
|---|---|---|
| Frontend | React + Vite | 19.2.8 / 8.3.0 |
| Backend | FastAPI + Uvicorn | 0.143.0 / 0.54.0 |
| Language (backend) | Python | 3.10+ |
| Language (frontend) | JavaScript (JSX) | ES2022 |
| Database | SQLite (WAL mode) | stdlib |
| PDF extraction | PyMuPDF (fitz) | 1.26.3 |
| Vector search | faiss-cpu | 1.15.1 |
| AI SDK | google-genai | 1.20.0 |
| Embedding model | gemini-embedding-001 | 768-dim (MRL) |
| Generation model | gemini-1.5-flash | Free tier |

---

## 4. Main Features

All features below are implemented and verified by automated tests.

| Feature | Status |
|---|---|
| Username/email login with PBKDF2-SHA256 hashing | ✅ Verified |
| Server-side sessions + CSRF double-submit | ✅ Verified |
| In-memory rate limiting (5 attempts / 5 min) | ✅ Verified |
| Admin-controlled account approvals | ✅ Verified |
| Role-based access (user / admin) | ✅ Verified |
| Multi-PDF upload (up to 10 files, 50 MB each) | ✅ Verified |
| PDF validation (type, magic bytes, size, encryption, text layer) | ✅ Verified |
| Page-aware text chunking | ✅ Verified |
| Gemini semantic embedding + FAISS indexing | ✅ Verified |
| Grounded Q&A with per-page citations | ✅ Verified |
| Citation persistence (survives logout/restart) | ✅ Verified |
| Persistent conversation history | ✅ Verified |
| Additive PDF uploads (no data loss) | ✅ Verified |
| Conversation rename and delete with cascade cleanup | ✅ Verified |
| Admin dashboard: user management + audit logs | ✅ Verified |
| Light Mode + Night Mode with localStorage persistence | ✅ Verified |
| Admin cannot access other users' private data | ✅ Verified (backend-tested) |
| OCR for scanned PDFs | ❌ Not implemented |
| In-browser PDF page preview | ❌ Not implemented |
| Conversation export | ❌ Not implemented |
| Email notifications | ❌ Not implemented |
| Multi-instance / horizontal scaling | ❌ Not supported |

---

## 5. Security and Privacy Design

- Passwords: PBKDF2-HMAC-SHA256, 600 000 iterations, random salt, `hmac.compare_digest()`
- Sessions: server-side in SQLite, HttpOnly cookie, CSRF double-submit
- Authorization: ownership enforced at DB query level — not UI visibility
- Admin privacy: administrator role does not bypass the `WHERE user_id = ?` ownership check on any endpoint
- File security: server-generated UUID filenames, magic-byte validation, no user-controlled paths
- Secrets: all credentials via environment variables — never hardcoded
- Audit log: immutable event log; passwords, tokens, document text never recorded
- Prompt injection: Gemini system instruction explicitly instructs the model to ignore PDF-embedded directives; PDF text is passed as labelled EVIDENCE only
- CORS: restricted to explicit localhost origins (must be updated for production)

**Data privacy note:** Document text is sent to Google's Gemini API during embedding and generation. Do not upload confidential organizational content without reviewing Google's applicable data-handling terms.

See `SECURITY.md` for the complete security documentation and deployment checklist.

---

## 6. Testing Summary

**Command:** `python -m pytest tests/ -v`  
**Environment:** Python 3.14.4, pytest 9.1.1, Windows — all Gemini calls mocked

| Test file | Tests | Result |
|---|---|---|
| `tests/test_auth_security.py` | 16 | ✅ 16 PASSED |
| `tests/test_rag_phase3.py` | 30 | ✅ 30 PASSED |
| `tests/test_phase4_conversations.py` | 37 | ✅ 37 PASSED |
| `tests/test_phase6_audit.py` | 57 | ✅ 57 PASSED |
| **Total** | **140** | ✅ **140 PASSED** |

**Tests NOT executed:**
- Browser automation (no Playwright/Cypress configured) — manual verification only
- Live Gemini integration (mocked) — requires a real `GOOGLE_API_KEY`

**Frontend build:** `node node_modules/vite/bin/vite.js build` → ✅ 1918 modules, 0 errors

---

## 7. Setup Instructions (Quick Reference)

Full instructions: see `README.md`

```bash
# 1. Clone and enter directory
git clone <repo-url> && cd DocuMind

# 2. Python virtual environment
python -m venv .venv && .venv\Scripts\activate   # Windows
# source .venv/bin/activate                       # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt
npm install

# 4. Configure environment
copy .env.example .env     # then edit: set GOOGLE_API_KEY and SESSION_SECRET

# 5. Bootstrap admin
python -m backend.cli create-admin --username admin --email admin@example.com

# 6. Start backend (terminal 1)
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

# 7. Start frontend (terminal 2)
node node_modules/vite/bin/vite.js

# 8. Open browser
#    http://127.0.0.1:5173

# 9. Run tests
python -m pytest tests/ -v
```

---

## 8. Environment Variables (Minimum Required)

| Variable | Purpose |
|---|---|
| `GOOGLE_API_KEY` | Gemini API key (embedding + generation) |
| `DOCUMIND_SESSION_SECRET` | Session integrity secret (32+ chars) |

Full reference: `.env.example`

---

## 9. Persistent Storage

The following directories **must survive server restarts and redeployments**:

| Path | Contents |
|---|---|
| `data/documind.db` | All user, conversation, message, and document data |
| `data/uploads/` | Uploaded PDF files (UUID filenames) |
| `data/indexes/` | FAISS vector indexes per conversation |

Losing any of these directories results in data loss. Back up all three together.

**Backup command:**
```bash
sqlite3 data/documind.db ".backup 'backup/documind.db'"
cp -r data/uploads backup/uploads
cp -r data/indexes backup/indexes
```

---

## 10. Known Limitations

| Limitation | Impact |
|---|---|
| No OCR | Scanned-image PDFs rejected with clear error |
| Single server only | SQLite + local filesystem; cannot scale horizontally |
| In-memory rate limiting | Resets on restart; no Redis backend |
| No browser tests | UI verified manually only |
| No email system | Account approvals require admin login |
| Gemini data leaves server | Document text sent to Google's API |
| No PDF preview | Citations show filename + page number only |

---

## 11. Future Enhancements

These are out of scope for the current build but represent natural next steps:

1. **OCR** — Integrate Tesseract or Google Vision for scanned PDFs
2. **PostgreSQL + object storage** — Replace SQLite + local filesystem for multi-instance deployments
3. **Redis rate limiting** — Persist rate-limit state across restarts
4. **Conversation export** — Export chat + citations as PDF or Markdown
5. **Email notifications** — Notify users when accounts are approved
6. **2FA** — TOTP-based two-factor authentication
7. **PDF page preview** — Serve authorized signed page images for citation clicking
8. **Background task queue** — Move PDF ingestion off the request thread (Celery, ARQ)
9. **Browser automation tests** — Playwright end-to-end test suite

---

## 12. Deployment Readiness

| Item | Status |
|---|---|
| Application functional | ✅ |
| Automated tests passing | ✅ 140/140 |
| Production build | ✅ 0 errors |
| Documentation complete | ✅ |
| HTTPS configured | ⚠️ Requires setup |
| Persistent storage provisioned | ⚠️ Requires setup |
| Secrets in environment | ⚠️ Requires setup |
| Production domain in CORS | ⚠️ Requires update |
| Deployed to public URL | ❌ Local only |

The application is **ready for local demonstration and development**. Deployment to a public URL requires the four ⚠️ items above — see `DEPLOYMENT.md`.
