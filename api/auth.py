import secrets as _secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from deeper_notebook.environment import resolve_env
from deeper_notebook.utils.encryption import get_secret_from_env


def _password_matches(provided: str, expected: str) -> bool:
    """Constant-time password comparison.

    v0.6.7 — previously `credentials != self.password`, which short-circuits
    on the first mismatched byte and leaks byte-by-byte timing info to a
    remote attacker. `secrets.compare_digest` runs in time proportional to
    the *longer* of the two strings, regardless of where the mismatch is.

    Important: `compare_digest` only accepts ASCII strings or bytes — it
    raises TypeError on any non-ASCII codepoint. We encode both sides to
    UTF-8 bytes so Unicode passwords (`pässwörd`, etc.) work correctly
    AND remain timing-safe. Without this guard the auth middleware would
    raise an uncaught TypeError on every request for such a password,
    which is both a crash bug and a more dramatic timing oracle.

    Empty inputs always return False — the "no password configured" bypass
    is filtered upstream by `if not self.password`, so reaching here with
    an empty arg means a malformed request.
    """
    if not provided or not expected:
        return False
    return _secrets.compare_digest(
        provided.encode("utf-8"),
        expected.encode("utf-8"),
    )


class PasswordAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to check password authentication for all API requests.
    Always active with default password if DEEPER_NOTEBOOK_PASSWORD is not set.
    Supports Docker secrets via DEEPER_NOTEBOOK_PASSWORD_FILE.
    """

    def __init__(self, app, excluded_paths: Optional[list] = None):
        super().__init__(app)
        self.password = resolve_env(
            "DEEPER_NOTEBOOK_PASSWORD", getter=get_secret_from_env
        )
        # v0.7.209 — defaults expanded to match what main.py passes
        # in production. Previously the class default omitted the
        # K8s/Docker probes (/livez, /readyz, /healthz/deep) and
        # the Prometheus endpoint (/metrics). main.py:608-630
        # constructs PasswordAuthMiddleware with the full list
        # explicitly, so production was fine — but any test fixture
        # or future re-wiring that instantiated
        # `PasswordAuthMiddleware(app)` (without excluded_paths=)
        # would get 401 on every probe and silently break health
        # monitoring. Make the class default match the production
        # call-site so the failure mode is impossible.
        self.excluded_paths = excluded_paths or [
            "/",
            "/health",
            "/livez",
            "/readyz",
            "/healthz/deep",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
        ]

    async def dispatch(self, request: Request, call_next):
        # Skip authentication if no password is set
        if not self.password:
            return await call_next(request)

        # Skip authentication for excluded paths
        if request.url.path in self.excluded_paths:
            return await call_next(request)

        # Skip authentication for CORS preflight requests (OPTIONS)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Check authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authorization header"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Expected format: "Bearer {password}"
        try:
            scheme, credentials = auth_header.split(" ", 1)
            if scheme.lower() != "bearer":
                raise ValueError("Invalid authentication scheme")
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid authorization header format"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check password — constant-time comparison (see _password_matches)
        if not _password_matches(credentials, self.password):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid password"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Password is correct, proceed with the request
        response = await call_next(request)
        return response


# Optional: HTTPBearer security scheme for OpenAPI documentation
security = HTTPBearer(auto_error=False)


def check_api_password(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> bool:
    """
    Utility function to check API password.
    Can be used as a dependency in individual routes if needed.
    Supports Docker secrets via DEEPER_NOTEBOOK_PASSWORD_FILE.
    Returns True without checking credentials if DEEPER_NOTEBOOK_PASSWORD is not configured.
    Raises 401 if credentials are missing or don't match the configured password.
    """
    password = resolve_env("DEEPER_NOTEBOOK_PASSWORD", getter=get_secret_from_env)

    # No password configured - skip authentication
    if not password:
        return True

    # No credentials provided
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check password — constant-time comparison (see _password_matches)
    if not _password_matches(credentials.credentials, password):
        raise HTTPException(
            status_code=401,
            detail="Invalid password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True
