"""ONP v0.7.120 / v0.7.121 — Defense-in-depth security headers.

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
  - `Strict-Transport-Security` (v0.7.121, HTTPS-only)
        HSTS. Set ONLY when the request arrived over HTTPS — sending HSTS
        on plaintext HTTP would teach the browser to upgrade every future
        request to HTTPS even when there's no TLS terminator. 2-year
        max-age + includeSubDomains is the modern baseline.
  - `Permissions-Policy` (v0.7.121)
        Disables browser features the API has no business using
        (camera, microphone, geolocation, payment, etc.). Defense for
        the day someone accidentally embeds the API's `/docs` page in
        an iframe.
  - `X-XSS-Protection: 0` (v0.7.121)
        Modern best practice. The legacy IE-era filter does more harm
        than good (universal-XSS vulnerabilities in IE/Edge); explicitly
        disabling it tells modern browsers not to attempt heuristic
        sanitization on the JSON-only API responses.
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


# v0.7.121 — Permissions-Policy. Disable APIs the backend has no
# legitimate use for. Defense for the case where /docs ends up
# embedded somewhere unexpected.
_PERMISSIONS_POLICY = (
    "accelerometer=(), "
    "ambient-light-sensor=(), "
    "autoplay=(), "
    "battery=(), "
    "camera=(), "
    "display-capture=(), "
    "geolocation=(), "
    "gyroscope=(), "
    "magnetometer=(), "
    "microphone=(), "
    "midi=(), "
    "payment=(), "
    "usb=(), "
    "xr-spatial-tracking=()"
)

# v0.7.121 — HSTS max-age. 2 years matches the modern OWASP
# recommendation. `includeSubDomains` extends protection to any
# subdomains the operator may serve under the same TLS origin.
_HSTS_VALUE = "max-age=63072000; includeSubDomains"


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
        # v0.7.121 — Modern best practice: explicitly disable the
        # legacy IE-era XSS filter (the heuristic causes universal-XSS
        # in older browsers and has zero benefit in modern ones).
        if "X-XSS-Protection" not in response.headers:
            response.headers["X-XSS-Protection"] = "0"
        # v0.7.121 — Permissions-Policy on every response.
        if "Permissions-Policy" not in response.headers:
            response.headers["Permissions-Policy"] = _PERMISSIONS_POLICY
        # v0.7.121 — HSTS — ONLY on HTTPS requests. Sending HSTS on
        # plaintext HTTP would teach the browser to force-upgrade
        # future requests even if no TLS terminator is present;
        # operators behind a reverse proxy (Caddy, Cloudflare, nginx)
        # rely on the `X-Forwarded-Proto: https` header to surface
        # the TLS state to FastAPI. starlette's request.url.scheme
        # already honours `--proxy-headers` when uvicorn is started
        # correctly.
        if request.url.scheme == "https":
            if "Strict-Transport-Security" not in response.headers:
                response.headers["Strict-Transport-Security"] = _HSTS_VALUE
        # CSP — skip on docs paths so Swagger UI / Redoc still work.
        path = request.url.path
        if not any(path.startswith(p) for p in _CSP_EXEMPT_PREFIXES):
            if "Content-Security-Policy" not in response.headers:
                response.headers["Content-Security-Policy"] = _CSP_DEFAULT
        return response
