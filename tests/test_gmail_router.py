"""ONP v0.6.3 — Tests for the Gmail OAuth router.

Covers pure helpers — _result_page HTML escaping, _purge_stale_states.
The full OAuth round-trip and the network-bound _refresh_access_token are
intentionally NOT covered here (would require mocking httpx + Google);
that's left for a future integration suite.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from api.routers import gmail as gmail_mod


def test_result_page_escapes_title_and_body():
    """Hostile content in title or body must not break out as raw HTML."""
    page = gmail_mod._result_page(
        title="<script>alert('t')</script>",
        body="<img src=x onerror=alert('b')>",
        ok=False,
    )
    html = page.body.decode("utf-8")
    # Raw tags absent…
    assert "<script>alert('t')</script>" not in html
    assert "<img src=x onerror=alert('b')>" not in html
    # …escaped versions present.
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x onerror=alert(&#x27;b&#x27;)&gt;" in html
    # Title still rendered (escaped) inside <h1> and <title>.
    assert "<h1>" in html and "<title>" in html


def test_result_page_color_reflects_ok_flag():
    ok_page = gmail_mod._result_page("Connected!", "yay", ok=True).body.decode()
    fail_page = gmail_mod._result_page("Failed", "boo", ok=False).body.decode()
    assert "#14B870" in ok_page  # green
    assert "#C44" in fail_page  # red


def test_purge_stale_states_drops_expired_entries():
    """_purge_stale_states removes entries whose deadline is in the past."""
    # Start clean
    gmail_mod._oauth_states.clear()
    now = datetime.now(timezone.utc)
    gmail_mod._oauth_states["stale-1"] = now - timedelta(minutes=1)
    gmail_mod._oauth_states["stale-2"] = now - timedelta(hours=1)
    gmail_mod._oauth_states["fresh"] = now + timedelta(minutes=5)

    gmail_mod._purge_stale_states()

    assert "stale-1" not in gmail_mod._oauth_states
    assert "stale-2" not in gmail_mod._oauth_states
    assert "fresh" in gmail_mod._oauth_states
    # Cleanup so we don't pollute later runs
    gmail_mod._oauth_states.clear()


def test_new_oauth_connect_callback_url_is_canonical():
    """New consent flows register the canonical Deeper Notebook callback."""
    from starlette.requests import Request

    request = Request(
        {
            "type": "http",
            "scheme": "http",
            "server": ("127.0.0.1", 5055),
            "path": "/api/onp/gmail/connect",
            "root_path": "",
            "headers": [],
            "query_string": b"",
        }
    )

    assert (
        gmail_mod._callback_url(request)
        == "http://127.0.0.1:5055/api/deeper-notebook/gmail/callback"
    )


def test_canonical_and_legacy_callback_paths_share_state_validation():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    for path in (
        "/api/deeper-notebook/gmail/callback",
        "/api/onp/gmail/callback",
    ):
        response = client.get(
            path,
            params={"code": "oauth-code", "state": "invalid-state"},
        )
        assert response.status_code == 200
        assert "OAuth state mismatch" in response.text


@pytest.mark.parametrize(
    "connect_path",
    (
        "/api/deeper-notebook/gmail/connect",
        "/api/onp/gmail/connect",
    ),
)
def test_canonical_and_legacy_connect_routes_issue_canonical_callback(
    connect_path,
):
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi.testclient import TestClient

    from api.main import app

    integration = MagicMock()
    integration.client_id = "client-id.apps.googleusercontent.com"
    integration.client_secret = "client-secret"
    with patch(
        "api.routers.gmail.GmailIntegration.get",
        AsyncMock(return_value=integration),
    ):
        response = TestClient(app).get(connect_path, follow_redirects=False)

    assert response.status_code == 307
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["redirect_uri"] == [
        "http://testserver/api/deeper-notebook/gmail/callback"
    ]


@pytest.mark.parametrize(
    "callback_path",
    (
        "/api/deeper-notebook/gmail/callback",
        "/api/onp/gmail/callback",
    ),
)
@pytest.mark.asyncio
async def test_oauth_callback_preserves_existing_refresh_token(
    monkeypatch, callback_path
):
    """Google may omit refresh_token on reconnect; keep the persisted token."""
    from unittest.mock import AsyncMock, MagicMock

    from starlette.requests import Request

    state = "refresh-token-continuity"
    gmail_mod._oauth_states[state] = datetime.now(timezone.utc) + timedelta(minutes=5)
    integration = MagicMock()
    integration.client_id = "client-id.apps.googleusercontent.com"
    integration.client_secret = "client-secret"
    integration.refresh_token = "persisted-refresh-token"
    integration.save = AsyncMock()

    token_response = MagicMock()
    token_response.raise_for_status.return_value = None
    token_response.json.return_value = {
        "access_token": "new-access-token",
        "expires_in": 3600,
    }
    user_response = MagicMock()
    user_response.raise_for_status.return_value = None
    user_response.json.return_value = {"email": "owner@example.com"}
    token_requests = []

    class _Client:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **kwargs):
            token_requests.append(kwargs["data"])
            return token_response

        async def get(self, *_args, **_kwargs):
            return user_response

    monkeypatch.setattr(
        gmail_mod.GmailIntegration,
        "get",
        AsyncMock(return_value=integration),
    )
    monkeypatch.setattr(gmail_mod.httpx, "AsyncClient", _Client)
    request = Request(
        {
            "type": "http",
            "scheme": "http",
            "server": ("127.0.0.1", 5055),
            "path": callback_path,
            "root_path": "",
            "headers": [],
            "query_string": b"",
        }
    )

    response = await gmail_mod.callback(
        request,
        code="oauth-code",
        state=state,
        error=None,
    )

    assert response.status_code == 200
    assert integration.access_token == "new-access-token"
    assert integration.refresh_token == "persisted-refresh-token"
    integration.save.assert_awaited_once()
    assert token_requests[0]["redirect_uri"] == (
        f"http://127.0.0.1:5055{callback_path}"
    )


# ---------------------------------------------------------------------------
# v0.8.24 — sanitization regression tests for the two exception-leak sites.
# Same family as the v0.7.177 podcast_service sweep and v0.8.22 credentials
# migration sweep. The gmail router was missed in both.
# ---------------------------------------------------------------------------


def test_v0824_send_test_endpoint_sanitizes_exception_detail():
    """POST /api/gmail/send-test must NOT echo raw exception text. The
    _send_digest_now exception can carry build_digest_html DB internals
    or Gmail API response fragments (including Authorization-header
    leaks via traceback formatting libraries). The 500 detail must
    name only the exception TYPE."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi.testclient import TestClient

    from api.main import app

    secret_in_exception = (
        "INTERNAL: SurrealDB WS frame=0x4F2C; "
        "Authorization=Bearer ya29.SECRET_TOKEN_DO_NOT_LEAK; "
        "user_email=alice@example.com"
    )

    fake_g = MagicMock()
    fake_g.is_connected = True

    with patch(
        "api.routers.gmail.GmailIntegration.get",
        AsyncMock(return_value=fake_g),
    ):
        with patch(
            "api.routers.gmail._send_digest_now",
            AsyncMock(side_effect=RuntimeError(secret_in_exception)),
        ):
            client = TestClient(app)
            # Router prefix is /onp/gmail, mounted under /api (see api/main.py).
            response = client.post("/api/onp/gmail/send-test")

    assert response.status_code == 500, response.text
    detail = response.json().get("detail", "")
    # CRITICAL: no leak of any sensitive token.
    assert "ya29.SECRET_TOKEN_DO_NOT_LEAK" not in detail, (
        f"OAuth access token leaked into send-test response: {detail!r}. "
        f"v0.8.24 fix: emit type(exc).__name__, not str(exc)."
    )
    assert "WS frame" not in detail, f"SurrealDB internal leaked: {detail!r}."
    assert "alice@example.com" not in detail, f"User email leaked: {detail!r}."
    # And the type name IS present so the operator can correlate
    # with the log line written by log.exception above.
    assert "RuntimeError" in detail, (
        f"Expected exception type name in {detail!r} for operator triage."
    )


def test_v0824_oauth_callback_sanitizes_token_exchange_error():
    """The OAuth callback HTML page must NOT echo raw exception text
    from the Google token exchange. Google's error responses include
    the OAuth client_id and redirect_uri, which leak operator config
    in the user's browser tab beyond what the user needs to triage."""
    from datetime import datetime, timedelta, timezone
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi.testclient import TestClient

    from api.main import app
    from api.routers import gmail as gmail_mod

    # Arm a valid OAuth state so the callback advances past the CSRF
    # check into the token-exchange try/except.
    state = "test-state-v0824"
    gmail_mod._oauth_states[state] = datetime.now(timezone.utc) + timedelta(minutes=5)

    fake_g = MagicMock()
    fake_g.client_id = "client-abc.apps.googleusercontent.com"
    fake_g.client_secret = "GOCSPX-SUPERSECRET"

    # The exception we will assert does NOT leak. Mimics a Google error
    # response that included echo-back of our config.
    secret_in_exception = (
        "TokenExchangeError 400: invalid_request "
        "client_id=client-abc.apps.googleusercontent.com "
        "client_secret_hint=GOCSPX-SUPER... "
        "redirect_uri=http://127.0.0.1:5055/api/gmail/callback"
    )

    # Patch httpx.AsyncClient so `client.post(...)` raises with the
    # sensitive content. Use a context-manager mock for `async with`.
    class _BoomClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            raise RuntimeError(secret_in_exception)

    with patch(
        "api.routers.gmail.GmailIntegration.get",
        AsyncMock(return_value=fake_g),
    ):
        with patch(
            "api.routers.gmail.httpx.AsyncClient",
            lambda *_a, **_kw: _BoomClient(),
        ):
            client = TestClient(app)
            response = client.get(
                "/api/onp/gmail/callback",
                params={"code": "irrelevant", "state": state},
            )

    # Cleanup the state map entry the test added (the callback handler
    # also tries to pop it; safe either way).
    gmail_mod._oauth_states.pop(state, None)

    assert response.status_code == 200, response.text  # HTML page, not API error
    body = response.text
    # CRITICAL: no leak of client_id / client_secret / redirect_uri.
    assert "client-abc.apps.googleusercontent.com" not in body, (
        f"OAuth client_id leaked into HTML page. v0.8.24 fix: emit "
        f"only type(exc).__name__, point user at launcher.log."
    )
    assert "GOCSPX-SUPER" not in body, f"Client-secret fragment leaked into HTML page."
    # And the type name IS present for operator triage.
    assert "RuntimeError" in body, (
        f"Expected exception type name in callback HTML for triage."
    )
