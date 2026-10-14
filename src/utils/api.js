/**
 * DocuMind centralized API client
 *
 * - All requests go to /api/* (Vite proxy forwards to FastAPI on :8000)
 * - Credentials (session cookie) are always included
 * - CSRF token is read from module-level state and sent as X-CSRF-Token header
 *   on every mutating request (POST/PATCH/DELETE/PUT)
 * - On 401, the global onUnauthorized callback is invoked so the app can
 *   redirect to login without circular imports
 * - Never logs passwords, session tokens, or document content
 */

let _csrfToken = null;
let _onUnauthorized = null;
const API_BASE = import.meta.env.VITE_API_URL || '';
export function setApiCsrfToken(token) {
  _csrfToken = token;
}

export function setOnUnauthorized(callback) {
  _onUnauthorized = callback;
}

// ── Low-level fetch wrapper ────────────────────────────────────────────────

async function request(method, path, body, opts = {}) {
  const headers = { ...opts.headers };

  if (body && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  if (['POST', 'PATCH', 'PUT', 'DELETE'].includes(method) && _csrfToken) {
    headers['X-CSRF-Token'] = _csrfToken;
  }

const res = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: 'include',  // always send session cookie
    headers,
    body: body instanceof FormData
      ? body
      : body != null ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    _onUnauthorized?.();
    throw new ApiError(401, 'Session expired. Please sign in again.');
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const json = await res.json();
      detail = json.detail || json.message || detail;
    } catch { /* ignore */ }
    throw new ApiError(res.status, detail);
  }

  // 204 No Content
  if (res.status === 204) return null;

  return res.json();
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

// ── Auth ───────────────────────────────────────────────────────────────────

export const auth = {
  me:       ()        => request('GET',  '/api/auth/me'),
  login:    (body)    => request('POST', '/api/auth/login', body),
  register: (body)    => request('POST', '/api/auth/register', body),
  logout:   ()        => request('POST', '/api/auth/logout'),
};

// ── Conversations ──────────────────────────────────────────────────────────

export const conversations = {
  list:    ()                  => request('GET',    '/api/conversations'),
  create:  (body)              => request('POST',   '/api/conversations',          body),
  get:     (id)                => request('GET',    `/api/conversations/${id}`),
  rename:  (id, title)         => request('PATCH',  `/api/conversations/${id}`,    { title }),
  delete:  (id)                => request('DELETE', `/api/conversations/${id}`),
  messages:(id)                => request('GET',    `/api/conversations/${id}/messages`),
  ask:     (id, question)      => request('POST',   `/api/conversations/${id}/ask`, { question }),
};

// ── Documents ─────────────────────────────────────────────────────────────

export const documents = {
  list:    (convId)            => request('GET',    `/api/conversations/${convId}/documents`),
  status:  (convId, docId)     => request('GET',    `/api/conversations/${convId}/documents/${docId}`),
  delete:  (convId, docId)     => request('DELETE', `/api/conversations/${convId}/documents/${docId}`),

  /**
   * Upload one or more File objects to a conversation.
   * Returns UploadResponse { results, accepted, failed }
   */
  upload: async (convId, files) => {
    const fd = new FormData();
    for (const f of files) fd.append('files', f, f.name);
    return request('POST', `/api/conversations/${convId}/documents`, fd);
  },
};

// ── Admin ──────────────────────────────────────────────────────────────────

export const admin = {
  users:          ()                   => request('GET',   '/api/admin/users'),
  createUser:     (body)               => request('POST',  '/api/admin/users',                    body),
  updateStatus:   (userId, status)     => request('PATCH', `/api/admin/users/${userId}/status`,   { status }),
  updateRole:     (userId, role)       => request('PATCH', `/api/admin/users/${userId}/role`,     { role }),
  auditLogs:      (limit = 100)        => request('GET',   `/api/admin/audit-logs?limit=${limit}`),
};

// ── Health ─────────────────────────────────────────────────────────────────

export const health = {
  check: () => request('GET', '/api/health'),
};
