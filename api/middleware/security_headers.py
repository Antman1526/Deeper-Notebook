"""ONP v0.7.120 — Defense-in-depth security headers.

Adds OWASP-recommended baseline headers to every API response:

  - `X-Content-Type-Options: nosniff`
        Prevents browsers from MIME-sniffing JSON responses as HTML/JS.
  - `X-Frame-Options: DENY`
        The API never serves embeddable content; refuse to be framed.
  - `Referrer-Policy: strict-origin-when-cross-origin`
        Prevents leaking the full API URL (with query params) on outbound
        navigation.
  - `Content-Security-Policy` (skipped on docs paths)
        Layered defense on top of v0.7.117's markdown XSS fix. Tight by
        default: default-src 'none', script/style/img only from self.
        Swagger UI / ReDoc / openapi.json paths are skipped because
        they pull resources from CDNs (Swagger CSS, fonts, etc.) and a
        strict CSP would break /docs.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Paths where CSP is skipped because they intentionally load
# third-party CDN resources (Swagger UI's bundled assets, Redoc's
# webfont, etc.). Adding 'self' to script-src isn't enough — Swagger
# UI uses inline scripts.
_CSP_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/docs",
    "/redoc",
    "/openapi.json",
)

# CSP for every other response. JSON responses don't render scripts,
# so this is purely defense-in-depth in case a future endpoint
# accidentally returns HTML. Frame-ancestors DENY is the modern
# replacement for X-Frame-Options.
_CSP_DEFAULT = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds the baseline security headers to every API response.

    Idempotent — if an upstream middleware (proxy, FastAPI itself) has
    already set a header, we leave it alone via `setdefault` semantics
    on response.headers. This matters when a custom exception handler
    in api/main.py builds its own JSONResponse with selective headers.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # setdefault-style writes: only set if absent. starlette
        # MutableHeaders does NOT have setdefault, so emulate.
        if "X-Content-Type-Options" not in response.headers:
            response.headers["X-Content-Type-Options"] = "nosniff"
        if "X-Frame-Options" not in response.headers:
            response.headers["X-Frame-Options"] = "DENY"
        if "Referrer-Policy" not in response.headers:
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # CSP — skip on docs paths so Swagger UI / Redoc still work.
        path = request.url.path
        if not any(path.startswith(p) for p in _CSP_EXEMPT_PREFIXES):
            if "Content-Security-Policy" not in response.headers:
                response.headers["Content-Security-Policy"] = _CSP_DEFAULT
        return response
