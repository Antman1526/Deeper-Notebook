# 14. Security Implementation

Exhaustive, code-grounded reference for every security control in **Open
Notebook Plus**. The app's design center is **privacy-first, self-hosted,
local-by-default** — most controls exist to keep user data on the machine and to
protect the one piece of long-lived secret material that unlocks everything else
(the Fernet encryption key).

> All API keys, tokens, and passwords in this document are shown as
> placeholders (`<...>` / `sk-...`). No real secret values appear here.

> **Version baseline**: app `v1.8.5`, `pydantic>=2.9.2`,
> `cryptography` (Fernet), `surrealdb>=1.0.4`, `fastapi>=0.104.0`.

---

## 14.1 Fernet Credential Encryption

File: `open_notebook/utils/encryption.py`.

Every API key and OAuth token stored in SurrealDB is encrypted at the field
level with **Fernet** (AES-128-CBC + HMAC-SHA256 authenticated encryption). The
module is the single source of truth for `encrypt_value` / `decrypt_value`.

### Key source (no default, lazy-loaded)

```python
def _get_encryption_keys_from_env() -> list[str]:
    # 1. OPEN_NOTEBOOK_ENCRYPTION_KEYS (plural, comma-separated) — rotation list
    multi = get_secret_from_env("OPEN_NOTEBOOK_ENCRYPTION_KEYS")
    if multi:
        keys = [k.strip() for k in multi.split(",") if k.strip()]
        if keys:
            return keys
    # 2. OPEN_NOTEBOOK_ENCRYPTION_KEY (singular) — pre-rotation default
    single = get_secret_from_env("OPEN_NOTEBOOK_ENCRYPTION_KEY")
    if single:
        return [single]
    raise ValueError("Neither OPEN_NOTEBOOK_ENCRYPTION_KEYS ... nor ... is set.")
```

- **No default key.** Encryption is unavailable until the env var is set; storing
  a credential without it raises. This prevents the catastrophic "hard-coded
  default key" anti-pattern.
- **Any string accepted.** A passphrase is derived to a valid 32-byte Fernet key
  via a KDF, so users can set `OPEN_NOTEBOOK_ENCRYPTION_KEY=<passphrase>`.
- **Docker secrets** via `get_secret_from_env` (lines 29-59): checks
  `<VAR>_FILE` first (reads the file), then the plain env var.

### Key Derivation Function (KDF) — SHA-256 vs PBKDF2 (v0.7.123)

```python
_KDF_PBKDF2_ITERATIONS = 600_000  # OWASP 2024 recommendation
_KDF_DECRYPT_ORDER = ("pbkdf2", "sha256")

def _ensure_fernet_key(key: str, kdf: str | None = None) -> str:
    kdf = (kdf or _selected_kdf()).lower()
    if kdf == "pbkdf2":
        return _derive_fernet_key_pbkdf2(key).decode()   # 600k iters, ~250ms/guess
    if kdf == "sha256":
        return _derive_fernet_key_sha256(key).decode()   # v0.7.0 default, fast
```

- **`ONP_ENCRYPTION_KDF=pbkdf2`** opts into 600,000-iteration PBKDF2-HMAC-SHA256,
  raising offline brute-force cost of a *stolen database* from "instant" to
  "~one year per million guesses." Default stays `sha256` for backward
  compatibility (existing data was encrypted with it).
- A deterministic, version-tagged salt (`_derive_kdf_salt`, salt version
  `onp-kdf-salt-v1`) is derived from the passphrase, so PBKDF2 is reproducible
  without storing a per-key salt blob.

### Key rotation via MultiFernet

```python
def get_multi_fernet() -> MultiFernet:
    keys = _get_encryption_keys()
    selected = _selected_kdf()
    kdf_order = (selected,) + tuple(k for k in _KDF_DECRYPT_ORDER if k != selected)
    fernets = [Fernet(_ensure_fernet_key(k, kdf).encode())
               for k in keys for kdf in kdf_order]
    return MultiFernet(fernets)   # encrypts with first, decrypts by trying each
```

`MultiFernet` encrypts with the *primary* (first) key but decrypts by trying
every key × every KDF in order. Rotation workflow (documented in
`re_encrypt_value`, lines 313-345): set
`OPEN_NOTEBOOK_ENCRYPTION_KEYS=<new>,<old>`, run a re-encrypt sweep over the
credentials table, then drop the old key.

### No caching — rotation must be live (v0.7.24)

```python
def _get_encryption_keys() -> list[str]:
    # v0.7.24 — no caching. A process-lifetime singleton masked a rotation
    # bug: under uvicorn --reload, updating ENCRYPTION_KEYS appeared to take
    # effect but the stale cached list kept using the old key; across API +
    # worker processes the caches diverged mid-rotation, producing
    # ciphertexts neither could later decrypt. Fernet construction is
    # microseconds — reading env per call is correct.
    return _get_encryption_keys_from_env()
```

### Graceful, leak-proof decryption

`decrypt_value` (lines 382-428) distinguishes three cases via
`looks_like_fernet_token` (a structural check: ≥100 chars, decoded ≥73 bytes,
Fernet version byte `0x80`, PKCS7-aligned ciphertext — `v0.6.15`):

1. Valid token → decrypt.
2. Looks like a token but no key works → raise a clear "rotate the key back"
   `ValueError`.
3. Not a token (legacy plaintext) → return as-is (backward compat).

Crucially (v0.8.66 audit S-5):

```python
except Exception as e:
    logger.error(f"Decryption failed: {e}")     # detail to logs only
    raise ValueError("Decryption failed due to an internal error. See server logs.")
```

The raw exception is **never** embedded in the raised `ValueError`, because that
message propagates into API responses on credential-read paths and could leak
Fernet/cryptography internals or input fragments.

---

## 14.2 `config.toml` File Permissions (0600)

File: `desktop/config.py` (`Config.save`, lines 42-65).

The desktop launcher's `~/.open-notebook-plus/config.toml` stores **both** the
SurrealDB password **and** the Fernet `encryption_key` that decrypts every saved
API key + Gmail OAuth token. With the default umask (022) the file would be
world-readable — any other local user on a shared machine could exfiltrate the
tokens. The fix (`v0.6.8`):

```python
def save(self, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)        # tighten parent dir (dir-listing reach)
    except OSError:
        pass                                 # non-fatal: read-only fs / Windows ACL
    ...
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(toml)
    try:
        os.chmod(tmp, 0o600)                 # owner read/write only
    except OSError:
        pass                                 # Windows: rely on ACLs
    os.replace(tmp, path)                     # atomic replace
```

Three properties:

- **`0o600` on the file**, **`0o700` on the parent directory** — owner-only.
- **Atomic write** (temp file + `os.replace`) so a crashed write never leaves a
  half-written, world-readable file behind.
- **Best-effort on Windows** — `chmod` failures are swallowed since Windows uses
  a different (ACL-based) permission model.

The `encryption_key` itself is generated with
`secrets.token_urlsafe(32)` and the SurrealDB password with
`secrets.token_urlsafe(24)` (lines 40, 87) — cryptographically strong random
defaults, never a hard-coded value.

---

## 14.3 SurrealDB Scoping

The DB connection authenticates as a configured user and selects an explicit
namespace + database before yielding (`open_notebook/database/repository.py`,
`db_connection` / `_new_connection`). Credentials resolve through
`get_database_password()` which falls back `SURREAL_PASSWORD` → legacy
`SURREAL_PASS`, and `get_database_url()` from `SURREAL_URL` or
`SURREAL_ADDRESS`/`SURREAL_PORT`.

Record-id discipline is the main query-safety control:

- **`ensure_record_id(value)`** (lines 339-343) coerces every external id through
  `RecordID.parse`, so a string id can't be interpolated raw into a query.
- **`repo_query(query_str, vars)`** uses **parameterized** SurrealQL (`$vars`),
  never string interpolation — the structural defense against SurrealQL
  injection. All domain models and routers go through it.

The desktop deployment runs SurrealDB **locally only** (bound to the host); it is
not exposed publicly. The stored function `fn::vector_search` and migrations are
the only privileged DB-side code, all version-controlled under
`open_notebook/database/migrations/`.

---

## 14.4 The Offline Gate (No Data Leaves the Machine When Offline)

Two cooperating modules guarantee that when the machine is offline — or the user
flips the Offline-mode toggle — no chat content is shipped to a cloud provider.

### Network state service

File: `open_notebook/health/network.py` (`v0.8.68`, see also doc 13.6). It
reports `online` / `offline` / `unknown` from a TTL-cached, off-loop TCP probe,
plus a DB-backed forced-offline toggle (`forced_offline_enabled`, 30s cache,
fails open).

### The provisioning offline gate

File: `open_notebook/ai/offline_gate.py`. It sits in
`provision_langchain_model`'s resolution path — the funnel every LangGraph
workflow uses:

```python
LOCAL_PROVIDERS = frozenset({"ollama", "openai_compatible"})

async def gate_language_model_id(candidate_id, *, fallback_out=None):
    record = await _get_model_record(candidate_id)        # loaded BEFORE the probe
    if record is None or getattr(record, "type", None) != "language":
        return candidate_id
    if _is_local(getattr(record, "provider", None)):
        return candidate_id                                # local: zero probes

    state = await get_network_state_with_settings()
    if state.status != "offline":                          # online AND unknown pass
        return candidate_id

    fallback = await find_local_language_model()
    if fallback is None:
        raise ConfigurationError(
            "You're offline and no local model is installed. Connect to the "
            "internet, or add a local model (Settings → Models) ...")
    return fallback.id                                     # substitute LOCAL model
```

Security-relevant properties:

- When **offline + candidate is a cloud provider**, the gate substitutes the best
  registered **local** model so the turn never reaches the network.
- **Fail-open for availability, fail-closed for privacy**: any internal error
  (DB hiccup, defaults fetch) returns the *original* candidate so the gate can't
  brick chat — but when the machine is genuinely offline it *will not* let a
  cloud call through; it substitutes local or raises.
- Local-provider candidates never even pay the probe cost (record loaded first).

This is reinforced by the **privacy gate** (`open_notebook/ai/privacy_gate.py`,
Phase 5.2a): a fail-closed, structured-secret detector that reroutes
auto-route *cloud* turns to local (or blocks) when the outbound content contains
API keys, SSNs, card numbers, emails, or `secret=` assignments — so a pasted
secret never leaves the device. Default OFF; enabled via `ONP_PRIVACY_GATE=on`.

---

## 14.5 Input Validation via Pydantic

All request bodies are **Pydantic v2** models (`api/models.py` and per-router
schemas), so malformed input is rejected at the FastAPI boundary with a 422
before any handler runs. Example (`api/routers/mcp.py`, lines 29-33):

```python
class MCPServerCreate(BaseModel):
    name: str
    url: str          # kept as str (not HttpUrl) so localhost/loopback work
    enabled: bool = True
```

Note the deliberate choice to keep `url` as `str` rather than `HttpUrl`: the app
*must* allow loopback/private URLs for self-hosted sidecars (Ollama, LM Studio),
so SSRF defense is applied as an explicit allow-list-aware validator (14.7)
rather than Pydantic's strict URL type. The global exception handlers in
`api/main.py` map typed exceptions to HTTP codes (`InvalidInputError`→400,
`ConfigurationError`→422, `AuthenticationError`→401, `RateLimitError`→429,
`NetworkError`/`ExternalServiceError`→502).

---

## 14.6 MCP Record-ID Parsing Hardening

File: `api/routers/mcp.py` (lines 12-24, 180-207).

`RecordID.parse` raises different exception types across SurrealDB client
versions. The `v0.8.66` H2/H3 hardening caught `(ValueError, TypeError)`, but
`surrealdb 2.0` raises its own `InvalidRecordIdError` (a `SurrealError`
subclass) — so a malformed id produced an opaque **500** instead of the intended
clean **400** (the bug fixed in `v0.8.68`):

```python
try:
    from surrealdb.errors import SurrealError as _SurrealIdError
except ImportError:                       # older clients
    class _SurrealIdError(Exception):
        pass

_BAD_RECORD_ID_ERRORS = (ValueError, TypeError, _SurrealIdError)

# ... in update / get-by-id handlers:
try:
    rid = ensure_record_id(server_id)
except _BAD_RECORD_ID_ERRORS:
    raise HTTPException(400, "Invalid server_id")
```

The library error class is caught alongside the stdlib ones, with an
`ImportError` fallback so a future client that drops the module path still
imports. This both fixes the 500 and avoids leaking a stack trace for attacker-
supplied ids.

---

## 14.7 SSRF Protection on URL Inputs

File: `api/credentials_service.py`, `validate_url(url, provider)` (lines 99+).

User-supplied URLs (credential `base_url`/`endpoint`, MCP server URL) are run
through an SSRF validator that is **intentionally permissive about private IPs**
(self-hosted services need them) but **blocks the dangerous classes**:

- **Scheme allow-list**: only `http`/`https` (line 131) — blocks `file://`,
  `gopher://`, etc.
- **Link-local blocked** (`169.254.x.x`, `ip.is_link_local`, line 147) — this is
  the cloud metadata endpoint (`169.254.169.254`), the classic SSRF
  credential-theft target.
- **IPv4-mapped IPv6 bypass blocked** (line 155):
  `::ffff:169.254.169.254` is caught via `ip.ipv4_mapped.is_link_local`.
- **DNS-rebinding guard**: hostnames are resolved and the resolved IP is
  re-checked for link-local (lines 163-178), so a hostname that *resolves* to
  metadata is rejected.

It is invoked off-loop from async handlers:
`await asyncio.to_thread(validate_url, body.url, "mcp")`
(`api/routers/mcp.py:128`) because resolution blocks. A `ValueError` becomes a
clean `HTTPException(400)`.

---

## 14.8 Secrets Never Logged (SecretStr)

API keys live in memory as Pydantic **`SecretStr`**, whose `repr`/`str` render
as `**********` — so an accidental log line or stack-trace dump can't leak the
value. From `open_notebook/domain/provider_config.py`:

```python
from pydantic import SecretStr

api_key: Optional[SecretStr] = None
...
data["api_key"] = encrypt_value(self.api_key.get_secret_value())   # explicit unwrap only
...
api_key = SecretStr(data["api_key"])                               # re-wrap on DB read
```

The plaintext is reachable only via the explicit `.get_secret_value()` call,
which happens exactly at the encrypt boundary. The credentials API additionally
**never returns the key value** — only metadata + `has_api_key: bool`
(`api/CLAUDE.md`, Credential Management). The decrypt-error path (14.1) logs
detail but never returns it.

---

## 14.9 Privacy-First Stance + Prompt-Optimizer Offline Gate

The whole product is "an open-source, privacy-focused alternative to Google's
NotebookLM" with "complete control over data" (root `CLAUDE.md`). Concretely:

- **Local-by-default models** — `ollama` and `openai_compatible` (the llama.cpp
  sidecar) are the privileged local providers; everything else is treated as
  cloud and gated when offline.
- **Web search short-circuits offline** (Task 7) and the **Gmail digest defers
  offline** (Task 8) — no outbound calls when the user is offline.

The **prompt optimizer (SkillOpt)** carries the same stance
(`open_notebook/prompt_optimizer/runner.py`, lines 1-9):

```python
"""... Runs fully local with local models — in keeping with the app's
privacy-first stance, no data leaves the machine unless the chosen models
are cloud models (the caller gates that)."""
```

Both the target (runs the prompt) and the optimizer (judges + proposes edits)
are configured as openai-compatible endpoints, which transparently covers the
local llama.cpp sidecar. When the user selects local models, the entire training
run — including every prompt sample and judge call — stays on the machine.

---

## 14.10 Known Dev-Only-Auth Caveat + Production Hardening

### Current state (documented as insecure)

Authentication is a single shared password checked by
`PasswordAuthMiddleware` (`api/auth.py`). Root `CLAUDE.md` states plainly:
"**Current**: Simple password middleware (insecure, dev-only). **Production**:
Replace with OAuth/JWT."

What it *does* get right:

- **Constant-time comparison** (`_password_matches`, lines 13-34, `v0.6.7`):
  `secrets.compare_digest` instead of `!=`, preventing a timing oracle that
  could leak the password char-by-char. UTF-8 encoded first so Unicode
  passwords stay timing-safe instead of raising `TypeError`.
- **Docker secrets** via `OPEN_NOTEBOOK_PASSWORD_FILE`.
- Default password `open-notebook-change-me` (must be overridden via
  `OPEN_NOTEBOOK_PASSWORD`).

### Known caveats (from `api/CLAUDE.md`)

- **No per-notebook / per-user permission checks** — every authenticated request
  trusts the auth layer; there is no row-level authorization.
- **CORS open by default** (`*`) in dev (`api/main.py`, `CORS_ALLOWED_ORIGINS`);
  the wildcard is flagged (`CORS_IS_DEFAULT_WILDCARD`).
- **No built-in rate limiting** — must be added at a proxy.
- **OpenAPI docs (`/docs`) unauthenticated** — disable before public exposure.

### Recommended production hardening

1. Replace `PasswordAuthMiddleware` with OAuth2/OIDC or JWT bearer auth, with
   per-user identity and a real session model.
2. Add row-level authorization (notebook/source ownership) at the domain layer.
3. Set `CORS_ORIGINS` to an explicit allow-list (never `*`); the value is parsed
   once at module load so it requires a restart.
4. Front the API with a reverse proxy enforcing TLS, rate limiting, and request
   size limits.
5. Set `OPEN_NOTEBOOK_ENCRYPTION_KEY` (or a `_FILE` Docker secret) and switch
   `ONP_ENCRYPTION_KDF=pbkdf2` so a stolen DB resists offline brute force.
6. Enable the privacy gate (`ONP_PRIVACY_GATE=on`) if any cloud model is in use.
7. Disable interactive API docs (`/docs`, `/redoc`) or place them behind auth.
8. Keep SurrealDB bound to localhost; never expose its port publicly.

> The desktop build mitigates much of the auth weakness by binding all services
> to the local host and never exposing them — the threat model there is "another
> local user on a shared Mac," addressed by the `0600`/`0700` config-file
> permissions (14.2). The hardening list above applies to any networked/server
> deployment.
