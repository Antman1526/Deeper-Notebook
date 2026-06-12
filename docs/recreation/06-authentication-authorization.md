# 06 — Authentication & Authorization

> Recreation reference for the auth/security model of **Open Notebook Plus**.
> Covers the password middleware, the frontend auth interceptor + token storage,
> the first-run Setup Wizard + `proxy.ts` cookie gate, Fernet credential encryption,
> and the dev-only nature of the model plus a production-hardening path.
>
> **All keys/passwords below are placeholders.** Never commit real values.

---

## 1. Security model overview

Open Notebook Plus is **single-user, local-first**. There is **one shared password** for
the whole API, no per-user identity, no roles, and no per-notebook permission checks — every
authenticated caller can read/write everything. The desktop launcher binds the API to
`127.0.0.1` only, so this is acceptable for the desktop fork but **must be hardened before any
networked deployment** (§7).

Two independent secrets:

| Env var | Used for |
|---|---|
| `OPEN_NOTEBOOK_PASSWORD` | API access (the "auth" the user types in the login screen) |
| `OPEN_NOTEBOOK_ENCRYPTION_KEY` / `OPEN_NOTEBOOK_ENCRYPTION_KEYS` | Fernet encryption of stored provider API keys |

Both support the Docker-secrets `*_FILE` pattern via `get_secret_from_env()`.

---

## 2. Backend: `PasswordAuthMiddleware` (`api/auth.py`)

A Starlette `BaseHTTPMiddleware` registered first in the stack (innermost), gating every
request not in `excluded_paths`.

```python
class PasswordAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, excluded_paths: Optional[list] = None):
        super().__init__(app)
        self.password = get_secret_from_env("OPEN_NOTEBOOK_PASSWORD")
        self.excluded_paths = excluded_paths or [
            "/", "/health", "/livez", "/readyz", "/healthz/deep",
            "/metrics", "/docs", "/openapi.json", "/redoc",
        ]

    async def dispatch(self, request: Request, call_next):
        if not self.password:                       # no password set → AUTH DISABLED
            return await call_next(request)
        if request.url.path in self.excluded_paths:
            return await call_next(request)
        if request.method == "OPTIONS":             # CORS preflight bypass
            return await call_next(request)
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(401, {"detail": "Missing authorization header"},
                                headers={"WWW-Authenticate": "Bearer"})
        scheme, credentials = auth_header.split(" ", 1)   # "Bearer {password}"
        if scheme.lower() != "bearer":
            return JSONResponse(401, {"detail": "Invalid authorization header format"}, ...)
        if not _password_matches(credentials, self.password):
            return JSONResponse(401, {"detail": "Invalid password"}, ...)
        return await call_next(request)
```

### 2.1 Key behaviors

- **No password set ⇒ no auth.** If `OPEN_NOTEBOOK_PASSWORD` is unset, the middleware is a pass-through. `main.py` logs a WARNING when this combines with wildcard CORS (downgraded ERROR→WARNING for the desktop fork since the API is `127.0.0.1`-bound).
- **Bearer scheme**: clients send `Authorization: Bearer {password}` — the password itself *is* the token (no JWT, no session).
- **Constant-time compare** (`_password_matches`, v0.6.7): uses `secrets.compare_digest` on UTF-8-encoded bytes (supports Unicode passwords, avoids byte-by-byte timing leaks). Empty inputs return `False`.

```python
def _password_matches(provided: str, expected: str) -> bool:
    if not provided or not expected:
        return False
    return _secrets.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))
```

### 2.2 Excluded (auth-exempt) paths

`main.py` constructs the middleware with the full production list, including: `/`, `/health`,
`/livez`, `/readyz`, `/healthz/deep`, `/api/healthz/deep`, `/api/system/env-refresh`
(own bearer auth), `/docs`, `/openapi.json`, `/redoc`, `/api/auth/status`, `/api/config`,
`/api/version`, `/api/local-models/health`, `/metrics`. The class default mirrors a subset so a
bare `PasswordAuthMiddleware(app)` doesn't 401 health probes.

### 2.3 Auth-status endpoint (`api/routers/auth.py`)

```python
@router.get("/status")          # mounted → GET /api/auth/status (auth-exempt)
async def get_auth_status():
    auth_enabled = bool(get_secret_from_env("OPEN_NOTEBOOK_PASSWORD"))
    return {"auth_enabled": auth_enabled,
            "message": "Authentication is required" if auth_enabled
                       else "Authentication is disabled"}
```

The frontend polls this on startup to decide whether to show the login screen.

### 2.4 Optional per-route dependency

`check_api_password()` (FastAPI `Depends`) exists for individual routes but the global
middleware is the primary gate. The `/api/system/env-refresh` endpoint enforces its **own**
bearer using `OPEN_NOTEBOOK_LAUNCHER_CONTROL_TOKEN` (the launcher↔API trust boundary), since
the launcher doesn't hold the user password. `/metrics` optionally enforces
`ONP_METRICS_AUTH_TOKEN`.

---

## 3. Frontend: auth interceptor + token storage

### 3.1 Token storage

The password (used as the bearer token) is persisted by Zustand `persist` to localStorage
under **`auth-storage`**, with `partialize` limiting it to `{ token, isAuthenticated }`
(`src/lib/stores/auth-store.ts`). There is no httpOnly cookie — the token is readable by JS.

### 3.2 Request interceptor (`src/lib/api/client.ts`)

```ts
const authStorage = localStorage.getItem('auth-storage')
if (authStorage) {
  const { state } = JSON.parse(authStorage)
  if (state?.token) config.headers.Authorization = `Bearer ${state.token}`
}
```

### 3.3 401 response interceptor

```ts
if (status === 401) {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('auth-storage')
    if (window.location.pathname !== '/login') window.location.href = '/login'
  }
}
```

Clears the token and redirects to `/login` (guarded against a `/login → /login` loop, v0.6.20).

### 3.4 Login flow (`auth-store.ts`)

`login(password)` validates by calling `GET /api/notebooks` with `Authorization: Bearer {password}`.
A `200` stores the token; `401`/`403`/`5xx` set a friendly error. `checkAuth()` re-validates the
same endpoint (30s cache, race-guarded by `isCheckingAuth`). **No JWT is decoded** — auth is a
live API check. Client-side `logout()` only clears the local token; there is no server session
to invalidate.

---

## 4. First-run Setup Wizard + `proxy.ts` cookie gate

`src/proxy.ts` is the Next.js 16 edge **proxy** (renamed from `middleware.ts`; same
`NextResponse` API and matcher). It does **not** enforce auth — it only redirects first-launch
users to the Setup Wizard.

```ts
const WIZARD_COMPLETED_COOKIE = 'wizard_completed'
const WIZARD_PATH = '/setup-wizard'
const EXEMPT_PREFIXES = [WIZARD_PATH, '/login', '/api', '/_next']

export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl
  for (const prefix of EXEMPT_PREFIXES)
    if (pathname === prefix || pathname.startsWith(prefix + '/'))
      return NextResponse.next()
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

**Why a cookie, not a health check**: the proxy runs at the edge with no shared client state;
fetching `/healthz/deep` on every navigation would add a round-trip per request. The sentinel
cookie `wizard_completed` short-circuits that. The wizard page itself reads `/healthz/deep`
(via `useDeepHealth`), auto-advances when healthy or lets the user fix subsystems and
"Continue anyway" when degraded, then sets the cookie before sending the user on. (Backend
quirk: the wizard's deep-health poll resolves to `/api/healthz/deep`, which is why `main.py`
adds that alias + auth exemption — v0.7.148.)

---

## 5. Credential encryption (Fernet)

Provider API keys are encrypted at rest in SurrealDB. Two modules cooperate:
`open_notebook/utils/encryption.py` (crypto) and `open_notebook/domain/credential.py` (model).

### 5.1 `encryption.py` — Fernet over a derived key

Fernet = AES-128-CBC + HMAC-SHA256 authenticated encryption. The user supplies **any string**;
a 32-byte Fernet key is derived from it.

**Key source priority** (`_get_encryption_keys_from_env`):
1. `OPEN_NOTEBOOK_ENCRYPTION_KEYS` (plural, comma-separated) — first entry is *primary* (new encryption), the rest are decrypt-only (rotation).
2. `OPEN_NOTEBOOK_ENCRYPTION_KEY` (singular).
3. Both honor the Docker `*_FILE` variant. If none set → `ValueError`.

Keys are read **per call** (no caching) so live rotation under `--reload` is always visible.

**Key derivation** — selectable via `ONP_ENCRYPTION_KDF`:

```python
def _ensure_fernet_key(key: str, kdf: str | None = None) -> str:
    kdf = (kdf or _selected_kdf()).lower()       # default 'sha256'
    if kdf == "pbkdf2":  return _derive_fernet_key_pbkdf2(key).decode()  # 600k iters, OWASP 2024
    if kdf == "sha256":  return _derive_fernet_key_sha256(key).decode()  # v0.7.0, fast
    raise ValueError(...)
```

- `sha256` (default): `base64.urlsafe_b64encode(sha256(key))` — instant, but instant to brute-force if the DB leaks.
- `pbkdf2` (opt-in, v0.7.123): PBKDF2-HMAC-SHA256, 600,000 iterations, deterministic salt from `sha256(key + "\0onp-kdf-salt-v1")[:16]` (~250ms/guess).

**Rotation + cross-KDF decrypt** via `MultiFernet`:

```python
def get_multi_fernet() -> MultiFernet:
    keys = _get_encryption_keys()
    selected = _selected_kdf()
    kdf_order = (selected,) + tuple(k for k in _KDF_DECRYPT_ORDER if k != selected)
    fernets = [Fernet(_ensure_fernet_key(k, kdf).encode())
               for k in keys for kdf in kdf_order]
    return MultiFernet(fernets)                  # encrypts with first, decrypts by trying each
```

Public API:

```python
def encrypt_value(value: str) -> str:            # encrypts with primary key × selected KDF
    return get_multi_fernet().encrypt(value.encode()).decode()

def decrypt_value(value: str) -> str:            # tries all keys × KDFs
    mf = get_multi_fernet()
    try:
        return mf.decrypt(value.encode()).decode()
    except InvalidToken:
        if looks_like_fernet_token(value):
            raise ValueError("Decryption failed: data appears encrypted but no key can decrypt it…")
        return value                             # legacy plaintext passthrough

def re_encrypt_value(value: str) -> str:         # decrypt with any key → re-encrypt with primary (rotation sweep)
```

- **`looks_like_fernet_token()`** sniffs the Fernet structure (≥73 decoded bytes, version byte `0x80`, ciphertext multiple of 16) to distinguish ciphertext from legacy plaintext — so unencrypted legacy data round-trips unchanged.
- **Sanitized errors** (v0.8.66): on an unexpected decrypt failure the detail is logged but the raised `ValueError` is generic ("Decryption failed due to an internal error. See server logs.") to avoid leaking crypto internals into API responses.

**Rotation procedure**: set `OPEN_NOTEBOOK_ENCRYPTION_KEYS=<new>,<old>` → run a sweep calling
`re_encrypt_value()` over every stored ciphertext → drop `<old>`.

### 5.2 `credential.py` — the `Credential` domain model

One SurrealDB `credential` record per provider account (replaced the old `ProviderConfig`
singleton). `api_key` is a Pydantic `SecretStr` (masked in logs/repr).

```python
class Credential(ObjectModel):
    table_name: ClassVar[str] = "credential"
    name: str
    provider: str
    modalities: list[str] = []
    api_key: Optional[SecretStr] = None
    decryption_error: Optional[str] = None
    base_url / endpoint / api_version / endpoint_llm / endpoint_embedding /
    endpoint_stt / endpoint_tts / project / location / credentials_path: Optional[str]
```

**Encrypt on save** (`_prepare_save_data`):

```python
if key == "api_key":
    if self.api_key:
        data["api_key"] = encrypt_value(self.api_key.get_secret_value())
    else:
        data["api_key"] = None
```

**Decrypt on read** (`get`, `get_all`, `_from_db_row`):

```python
@classmethod
async def get(cls, id: str) -> "Credential":
    instance = await super().get(id)
    if instance.api_key:
        raw = instance.api_key.get_secret_value() if isinstance(instance.api_key, SecretStr) else instance.api_key
        object.__setattr__(instance, "api_key", SecretStr(decrypt_value(raw)))
    return instance
```

`get_all()` decrypts per-row with isolation: a row whose key can't be decrypted (e.g. the
encryption key changed) yields a placeholder credential with `decryption_error` set and
`api_key = SecretStr("UNDECRYPTABLE")` rather than failing the whole list.

`to_esperanto_config()` builds the dict passed to Esperanto's `AIFactory.create_*()` (api_key
extracted from `SecretStr`, plus provider-specific fields; Azure maps `base_url → endpoint`).

### 5.3 How API keys flow into providers

`open_notebook/ai/key_provider.py` provisions DB credentials into env vars for Esperanto
("database-first, env fallback"): `provision_provider_keys(provider)` checks DB then env;
`get_api_key(provider)` returns DB-first; `provision_all_keys()` loads all. The
`credentials` router **never returns api_key values** — only metadata (`has_api_key`,
`model_count`, base_url, etc.).

### 5.4 Startup encryption check

`main.py` lifespan warns (does not fail) if neither `OPEN_NOTEBOOK_ENCRYPTION_KEY` nor
`OPEN_NOTEBOOK_ENCRYPTION_KEYS` is set — credential encryption then fails on first write.

---

## 6. Authorization model

There is **none beyond the single password**. No users, roles, scopes, or per-resource
checks. Every authenticated request can touch every notebook/source/note/credential. This is
intentional for the single-user desktop app; the `api/CLAUDE.md` flags it as a quirk
("Services don't validate user permission").

---

## 7. Dev-only nature & production-hardening path

The codebase documents the auth as **dev-only** in multiple places (root `CLAUDE.md`:
"Simple password middleware (insecure, dev-only)"; `api/CLAUDE.md`: "PasswordAuthMiddleware
is basic; production deployments should replace with OAuth/JWT").

| Risk (current) | Hardening |
|---|---|
| Single shared password, no identity | Replace `PasswordAuthMiddleware` with OAuth2 / OIDC / JWT; add a real user table |
| No authorization / per-resource scoping | Add per-user ownership + permission checks on notebooks/sources |
| Token in localStorage (XSS-readable) | Move to httpOnly, `Secure`, `SameSite` cookies; add CSRF protection |
| CORS `*` default | Set `CORS_ORIGINS=https://your-frontend.example.com` (enables credentialed CORS) |
| No password set ⇒ open API | Always set a strong `OPEN_NOTEBOOK_PASSWORD`; `main.py` warns on the `CORS=* + no-password` combo |
| OpenAPI docs (`/docs`, `/openapi.json`, `/redoc`) auth-exempt | Disable or gate docs in production |
| No rate limiting by default | Enable `ONP_RATE_LIMIT_PER_MIN` (or add at the reverse proxy) |
| `sha256` KDF (fast brute-force if DB leaks) | Set `ONP_ENCRYPTION_KDF=pbkdf2` and run a `re_encrypt_value` sweep |
| Encryption key in plain env | Use the `*_FILE` Docker-secrets pattern; rotate via `OPEN_NOTEBOOK_ENCRYPTION_KEYS` |
| API bound to `127.0.0.1` (desktop) | For networked deploys, terminate TLS at a reverse proxy and never expose `:5055` directly |

The desktop fork's mitigation is network isolation: the launcher spawns the API with
`--host 127.0.0.1`, so "anyone with the API URL" can't reach it off-machine — which is why the
`CORS=* + no-password` warning is logged at WARNING rather than ERROR for this build.
