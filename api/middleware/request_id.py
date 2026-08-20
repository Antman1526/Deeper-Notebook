"""ONP v0.7.120 — Request-ID correlation middleware.

Generates (or accepts) a UUID4 per request, sets it as an
`X-Request-ID` response header, and binds it into loguru's context so
every log line emitted during the request flow carries the same id.

Operators can then `grep <req-id>` to follow a single request across
the codebase — much faster than the previous "I see logs say it
failed somewhere" debugging UX. Particularly valuable post-v0.7.109
when typed status codes finally propagate to the client and detail
strings actually mean something.

The middleware respects an inbound `X-Request-ID` header from
upstream proxies / clients so a request_id flowing in from a reverse
proxy keeps the same value end-to-end. Falls back to a fresh UUID4
when no inbound header is present.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Process-wide ContextVar so async code paths that span multiple
# `await`s see the same id. Default is empty string so log emit
# outside any request context still works.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


# Cap on the inbound header length. Clients can pass arbitrary ids
# (some traceparent setups use 32-char hex strings) but we cap at
# 128 chars to avoid log-injection / log-bloat via a malicious header.
_MAX_INBOUND_ID_LEN = 128

# v0.7.131 — character-set validation for inbound IDs (Area for Review
# #25). Previously we only enforced length, so a caller could pass
# `X-Request-ID: \n[CRITICAL] forged log line` and we'd log it
# verbatim into the loguru `req=` column. Log-aggregation tools that
# split on newlines (or any control-char-aware parser) would then
# treat that as a separate, freshly-attributed log entry — classic
# log-injection.
#
# The allowed set is deliberately conservative: alphanumerics + the
# four punctuation chars that appear in real-world request-ID formats:
#   - `-` (UUID4 hyphens, kebab-case correlation IDs)
#   - `_` (some traceparent variants, snake_case)
#   - `.` (period-separated multi-segment IDs)
#   - `:` (Datadog / OTel-style "trace-id:span-id" composites)
# Anything outside this set triggers a fresh UUID4 — the upstream
# tooling sees a normal correlation ID and the bad header is dropped
# silently. We log at DEBUG (not WARNING) because a misconfigured
# proxy could fire this on every request and we don't want to flood
# the log; a real attack would be obvious from a sudden bump in the
# `http_requests_total` rate combined with no matching request IDs
# upstream.
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-.:]+$")


def _short(request_id: str, *, width: int = 8) -> str:
    """Truncate to the first N chars for log readability. UUID4s and
    36-char traceparents both have entropy in the first 8."""
    return (request_id or "-")[:width]


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Set X-Request-ID on every response + bind into loguru context."""

    async def dispatch(self, request: Request, call_next):
        # Honour an inbound X-Request-ID if one was set by an upstream
        # proxy / client so cross-service correlation works.
        # v0.7.131 — added character-set validation (see _REQUEST_ID_PATTERN
        # comment above). The previous version only checked length, which
        # let a malicious header like `\n[CRITICAL] forged` through into
        # logs verbatim.
        inbound = request.headers.get("X-Request-ID", "").strip()
        if (
            inbound
            and len(inbound) <= _MAX_INBOUND_ID_LEN
            and _REQUEST_ID_PATTERN.match(inbound)
        ):
            rid = inbound
        else:
            if inbound:
                # Distinguish "rejected as malformed" from "no header" so
                # operators can see the reason in DEBUG-level logs. Don't
                # log the inbound value itself — we already established
                # we don't trust it, and logging it would defeat the
                # whole point of the validation.
                logger.debug(
                    "Request-ID rejected (length={}, valid_chars={}); "
                    "minting fresh UUID4",
                    len(inbound),
                    bool(_REQUEST_ID_PATTERN.match(inbound)),
                )
            rid = str(uuid.uuid4())

        # Set the ContextVar so any async-spawned helper coroutines
        # inherit the same id. Token lets us restore the previous
        # value on exit (handles nested middleware cleanly).
        token = request_id_var.set(rid)
        try:
            # loguru's contextualize() patches the extra dict for the
            # duration of the `with` block. All `logger.info(...)` etc
            # calls inside this block carry `extra[request_id]=rid`.
            with logger.contextualize(request_id=_short(rid)):
                response = await call_next(request)
                response.headers["X-Request-ID"] = rid
                return response
        finally:
            request_id_var.reset(token)


def current_request_id() -> str:
    """Helper for code that wants to surface the current request_id
    (e.g. in an error response detail or a slow-query warning).
    Returns '-' when called outside a request scope."""
    return request_id_var.get()
