# 06 — Authentication & Authorization System

> **Threat model first.** This is a single-user, local-first desktop app. Every service
> binds `127.0.0.1`. There are no user accounts, roles, or tenants. The adversaries that
> matter are: other local processes, malicious *content* (a hostile PDF or web page), and
> the network destinations the app is induced to contact. Authorization is therefore about
> **capability boundaries**, not identities.

---

## 1. API password (optional)

```python
# api/auth.py
security = HTTPBearer(auto_error=False)

def check_api_password(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> bool:
    """Supports Docker secrets via DEEPER_NOTEBOOK_PASSWORD_FILE.
    Returns True without checking credentials if DEEPER_NOTEBOOK_PASSWORD
    is not configured. Raises 401 if credentials are missing or don't match."""
    password = resolve_env("DEEPER_NOTEBOOK_PASSWORD", getter=get_secret_from_env)
    if not password:
        return True
    ...
```

- **Unset (desktop default):** open. The port is loopback-only; adding a password the user
  must type on every launch buys nothing against a local attacker who could read the
  password file anyway.
- **Set (Docker/LAN):** `Authorization: Bearer <password>` required; 401 otherwise.
- `*_FILE` indirection keeps the secret out of the environment table in container
  deployments.

Applied per route: `_authenticated: bool = Depends(check_api_password)`.

## 2. Credential storage — encryption at rest

Third-party API keys live in the `credential` table, encrypted with a key from the
environment.

```
DEEPER_NOTEBOOK_ENCRYPTION_KEY=change-me-to-a-secret-string     # ≥16 chars
DEEPER_NOTEBOOK_ENCRYPTION_KEYS=new-secret,old-secret          # rotation
DEEPER_NOTEBOOK_ENCRYPTION_KDF=                                 # KDF selection
```

**Rotation without re-entry:** the plural `KEYS` var takes an ordered list — first is the
new primary (used for all writes), the rest are accepted for decryption. Run the
re-encrypt sweep, then drop the old keys. This exists because the alternative — asking a
user to re-enter a dozen provider keys — guarantees they never rotate.

Keys are **never** logged. Error paths log the provider *name* and the exception text, on
the verified basis that these providers put the key in headers/body, not in the
exception's string form.

## 3. Capability boundaries (the real authorization model)

### 3.1 Outbound URL policy — fail-closed SSRF guard

`deeper_notebook/security/outbound_url.py` validates any user- or model-controlled URL
before fetch:

```python
MAX_URL_LENGTH = 2_048
ALLOWED_SCHEMES = frozenset({"http", "https"})

def _canonical_hostname(hostname: str) -> str:
    if not hostname or "%" in hostname or "\\" in hostname:
        _reject("URL hostname is malformed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        # Python's URL parser accepts legacy numeric forms that network stacks
        # interpret as IP literals. Refuse them instead of guessing.
        if hostname.lower().startswith("0x") or all(
            char in "0123456789abcdefABCDEFxX." for char in hostname
        ):
            _reject("URL hostname uses a non-canonical IP address")
        ...
```

It resolves the hostname and checks **every** returned address, so DNS rebinding to a
private range is refused. Deliberately separate from the MCP/credential validator: the
desktop may legitimately talk to a localhost MCP server, but a *web source* must never
reach the local network.

Consumers: `research/safe_fetch.py`, `research/discovery.py`, `utils/crawler.py`,
`study/assistant_service.py`, `api/routers/research.py`.

### 3.2 Model-callable tools cross the boundary

`add_web_source_to_notebook` lets the model ingest a URL. **Both** branches go through the
policy:

```python
if url_engine == "crawl4ai":
    # Crawl4AI may spawn browser subrequests. Fetch once through the policy
    # boundary and give it only the checked local response.
    checked_response = await fetch_public_url(url)
    content = await extract_url_with_crawl4ai(url, prefetched=checked_response)

if processed_state is None:
    # Do not delegate a raw URL to content-core, whose fetcher has a
    # different localhost policy.
    processed_state = await _extract_checked_url(content_state)
```

### 3.3 Study assistant network scope

Web research for the study assistant is scoped to an **owner-approved** allowlist, and —
critically — results are **post-filtered**, not merely `site:`-prefixed in the query:

```python
for item in evidence:
    url = str(_value(item, "url", ""))
    if len(url) > 512 or not StudyAssistantService._url_in_scope(url, scope):
        continue
    checked = await _maybe_await(self.url_validator(url))
    checked_url = str(_value(checked, "url", ""))
    if checked_url != url and not StudyAssistantService._url_in_scope(checked_url, scope):
        continue    # a redirect must ALSO land in scope
```

`_url_in_scope` requires `https`, rejects `.`/`..` path segments, normalises with
`posixpath.normpath`, and compares against approved authority + path prefix. This matters
because the keyless Wikipedia provider ignores `site:` operators entirely — the query
filter is advisory; the post-filter is the control.

### 3.4 Desktop shell navigation policy

The window is an app shell, not a browser. Settings are **pinned**, not inherited:

```python
def apply_webview_security_settings(webview) -> dict:
    desired = {
        "OPEN_EXTERNAL_LINKS_IN_BROWSER": True,   # links leave the shell
        "ALLOW_DOWNLOADS": False,                 # no page-initiated writes
        "OPEN_DEVTOOLS_IN_DEBUG": False,
    }
    settings = getattr(webview, "settings", None)
    if not isinstance(settings, dict):
        return {}
    ...   # only keys this pywebview defines are set (forward-compatible)
```

pywebview 5.4 already defaults `OPEN_EXTERNAL_LINKS_IN_BROWSER` to `True`; pinning makes
it *our* guarantee rather than a library default that could flip. The JS bridge exposes
exactly one method — `window.pywebview.api.relaunch`.

### 3.5 Feature flags as capability gates

Every visual route is guarded before any parsing:

```python
def _guard() -> None:
    if not source_visuals_enabled():
        raise HTTPException(status_code=404, detail=_FEATURE_UNAVAILABLE)
```

A test asserts the guard runs **before** source lookup or payload parsing, so a disabled
feature leaks nothing about record existence.

## 4. Injection defences

**SurrealQL.** Identifiers are whitelisted; values are always `$`-bound. Record ids are
parsed by `RecordID.parse` (`ensure_record_id`) before ever touching a query string.

**Memory shim id whitelist** — hostile ids are rejected at the boundary:

```python
bad_ids = ["abc'; DROP TABLE memory_fact;", "abc def",
           "abc\nDELETE memory_fact", "abc:other_id", ""]
# each must yield 4xx, or be refused client-side by the HTTP layer,
# and mem.delete must never be called
```

**Vector ids** in the Surreal memory store pass `_validate_vector_id` before interpolation.

## 5. Content-derived data is untrusted

Alt text, titles, and snippets from sources or the web are rendered as **text**, never
HTML. Wikipedia snippets are tag-stripped:

```python
snippet = unescape(re.sub(r"<[^>]+>", "", str(hit.get("snippet") or "")))
```

Visual assets are same-origin opaque WebP derivatives served from the app's own API — the
gallery never renders a remote image URL. Provenance is always displayed, and the product
rule is explicit: **a generated visual is a presentation aid, never evidence.**

## 6. Local model isolation

Sidecars bind `127.0.0.1` on ephemeral ports, are children of the launcher's process
group, and die with it. Credentials pointing at them are refreshed each launch, so a
stale port can't be reused by a different process.

## 7. What is deliberately absent

| Not implemented | Why |
|---|---|
| Multi-user accounts / RBAC | Single-user desktop product |
| OAuth for the app itself | No remote identity to federate |
| Rate limiting per user | `RATE_LIMIT_PER_MIN` exists for the server deployment |
| CSRF tokens | No cookie auth; bearer only |
| Notarization | Owner decision; local-signed identity only |

---

*Continues in [07 — Business Logic & Core Algorithms](./07-business-logic-core-algorithms.md).*
