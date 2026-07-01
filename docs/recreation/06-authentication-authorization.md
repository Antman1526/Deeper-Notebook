# 06 — Authentication & Authorization

Exhaustive recreation reference for Open Notebook Plus auth, from the real
source on branch `desktop-app`. Paths are repo-relative to
`/Users/Antman/Desktop/OpenNotebook/open-notebook-Plus`.

> **This is dev-grade auth by design.** The whole model is a single shared
> password compared against `OPEN_NOTEBOOK_PASSWORD`, sent as an
> `Authorization: Bearer <password>` header. There are no users, sessions,
> JWTs, or roles. The desktop fork binds the API to `127.0.0.1` and typically
> leaves the password **unset** (auth disabled). See §7 for production hardening.

---

## 1. Model overview

```
Browser (Next.js)                    FastAPI (api/ @ :5055)                 SurrealDB
──────────────────                   ──────────────────────                ─────────
localStorage['auth-storage']         PasswordAuthMiddleware                 credential table
  { state: { token, … } }      ──►     compares Bearer token                  api_key encrypted
axios interceptor adds                 == OPEN_NOTEBOOK_PASSWORD               at rest (Fernet)
  Authorization: Bearer <token>        (constant-time)
401 → clear + redirect /login        /api/auth/status → { auth_enabled }
```

- **Credential = the password itself.** The frontend's "token" is literally the
  password string the user typed. It is validated by making a real API call
  (`GET /api/notebooks`), not by decoding a JWT.
- **No password set ⇒ auth off.** If `OPEN_NOTEBOOK_PASSWORD` is empty/unset,
  the middleware short-circuits and every request passes. The frontend detects
  this via `/api/auth/status` and marks itself authenticated with a sentinel
  token `'not-required'`.
- **Provider API keys are a separate concern** — encrypted at rest with Fernet
  and `OPEN_NOTEBOOK_ENCRYPTION_KEY` (see §5).

---

## 2. `PasswordAuthMiddleware` (backend)

**File:** `api/auth.py`.

The middleware reads the password once at construction via
`get_secret_from_env("OPEN_NOTEBOOK_PASSWORD")` (which also supports the Docker
secret pattern `OPEN_NOTEBOOK_PASSWORD_FILE`). Its `dispatch`:

1. **No password configured → bypass entirely** (`if not self.password`).
2. **Excluded path → bypass.**
3. **`OPTIONS` (CORS preflight) → bypass.**
4. Require an `Authorization` header (else `401 Missing authorization header`).
5. Require the `Bearer <password>` scheme (else `401 Invalid authorization header format`).
6. **Constant-time compare** the credential against the configured password via
   `_password_matches` (else `401 Invalid password`).
7. Otherwise `await call_next(request)`.

All 401s carry `WWW-Authenticate: Bearer`.

Verbatim core (`api/auth.py`):

```python
def _password_matches(provided: str, expected: str) -> bool:
    """Constant-time password comparison.
    ... secrets.compare_digest runs in time proportional to the *longer* of
    the two strings ... encode both sides to UTF-8 so Unicode passwords work
    AND remain timing-safe."""
    if not provided or not expected:
        return False
    return _secrets.compare_digest(
        provided.encode("utf-8"),
        expected.encode("utf-8"),
    )


class PasswordAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, excluded_paths: Optional[list] = None):
        super().__init__(app)
        self.password = get_secret_from_env("OPEN_NOTEBOOK_PASSWORD")
        self.excluded_paths = excluded_paths or [
            "/", "/health", "/livez", "/readyz", "/healthz/deep",
            "/metrics", "/docs", "/openapi.json", "/redoc",
        ]

    async def dispatch(self, request: Request, call_next):
        if not self.password:
            return await call_next(request)
        if request.url.path in self.excluded_paths:
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(status_code=401,
                content={"detail": "Missing authorization header"},
                headers={"WWW-Authenticate": "Bearer"})
        try:
            scheme, credentials = auth_header.split(" ", 1)
            if scheme.lower() != "bearer":
                raise ValueError("Invalid authentication scheme")
        except ValueError:
            return JSONResponse(status_code=401,
                content={"detail": "Invalid authorization header format"},
                headers={"WWW-Authenticate": "Bearer"})
        if not _password_matches(credentials, self.password):
            return JSONResponse(status_code=401,
                content={"detail": "Invalid password"},
                headers={"WWW-Authenticate": "Bearer"})

        return await call_next(request)
```

`api/auth.py` also exports an optional per-route dependency
`check_api_password(credentials=Depends(HTTPBearer(auto_error=False)))` with the
same semantics (returns `True` when no password is configured, raises 401
otherwise) — available for routes that want explicit protection.

### 2.1 Registration & excluded paths (production call-site)

**File:** `api/main.py` (~lines 709–741). The real registration passes a
**larger** exclusion list than the class default — health probes, launcher
control endpoints, and pre-auth splash polls:

```python
app.add_middleware(
    PasswordAuthMiddleware,
    excluded_paths=[
        "/", "/health", "/livez", "/readyz",
        "/healthz/deep",            # operators poll without auth
        "/api/healthz/deep",        # frontend reaches it via Next /api rewrite
        "/api/system/env-refresh",  # launcher uses its own control-token bearer
        "/docs", "/openapi.json", "/redoc",
        "/api/auth/status",
        "/api/config",
        "/api/version",             # launch splash polls before auth
        "/api/local-models/health", # launch splash polls before auth
        "/metrics",                 # Prometheus scrapes without auth
    ],
)
```

Middleware ordering matters. The full stack (registered inner→outer):
`PasswordAuthMiddleware` → `SelectiveGZipMiddleware` →
`SecurityHeadersMiddleware` → `PrometheusMetricsMiddleware` →
`RequestIDMiddleware` → `RateLimitMiddleware` → **`CORSMiddleware`
(outermost)**. CORS is outermost so preflight `OPTIONS` is handled before auth
would 401 it (`api/main.py` ~689–832).

### 2.2 `/api/auth/status`

**File:** `api/routers/auth.py` (registered at `api/main.py` with `prefix="/api"`
→ `/api/auth/status`, itself in the exclusion list). The whole endpoint:

```python
router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/status")
async def get_auth_status():
    auth_enabled = bool(get_secret_from_env("OPEN_NOTEBOOK_PASSWORD"))
    return {
        "auth_enabled": auth_enabled,
        "message": "Authentication is required" if auth_enabled
                   else "Authentication is disabled",
    }
```

### 2.3 CORS

**File:** `api/main.py`. `CORS_ORIGINS` (comma-separated) parses to a list;
unset ⇒ `["*"]` and `CORS_IS_DEFAULT_WILDCARD = True`. Critically,
`allow_credentials = not CORS_IS_DEFAULT_WILDCARD` — the browser rejects
`Access-Control-Allow-Origin: *` combined with credentials, so wildcard mode
disables credentialed CORS:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=not CORS_IS_DEFAULT_WILDCARD,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Startup emits a **WARNING** (downgraded from ERROR for the desktop fork, which
binds to `127.0.0.1`) when both `CORS_ORIGINS='*'` and `OPEN_NOTEBOOK_PASSWORD`
is unset — "ANYONE with the API URL can read/write every notebook."

---

## 3. Frontend auth store (Zustand)

**File:** `frontend/src/lib/stores/auth-store.ts`. Persisted via `persist` under
key **`auth-storage`** with `partialize` limiting storage to
`{ token, isAuthenticated }`. `onRehydrateStorage` flips `hasHydrated`.

Actions:

- **`checkAuthRequired()`** — `fetch(${apiUrl}/api/auth/status)` (cache:
  no-store). Sets `authRequired = data.auth_enabled`. If **not** required,
  immediately sets `{ isAuthenticated: true, token: 'not-required' }`. On a
  network error it sets `authRequired: null` (safe: don't assume) and a helpful
  message; other errors default `authRequired: true` (fail-closed).
- **`login(password)`** — validates by calling the real API, **not** JWT decode:

  ```ts
  const response = await fetch(`${apiUrl}/api/notebooks`, {
    method: 'GET',
    headers: { 'Authorization': `Bearer ${password}`, 'Content-Type': 'application/json' }
  })
  if (response.ok) {
    set({ isAuthenticated: true, token: password, isLoading: false,
          lastAuthCheck: Date.now(), error: null })
    return true
  }
  ```

  On failure it maps status → message (401 invalid password, 403 access denied,
  5xx server error) and clears the token.
- **`checkAuth()`** — re-validates the stored token against `GET /api/notebooks`.
  Guards: returns early if `isCheckingAuth` (race guard); returns false with no
  token; **30-second cache** (`if (isAuthenticated && lastAuthCheck && now -
  lastAuthCheck < 30000) return true`). On non-ok/error, clears the token.
- **`logout()`** — clears local state only. (No server session to invalidate —
  logout is purely client-side.)

---

## 4. Axios interceptor + `onpFetch` (Bearer + 401 handling)

**File:** `frontend/src/lib/api/client.ts`. Every request through `apiClient`:

```ts
apiClient.interceptors.request.use(async (config) => {
  if (!config.baseURL) {
    const apiUrl = await getApiUrl()
    config.baseURL = `${apiUrl}/api`
  }
  if (typeof window !== 'undefined') {
    const authStorage = localStorage.getItem('auth-storage')
    if (authStorage) {
      const { state } = JSON.parse(authStorage)
      if (state?.token) config.headers.Authorization = `Bearer ${state.token}`
    }
  }
  // FormData → drop Content-Type so the browser sets the multipart boundary
  if (config.data instanceof FormData) delete config.headers['Content-Type']
  else if (['post','put','patch'].includes((config.method||'').toLowerCase()))
    config.headers['Content-Type'] = 'application/json'
  return config
})
```

Response interceptor — **401 → clear + redirect to `/login`** (guarded so it
doesn't loop when already on `/login`); **5xx → deduped toast**:

```ts
if (status === 401) {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('auth-storage')
    if (window.location.pathname !== '/login') window.location.href = '/login'
  }
} else if (status >= 500 && status < 600 && !skipToast) { /* deduped sonner toast */ }
```

**`onpFetch`** (`frontend/src/lib/api/onp.ts`) is a parallel tiny wrapper for the
`/api/onp/*` endpoints (ThemeSwitcher, Gmail). It reads the same
`auth-storage` token, adds `Authorization: Bearer <token>`, and mirrors the
401 → clear + `/login` behavior (skipping the redirect if already on `/login`).

### 4.1 Route guards

- **Dashboard layout** (`app/(dashboard)/layout.tsx`) — client component that
  reads `useAuth()`; when resolved and `!isAuthenticated`, stashes the current
  path in `sessionStorage['redirectAfterLogin']` and `router.push('/login')`.
- **Login page** (`app/(auth)/login/page.tsx` → `components/auth/LoginForm.tsx`)
  — on mount (after hydration) calls `checkAuthRequired()`; if auth isn't
  required it redirects to `/notebooks`. If `authRequired === null` (couldn't
  connect) it renders a connection-error card with diagnostic info
  (version/apiUrl/buildTime) and a retry button. The password field has a
  show/hide toggle. `handleSubmit` just calls `login(password)`.

---

## 5. The Next 16 proxy — Setup Wizard redirect (NOT auth)

**File:** `frontend/src/proxy.ts` (renamed from `middleware.ts` in Next 16;
`middleware` → `proxy`, same `NextResponse` API and matcher shape). **This does
NOT enforce auth** — auth enforcement is the axios interceptor's job. The proxy
handles the **first-launch Setup Wizard** via a sentinel cookie:

```ts
const WIZARD_COMPLETED_COOKIE = 'wizard_completed'
const WIZARD_PATH = '/setup-wizard'
const EXEMPT_PREFIXES = [WIZARD_PATH, '/login', '/api', '/_next']

export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl
  for (const prefix of EXEMPT_PREFIXES) {
    if (pathname === prefix || pathname.startsWith(prefix + '/')) return NextResponse.next()
  }
  const completed = req.cookies.get(WIZARD_COMPLETED_COOKIE)?.value
  if (completed) return NextResponse.next()
  const url = req.nextUrl.clone()
  url.pathname = WIZARD_PATH
  return NextResponse.redirect(url)
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|gif|svg|webp|ico|css|js|map)$).*)'],
}
```

If `wizard_completed` is absent the user is sent to `/setup-wizard`, which reads
`/healthz/deep` and either auto-advances (healthy) or lets the user fix
subsystems and "Continue anyway" (degraded) — either way it sets the cookie
before releasing the user. The proxy can't poll `/healthz/deep` per navigation
(edge, no shared client state), hence the cookie sentinel.

---

## 6. Credential encryption (Fernet)

Provider API keys are encrypted at rest. **File:**
`open_notebook/utils/encryption.py`.

### 6.1 Key loading & rotation

- **`get_secret_from_env(var)`** checks `{VAR}_FILE` (Docker secret) first, then
  the plain env var.
- **`_get_encryption_keys_from_env()`** — priority:
  1. `OPEN_NOTEBOOK_ENCRYPTION_KEYS` (**plural**, comma-separated; first entry is
     the *primary* used for new encryption, the rest are decrypt-only —
     the rotation path).
  2. `OPEN_NOTEBOOK_ENCRYPTION_KEY` (**singular**, pre-rotation default).
  3. Both honor their `_FILE` variants.
  - **Raises `ValueError` if neither is set** — encrypted storage is unavailable
    until a key is configured.
- **No caching** — `_get_encryption_keys()` reads env per call so live rotation
  (uvicorn `--reload`, in-place env refresh) is immediately visible and the API
  + worker processes never diverge on a stale cached key.

The key string is an **arbitrary passphrase**, not a raw Fernet key. It's run
through a KDF to derive the 32-byte Fernet key.

### 6.2 KDF selection

`ONP_ENCRYPTION_KDF` picks the derivation:

- **`sha256`** (default, v0.7.0): `SHA-256(passphrase)` — instant, no work
  factor. Acceptable for a local desktop app.
- **`pbkdf2`** (v0.7.123, opt-in): PBKDF2-HMAC-SHA256, `600_000` iterations
  (OWASP 2024), deterministic salt derived from the passphrase +
  `onp-kdf-salt-v1` version tag. ~250 ms/guess — slows offline brute-force of a
  stolen DB from "instant" to years.

Decryption tries KDFs in `_KDF_DECRYPT_ORDER = ("pbkdf2", "sha256")` (selected
first), so migrating sha256→pbkdf2 keeps existing data readable.

### 6.3 encrypt / decrypt

- **`encrypt_value(value)`** → `get_multi_fernet().encrypt(...)`. `MultiFernet`
  encrypts with the **first** Fernet only (primary key × selected KDF).
- **`get_multi_fernet()`** builds Fernets for every `key × KDF` combination
  (`[primary×selected, primary×others, secondary×selected, …]`) so decryption
  transparently spans key rotation AND KDF migration.
- **`decrypt_value(value)`** tries every key×KDF. On `InvalidToken`:
  - if `looks_like_fernet_token(value)` → raise `ValueError` with rotation
    guidance ("ensure the OLD key is still in OPEN_NOTEBOOK_ENCRYPTION_KEYS");
  - else treat as **legacy plaintext** and return the value as-is.
  - On any other exception it logs the detail but raises a generic
    `"Decryption failed due to an internal error."` (audit S-5 — never echo
    `str(e)` to the API, which would leak crypto internals).
- **`looks_like_fernet_token(s)`** validates length ≥ ~100 chars, decoded ≥ 73
  bytes, first byte `0x80` (Fernet version), and ciphertext length a positive
  multiple of 16 — to avoid misclassifying plaintext as ciphertext.
- **`re_encrypt_value(value)`** decrypts with any key and re-encrypts with the
  primary — the per-row helper for a rotation sweep.

### 6.4 The `Credential` domain model

**File:** `open_notebook/domain/credential.py` (table `credential`). Fields:
`name`, `provider`, `modalities`, `api_key: Optional[SecretStr]`,
`decryption_error`, plus provider config (`base_url`, `endpoint`, `api_version`,
`endpoint_llm/embedding/stt/tts`, `project`, `location`, `credentials_path`).

- **Encrypt on save** — `_prepare_save_data()` extracts the `SecretStr` value
  and calls `encrypt_value()` before storage; skips `decryption_error`.
- **Decrypt on read** — `get()`, `get_all()`, and `_from_db_row()` call
  `decrypt_value()` and re-wrap in `SecretStr`. `get_all()` has **per-row error
  handling**: an undecryptable row becomes a placeholder credential with
  `decryption_error` set and `api_key = SecretStr("UNDECRYPTABLE")` rather than
  failing the whole list.
- The **plaintext key is never returned to the client** — the credential API
  exposes `has_api_key: boolean`, not the value.

### 6.5 Credentials router — status & migration

**File:** `api/routers/credentials.py` + `api/credentials_service.py`.

- `GET /credentials/status` → `get_provider_status()` returns
  `{ configured: {provider: bool}, source: {provider: 'database'|'environment'|'none'}, encryption_configured: bool }`.
  **`encryption_configured` is `True` if EITHER** the singular or plural key env
  var is set:

  ```python
  encryption_configured = bool(
      get_secret_from_env("OPEN_NOTEBOOK_ENCRYPTION_KEY")
      or get_secret_from_env("OPEN_NOTEBOOK_ENCRYPTION_KEYS")
  )
  ```

- `GET /credentials/env-status` → `{ provider: bool }` for env-configured keys.
- `POST /credentials/migrate-from-env` and
  `POST /credentials/migrate-from-provider-config` — call `require_encryption_key()`
  first (raises if no key), then create encrypted `Credential` rows from env vars
  / the legacy `ProviderConfig` singleton, returning
  `{ message, migrated, skipped, not_configured, errors }`. Create/update paths
  also gate on `require_encryption_key()`.
- **SSRF guard** — `validate_url()` (`credentials_service.py`) blocks link-local
  / cloud-metadata addresses but allows localhost/private IPs (self-hosted),
  re-invoked before outbound model discovery.

---

## 7. Production hardening notes

This model is explicitly dev-grade. To productionize:

1. **Set a strong `OPEN_NOTEBOOK_PASSWORD`** — without it, and with the default
   `CORS_ORIGINS='*'`, anyone who can reach the API has full read/write.
2. **Set `CORS_ORIGINS`** to your real frontend origin(s) so credentialed CORS
   turns on and cross-origin abuse is blocked.
3. **Set `OPEN_NOTEBOOK_ENCRYPTION_KEY`** (or the plural rotation list) so
   provider keys are encrypted at rest; prefer `ONP_ENCRYPTION_KDF=pbkdf2` if the
   DB could ever leave the machine.
4. **Replace the shared-password model** with real per-user auth (OAuth/JWT) —
   there are no users, sessions, roles, or server-side logout today; a leaked
   password is a full compromise and can't be revoked without changing the
   env var and restarting.
5. **Bind to `127.0.0.1`** (the desktop launcher already does) or put the API
   behind an authenticating reverse proxy; add **rate limiting** at the proxy
   (the built-in `RateLimitMiddleware` / `ONP_RATE_LIMIT_PER_MIN` is minimal).
6. **Rotate keys** with the plural env var + a `re_encrypt_value` sweep; keep
   the old key listed until the sweep completes.
