# DocuMind — Deployment Guide

This guide covers local production simulation, self-hosted VPS deployment, and platform-as-a-service options. Read it fully before attempting any deployment.

---

## Deployment Readiness Assessment

| Requirement | Status | Notes |
|---|---|---|
| Backend functional | ✅ | FastAPI + Uvicorn |
| Frontend production build | ✅ | Vite, 0 errors |
| Automated test suite | ✅ | 140/140 pass |
| HTTPS support | ⚠️ Needs configuration | Requires reverse proxy + TLS certificate |
| Persistent storage | ⚠️ Must be provisioned | SQLite + local filesystem — cannot use ephemeral disk |
| Secrets management | ⚠️ Must be configured | `.env` or platform secret store |
| Multi-instance scaling | ❌ Not supported | Single-server only (SQLite + local FAISS) |
| Browser automation tests | ❌ Not configured | Manual UI verification only |

**Do not deploy to a public URL without addressing the HTTPS and persistent-storage requirements.**

---

## 1. Architecture for Deployment

```
Internet
    │  HTTPS (port 443)
    ▼
Reverse Proxy  (nginx / Caddy / Traefik)
    ├── Static files: /  →  dist/   (Vite production build)
    └── API:          /api/*  →  localhost:8000  (Uvicorn)

Uvicorn  :8000
    └── FastAPI app  (backend/)

Persistent Volume  (must survive restarts)
    └── data/
        ├── documind.db
        ├── uploads/
        └── indexes/
```

The frontend and backend can run on the same machine served by a single reverse proxy, or on separate hosts with CORS configured accordingly.

---

## 2. Production Environment Variables

Create a `.env` file (never commit it). Every variable below should be set explicitly in production.

```env
# ── Required ──────────────────────────────────────────────────────────────────
GOOGLE_API_KEY=your_real_gemini_api_key

# At least 32 random characters — generate with:
# python -c "import secrets; print(secrets.token_urlsafe(48))"
DOCUMIND_SESSION_SECRET=<generated-secret>

# ── Storage (point to your persistent volume) ─────────────────────────────────
DOCUMIND_DB_PATH=/data/documind.db
DOCUMIND_UPLOAD_DIR=/data/uploads
DOCUMIND_INDEX_DIR=/data/indexes

# ── Security ──────────────────────────────────────────────────────────────────
DOCUMIND_COOKIE_SECURE=true       # MUST be true when served over HTTPS
DOCUMIND_COOKIE_SAMESITE=lax

# ── Session ───────────────────────────────────────────────────────────────────
DOCUMIND_SESSION_LIFETIME=86400   # 24 hours

# ── Gemini models ─────────────────────────────────────────────────────────────
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
GEMINI_EMBEDDING_DIMENSIONS=768
GEMINI_GENERATION_MODEL=gemini-1.5-flash
GEMINI_MAX_RETRIES=3
GEMINI_RETRY_BACKOFF=2.0

# ── Upload limits ─────────────────────────────────────────────────────────────
MAX_FILE_SIZE_MB=50
MAX_FILES_PER_REQUEST=10
MAX_DOCS_PER_CONV=20
```

---

## 3. Build Steps

### Backend (no build step)
FastAPI runs directly from source. Just install dependencies:

```bash
pip install -r requirements.txt
```

### Frontend

```bash
node node_modules/vite/bin/vite.js build
# Output: dist/
```

The `dist/` directory contains static HTML, CSS, and JS. Serve it from any static file server or the same Uvicorn host via a reverse proxy.

---

## 4. Database Initialization

The database is created automatically when the backend starts if it does not already exist:

```bash
# The database is initialized inside lifespan() in backend/main.py
# Just starting the server is enough:
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Migrations are additive `ALTER TABLE ADD COLUMN` statements wrapped in try/except — they run at every startup and are safe to run repeatedly. **There is no separate migration command.**

---

## 5. Administrator Provisioning

Run once on a fresh database:

```bash
python -m backend.cli create-admin \
  --username admin \
  --email admin@yourdomain.com
# Enter password securely at the prompt
```

This command is idempotent-safe: it is blocked from running a second time if any approved admin already exists.

---

## 6. Starting the Application

### Development

```bash
# Terminal 1 — backend
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 — frontend dev server
node node_modules/vite/bin/vite.js
```

### Production (single server)

```bash
# Backend (as a systemd service or process manager)
uvicorn backend.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 1 \
  --no-access-log

# Serve dist/ with nginx (see §8 below)
```

> **Workers must be 1.** SQLite with WAL mode supports concurrent reads but not concurrent writes from multiple processes. More than one Uvicorn worker will cause database corruption.

---

## 7. Health Check

```bash
curl http://127.0.0.1:8000/api/health
# Expected: {"status":"online","database":"healthy","version":"2.0.0"}
```

Set this endpoint as the health-check probe in any process manager, container orchestrator, or load balancer.

---

## 8. Nginx Configuration (example)

```nginx
server {
    listen 443 ssl http2;
    server_name your.domain.com;

    ssl_certificate     /etc/letsencrypt/live/your.domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your.domain.com/privkey.pem;

    # Serve Vite build output
    root /var/www/documind/dist;
    index index.html;

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API to Uvicorn
    location /api/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # Allow large PDF uploads
        client_max_body_size 55M;
    }

    # Deny direct access to data directory
    location /data/ { deny all; }
}

server {
    listen 80;
    server_name your.domain.com;
    return 301 https://$host$request_uri;
}
```

> Update CORS origins in `backend/main.py` to match your production domain — remove the `localhost` entries.

---

## 9. Persistent Storage

### What must persist

| Path | Contents | Consequence if lost |
|---|---|---|
| `data/documind.db` | All users, sessions, conversations, messages, document metadata, chunks | Complete data loss |
| `data/uploads/` | Uploaded PDF files (UUID filenames) | Documents unreadable; FAISS index orphaned |
| `data/indexes/` | FAISS `.faiss` and `.meta.json` files | Q&A unavailable; must re-upload to rebuild |

### Platform-specific notes

- **VPS / dedicated server**: mount a persistent disk at `/data` and point all three paths there.
- **Render, Railway, Fly.io**: use a persistent volume (not the ephemeral filesystem). Free tiers often reset the disk on sleep.
- **Docker**: mount a named volume at `/data` — do NOT rely on the container layer.
- **Heroku**: Heroku's filesystem is ephemeral. SQLite and local FAISS are not suitable. A full database migration to PostgreSQL + object storage would be required.

### What does NOT need to persist

- `dist/` — regenerated by `vite build`
- `node_modules/` — regenerated by `npm install`
- `.pytest_cache/`, `__pycache__/` — regenerated automatically

---

## 10. Backup Procedure

Run these commands from the server. Schedule them in cron or a process manager.

```bash
#!/usr/bin/env bash
# backup.sh — full DocuMind backup
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/documind_${TIMESTAMP}"
DATA_DIR="/data"    # adjust to your persistent volume path

mkdir -p "$BACKUP_DIR"

# 1. SQLite database (WAL-safe hot backup)
sqlite3 "$DATA_DIR/documind.db" ".backup '$BACKUP_DIR/documind.db'"

# 2. Uploaded PDFs
cp -r "$DATA_DIR/uploads/" "$BACKUP_DIR/uploads/"

# 3. FAISS indexes and metadata
cp -r "$DATA_DIR/indexes/" "$BACKUP_DIR/indexes/"

echo "Backup complete: $BACKUP_DIR"
```

**Important:** Always back up all three components together. An index file without its corresponding chunk metadata in the database will not work correctly.

### Restore procedure

```bash
# Stop the backend first
systemctl stop documind  # or your process manager command

# Restore database
cp /backups/documind_TIMESTAMP/documind.db /data/documind.db

# Restore uploads
rm -rf /data/uploads/
cp -r /backups/documind_TIMESTAMP/uploads/ /data/uploads/

# Restore indexes
rm -rf /data/indexes/
cp -r /backups/documind_TIMESTAMP/indexes/ /data/indexes/

# Restart the backend
systemctl start documind
```

---

## 11. Systemd Service (Linux)

Save as `/etc/systemd/system/documind.service`:

```ini
[Unit]
Description=DocuMind FastAPI backend
After=network.target

[Service]
Type=exec
User=documind
WorkingDirectory=/opt/documind
EnvironmentFile=/opt/documind/.env
ExecStart=/opt/documind/.venv/bin/uvicorn backend.main:app \
    --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable documind
systemctl start documind
systemctl status documind
```

---

## 12. Docker (single-container example)

> This is a starting point only. Review and harden before production use.

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source
COPY backend/ backend/
COPY .env.example .env.example

# Create data directories (override with volume mount)
RUN mkdir -p data/uploads data/indexes

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

```yaml
# docker-compose.yml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - documind_data:/app/data   # persistent volume
    restart: unless-stopped

  web:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./dist:/usr/share/nginx/html:ro
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - api
    restart: unless-stopped

volumes:
  documind_data:
```

Build the frontend before starting:

```bash
node node_modules/vite/bin/vite.js build
docker compose up -d
```

---

## 13. Remaining Blockers for Secure Public Deployment

1. **HTTPS** — must be configured before going public. Set `DOCUMIND_COOKIE_SECURE=true`.
2. **Strong session secret** — generate a minimum 32-character random secret.
3. **Persistent storage** — `data/` must survive restarts and redeployments.
4. **CORS origins** — update `backend/main.py` `allow_origins` to your production domain only.
5. **Rate limiting** — current in-memory implementation resets on restart; consider Redis for multi-restart resilience.
6. **Single worker** — only 1 Uvicorn worker is safe with SQLite.
7. **Data privacy review** — inform users that document text is sent to the Gemini API and ensure compliance with your organization's data policies.
