"""Deeper Notebook Gmail digest integration.

User flow:
  1. User pastes their Google Cloud OAuth Client ID + Secret in Settings.
     (Creating an OAuth app is one-time setup at console.cloud.google.com.
     We can't ship shared client credentials in an open-source desktop app
     because Google's terms forbid it.)
  2. User clicks "Connect Gmail" and the canonical connect route redirects to the
     Google consent screen.
  3. Google redirects back to the canonical callback (or the retained legacy
     callback for existing registrations/in-flight state), where we exchange
     the code for access+refresh tokens and fetch the user's email address.
  4. User configures frequency + which sections to include.
  5. The namespace-relative /gmail/send-test route sends a digest right now
     works end-to-end.

Daily auto-send is a v0.6.1 follow-up (background scheduler). For v0.6 the
user clicks "Send digest now" when they want one.
"""

from __future__ import annotations

import asyncio
import base64
import html as _html
import logging
import secrets as _secrets
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import (  # noqa: F401  (List kept for back-compat consumers)
    Dict,
    List,
    Optional,
)
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from deeper_notebook.digest.scheduler import pending_digest_info
from deeper_notebook.domain.gmail import GmailIntegration
from deeper_notebook.identity import API_NAMESPACE, LEGACY_API_NAMESPACE, PRODUCT_NAME

log = logging.getLogger(__name__)

router = APIRouter(prefix="/gmail")


# Google OAuth scopes — we only need gmail.send. We do NOT request read access.
_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
_GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# CSRF protection: ephemeral state token in-memory. ONP is single-user, single-
# process so this dict is safe; in a multi-tenant API it'd need to move to
# session/redis.
_oauth_states: dict[str, datetime] = {}
# v0.8.66 (audit E-4) — serialize digest sends. The scheduler tick and a manual
# /send-test (or two overlapping scheduler ticks) could previously interleave
# into duplicate digest emails and race on the `last_sent_at` write. The lock is
# created LAZILY (not at import) and matches the v0.8.35d `_get_cache_lock`
# pattern in domain/gmail.py: a module-level `asyncio.Lock()` constructed at
# import binds to whatever loop first touches it, which deadlocks tests that run
# each case in a fresh event loop.
_SEND_LOCK: "asyncio.Lock | None" = None


def _get_send_lock() -> asyncio.Lock:
    global _SEND_LOCK
    if _SEND_LOCK is None:
        _SEND_LOCK = asyncio.Lock()
    return _SEND_LOCK


# ────────────────────────────────────────────────────────────────────────────────
# Request/response shapes
# ────────────────────────────────────────────────────────────────────────────────


class GmailStatusResponse(BaseModel):
    connected: bool
    email_address: Optional[str] = None
    has_client_credentials: bool
    enabled: bool
    frequency: str
    include_notebooks: bool
    include_sources: bool
    include_notes: bool
    include_podcasts: bool
    include_memory: bool
    last_sent_at: Optional[str] = None
    # v0.8.68 — True when a due digest was deferred because the machine is
    # offline; it sends automatically once connectivity returns.
    pending_digest: bool = False


class SaveCredentialsRequest(BaseModel):
    client_id: str = Field(..., min_length=10)
    client_secret: str = Field(..., min_length=10)


class UpdateSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    frequency: Optional[str] = None
    include_notebooks: Optional[bool] = None
    include_sources: Optional[bool] = None
    include_notes: Optional[bool] = None
    include_podcasts: Optional[bool] = None
    include_memory: Optional[bool] = None


class SendResult(BaseModel):
    ok: bool
    message: str
    items_included: int = 0


# ────────────────────────────────────────────────────────────────────────────────
# Status + settings
# ────────────────────────────────────────────────────────────────────────────────


@router.get("/status", response_model=GmailStatusResponse)
async def gmail_status() -> GmailStatusResponse:
    g = await GmailIntegration.get()
    return GmailStatusResponse(
        connected=g.is_connected,
        email_address=g.email_address,
        has_client_credentials=bool(g.client_id and g.client_secret),
        enabled=g.enabled,
        frequency=g.frequency,
        include_notebooks=g.include_notebooks,
        include_sources=g.include_sources,
        include_notes=g.include_notes,
        include_podcasts=g.include_podcasts,
        include_memory=g.include_memory,
        last_sent_at=g.last_sent_at.isoformat() if g.last_sent_at else None,
        # v0.8.68 — deferred-digest indicator (offline deferral, spec §5).
        pending_digest=pending_digest_info()["pending"],
    )


@router.post("/credentials")
async def save_credentials(body: SaveCredentialsRequest):
    """One-time setup: user pastes their Google Cloud OAuth credentials."""
    g = await GmailIntegration.get()
    g.client_id = body.client_id.strip()
    g.client_secret = body.client_secret.strip()
    await g.save()
    return {"ok": True}


@router.post("/settings")
async def update_settings(body: UpdateSettingsRequest):
    g = await GmailIntegration.get()
    if body.enabled is not None:
        g.enabled = body.enabled
    if body.frequency is not None:
        if body.frequency not in {"daily", "weekly", "manual"}:
            raise HTTPException(
                status_code=400, detail="frequency must be daily|weekly|manual"
            )
        g.frequency = body.frequency
    for field in (
        "include_notebooks",
        "include_sources",
        "include_notes",
        "include_podcasts",
        "include_memory",
    ):
        val = getattr(body, field)
        if val is not None:
            setattr(g, field, val)
    await g.save()
    return {"ok": True}


@router.post("/disconnect")
async def disconnect():
    """Wipe the access + refresh tokens. Keeps client_id/secret so re-connect
    doesn't require re-pasting OAuth credentials."""
    g = await GmailIntegration.get()
    g.access_token = None
    g.refresh_token = None
    g.token_expires_at = None
    g.email_address = None
    g.enabled = False
    await g.save()
    return {"ok": True}


@router.delete("/credentials")
async def forget_credentials():
    """Wipe BOTH the OAuth client credentials AND the tokens. Returns the
    integration to its 'fresh install' state. v0.6.1 — fixes the misnamed
    'Forget credentials' button that previously only toggled `enabled`."""
    g = await GmailIntegration.get()
    g.client_id = None
    g.client_secret = None
    g.access_token = None
    g.refresh_token = None
    g.token_expires_at = None
    g.email_address = None
    g.enabled = False
    await g.save()
    return {"ok": True}


# ────────────────────────────────────────────────────────────────────────────────
# OAuth flow
# ────────────────────────────────────────────────────────────────────────────────


@router.get("/connect")
async def connect(request: Request):
    """Redirect to Google's consent screen.

    Computes the OAuth redirect_uri from the current request's host so the
    callback lands back at the canonical Gmail callback on the same port.
    """
    g = await GmailIntegration.get()
    if not (g.client_id and g.client_secret):
        raise HTTPException(
            status_code=400,
            detail=(
                "Google OAuth client_id/client_secret not configured. Open "
                "Settings → Email Digests and paste credentials from your "
                "Google Cloud Console (Console → APIs & Services → "
                "Credentials → OAuth 2.0 Client IDs)."
            ),
        )

    # Build a CSRF state token, cleared on successful callback or after 10 min
    state = _secrets.token_urlsafe(24)
    _oauth_states[state] = datetime.now(timezone.utc) + timedelta(minutes=10)
    _purge_stale_states()
    # v0.8.66 (audit E-6) — hard cap as a backstop. `_purge_stale_states` keeps
    # only un-expired (<10 min) entries, so the map is already bounded by the
    # connect rate in a 10-min window — tiny for a single-user desktop app. The
    # cap defends the general/multi-user case: if a flood of `/connect`s without
    # callbacks ever outpaces the TTL, evict the oldest (insertion-order) first.
    _OAUTH_STATES_CAP = 256
    while len(_oauth_states) > _OAUTH_STATES_CAP:
        oldest = next(iter(_oauth_states))
        if oldest == state:
            break
        del _oauth_states[oldest]

    redirect_uri = _callback_url(request)
    params = {
        "client_id": g.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(_GMAIL_SCOPES + ["openid", "email"]),
        "access_type": "offline",  # so we get a refresh_token
        "prompt": "consent",  # force refresh_token re-issue
        "state": state,
    }
    return RedirectResponse(f"{_GOOGLE_AUTH_URL}?{urlencode(params)}")


@router.get("/callback", response_class=HTMLResponse)
async def callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """OAuth callback. Exchanges code for tokens + persists."""
    # v0.6.3 — Always purge stale states so an abandoned consent doesn't
    # leak memory across the day.
    _purge_stale_states()

    if error:
        log.warning("Gmail OAuth callback error from Google: %s", error)
        return _result_page(
            "Gmail connection cancelled", f"Google returned: {error}", ok=False
        )
    if not code or not state:
        return _result_page("Gmail connection failed", "Missing code/state.", ok=False)
    if state not in _oauth_states or _oauth_states[state] < datetime.now(timezone.utc):
        _oauth_states.pop(state, None)
        log.warning("Gmail OAuth state mismatch — possible CSRF or stale link")
        return _result_page(
            "Gmail connection failed",
            "OAuth state mismatch (possible CSRF or stale link). Try again.",
            ok=False,
        )
    _oauth_states.pop(state, None)

    g = await GmailIntegration.get()
    if not (g.client_id and g.client_secret):
        log.warning("Gmail OAuth callback: client credentials cleared mid-flow")
        return _result_page(
            "Gmail connection failed",
            "Client credentials were cleared mid-flow.",
            ok=False,
        )

    redirect_uri = _callback_url(request, preserve_callback_path=True)
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "client_id": g.client_id,
                    "client_secret": g.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
            r.raise_for_status()
            tok = r.json()
        except HTTPException:
            # v0.7.108 — re-raise typed HTTPExceptions so the next
            # `except Exception` doesn't clobber them to 500.
            raise
        except Exception as exc:
            # v0.8.24 — sanitize what we echo into the HTML response page
            # rendered in the user's browser. Same family as the v0.7.177
            # podcast_service sweep and the v0.8.22 credentials migration
            # sweep — gmail.py was missed. Google's token-exchange error
            # responses can include the OAuth client_id, the redirect_uri,
            # and (rarely) fragments of the auth code; surfacing them in
            # the browser tab leaks operator config beyond what the user
            # needs to triage. Full detail stays in log.exception above.
            log.exception("Gmail OAuth token exchange failed")
            return _result_page(
                "Gmail connection failed",
                f"Token exchange error ({type(exc).__name__}). "
                "Check launcher.log for details — the response from "
                "Google may contain config-specific information that "
                "is safer to inspect server-side.",
                ok=False,
            )

        access_token = tok.get("access_token")
        # Google commonly omits refresh_token on a repeat consent exchange.
        # Preserve the encrypted token already stored for this integration.
        refresh_token = tok.get("refresh_token") or g.refresh_token
        expires_in = int(tok.get("expires_in", 3600))
        if not access_token or not refresh_token:
            log.warning("Gmail token response missing access_token or refresh_token")
            return _result_page(
                "Gmail connection failed",
                "Google didn't return both access + refresh tokens. "
                "If you previously connected this app, revoke at "
                "https://myaccount.google.com/permissions and retry.",
                ok=False,
            )

        # Fetch the user's email address (so we know who to send digests TO)
        try:
            ui = await client.get(
                _GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            ui.raise_for_status()
            email = ui.json().get("email", "")
        except HTTPException:
            # v0.7.108 — re-raise typed HTTPExceptions so the next
            # `except Exception` doesn't clobber them to 500.
            raise
        except Exception as exc:
            log.warning("Gmail userinfo fetch failed (non-fatal): %s", exc)
            email = ""

    g.access_token = access_token
    g.refresh_token = refresh_token
    g.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    g.email_address = email
    await g.save()
    log.info("Gmail OAuth connection established for %s", email or "(unknown email)")
    return _result_page(
        "Gmail connected!",
        f"Connected as {email or 'your account'}. You can close this tab "
        f"and return to {PRODUCT_NAME}.",
        ok=True,
    )


@router.post("/send-test")
async def send_test() -> SendResult:
    """Send a digest immediately for testing. Same path as the scheduled send."""
    g = await GmailIntegration.get()
    if not g.is_connected:
        raise HTTPException(status_code=400, detail="Gmail not connected")
    try:
        ok, msg, n = await _send_digest_now(g, label="Test")
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as exc:
        # v0.8.24 — sanitize: same family as the v0.7.177 / v0.8.22 sweep.
        # `_send_digest_now` can raise from build_digest_html (DB errors
        # with SurrealDB internals) or from the Gmail API path before
        # the status-code branch is reached (network errors carrying
        # request URLs + Authorization-header fragments in the traceback).
        # The full error stays in launcher.log via log.exception below;
        # the client gets the type name for triage.
        log.exception("Gmail send-test failed")
        raise HTTPException(
            status_code=500,
            detail=f"Send-test failed ({type(exc).__name__}). "
            "Check launcher.log for the full error.",
        )
    return SendResult(ok=ok, message=msg, items_included=n)


# ────────────────────────────────────────────────────────────────────────────────
# Internals
# ────────────────────────────────────────────────────────────────────────────────


def _callback_url(request: Request, *, preserve_callback_path: bool = False) -> str:
    """Build redirect_uri from the request's host so it matches whatever
    port the dynamically-allocated upstream API is on."""
    base = str(request.base_url).rstrip("/")
    namespace = API_NAMESPACE
    if preserve_callback_path and request.url.path.startswith(
        f"{LEGACY_API_NAMESPACE}/"
    ):
        namespace = LEGACY_API_NAMESPACE
    return f"{base}{namespace}/gmail/callback"


def _purge_stale_states() -> None:
    now = datetime.now(timezone.utc)
    stale = [k for k, v in _oauth_states.items() if v < now]
    for k in stale:
        _oauth_states.pop(k, None)


def _result_page(title: str, body: str, ok: bool) -> HTMLResponse:
    """Tiny HTML page shown after OAuth flow completes.

    v0.6.3 — title/body are HTML-escaped because they include callback-time
    interpolations (exception messages, the email Google returned). Without
    escaping, a `<` in either field breaks the page; in principle hostile
    content could inject script tags too.
    """
    color = "#14B870" if ok else "#C44"
    safe_title = _html.escape(title)
    safe_body = _html.escape(body)
    return HTMLResponse(
        f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{safe_title}</title>
<style>
  body {{ font: 15px -apple-system, sans-serif; padding: 48px;
          max-width: 560px; margin: 0 auto; }}
  h1 {{ color: {color}; }} p {{ color: #555; line-height: 1.5; }}
  .hint {{ color: #888; font-size: 13px; margin-top: 24px; }}
</style></head><body>
  <h1>{safe_title}</h1>
  <p>{safe_body}</p>
  <p class="hint">Window closes automatically in 5 seconds.</p>
  <script>setTimeout(function(){{window.close()}}, 5000);</script>
</body></html>""",
        status_code=200,
    )


async def _refresh_access_token(g: GmailIntegration) -> bool:
    """Use the refresh_token to get a new access_token. Returns True on success.

    v0.6.3 — Google occasionally rotates the refresh_token in the refresh
    response (security policy, suspicious-activity recovery, etc). If we
    don't persist the new one, the NEXT refresh fails and the user has to
    reconnect. We now save it whenever Google returns one.
    """
    if not g.refresh_token or not g.client_id or not g.client_secret:
        log.warning("Gmail token refresh skipped: missing credentials or refresh_token")
        return False
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "client_id": g.client_id,
                    "client_secret": g.client_secret,
                    "refresh_token": g.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            r.raise_for_status()
            tok = r.json()
        except HTTPException:
            # v0.7.108 — re-raise typed HTTPExceptions so the next
            # `except Exception` doesn't clobber them to 500.
            raise
        except Exception as exc:
            log.warning("Gmail token refresh failed: %s", exc)
            return False
    new_access = tok.get("access_token")
    if not new_access:
        log.warning("Gmail token refresh: response missing access_token")
        return False
    g.access_token = new_access
    # If Google rotated the refresh_token, persist the new one.
    new_refresh = tok.get("refresh_token")
    if new_refresh and new_refresh != g.refresh_token:
        log.info("Gmail rotated refresh_token — persisting new value")
        g.refresh_token = new_refresh
    expires_in = int(tok.get("expires_in", 3600))
    g.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    await g.save()
    return True


async def _send_digest_now(
    g: GmailIntegration, label: str = "Digest"
) -> tuple[bool, str, int]:
    """Build + send a digest email under the single-flight send lock (E-4), so
    concurrent sends (scheduler + /send-test, or overlapping ticks) serialize
    and can't produce duplicate emails. Returns (ok, message, item_count)."""
    async with _get_send_lock():
        g_latest = await GmailIntegration.get()
        if label != "Test":
            from deeper_notebook.digest.scheduler import _should_send

            if not await _should_send(g_latest):
                log.info(
                    "digest-scheduler: already sent or no longer due after acquiring send lock"
                )
                return (True, "Already sent recently", 0)
        return await _send_digest_now_inner(g_latest, label)


async def _send_digest_now_inner(
    g: GmailIntegration, label: str = "Digest"
) -> tuple[bool, str, int]:
    """Build + send a digest email. Returns (ok, message, item_count)."""
    if g.needs_refresh:
        refreshed = await _refresh_access_token(g)
        if not refreshed:
            return (
                False,
                "Could not refresh OAuth token — try Disconnect + Connect again.",
                0,
            )

    # Build digest content from recent activity
    from deeper_notebook.digest import build_digest_html

    html, n = await build_digest_html(g)

    msg = MIMEMultipart("alternative")
    today = datetime.now(timezone.utc).strftime("%b %d, %Y")
    msg["Subject"] = f"[{PRODUCT_NAME}] {label} — {today}"
    msg["From"] = g.email_address or ""
    msg["To"] = g.email_address or ""
    msg.attach(MIMEText(_strip_html(html), "plain"))
    msg.attach(MIMEText(html, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            _GMAIL_SEND_URL,
            headers={
                "Authorization": f"Bearer {g.access_token}",
                "Content-Type": "application/json",
            },
            json={"raw": raw},
        )
        if r.status_code >= 300:
            # v0.8.66 (audit E-5) — don't echo the Gmail API response body to
            # the client: it can reflect request context (Authorization-header
            # fragments via traceback/formatting, the raw base64 message). Log
            # it for the operator; return only the status code. Mirrors the
            # v0.8.24 sanitization sweep.
            log.warning("Gmail send failed: HTTP %s — %s", r.status_code, r.text[:500])
            return (False, f"Gmail API error (HTTP {r.status_code}).", n)

    # v0.7.81 — guard the post-send save. The Gmail API call ALREADY
    # succeeded (status < 300) so we know the email left our process; if
    # `g.save()` then raises (DB blip, lock contention), the previous
    # code let the exception propagate, the scheduler's `_tick` caught
    # it as a "tick failure" and applied failure backoff, and then on
    # the next tick `last_sent_at` was still stale → we'd send the
    # SAME digest again (a duplicate email). Now we always return
    # success after a confirmed send and log loudly on save failure so
    # the duplicate window is bounded to one tick instead of every
    # tick until the DB recovers. The next successful save (whether via
    # this scheduler or any other mutation of GmailIntegration) will
    # persist the correct last_sent_at.
    g.last_sent_at = datetime.now(timezone.utc)
    try:
        await g.save()
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as save_exc:
        log.exception(
            "Gmail send succeeded but persist of last_sent_at failed — "
            "next scheduler tick may send a duplicate digest until DB "
            "recovers: %s",
            save_exc,
        )
    return (True, f"Sent to {g.email_address} ({n} items)", n)


def _strip_html(s: str) -> str:
    """Naive HTML-to-text for the plain-text MIME alternative."""
    import re

    txt = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", txt).strip()
