"""ONP v0.6.18 — Regression test for sync-DNS-in-async in credentials router.

api/routers/credentials.py used to call validate_url(url, provider) directly
inside async create_credential and update_credential handlers. validate_url
calls socket.getaddrinfo() for non-IP hostnames — blocking DNS, can take
30s+ on a slow resolver. With 6 URL fields per request, the entire FastAPI
event loop could stall for up to ~3 minutes on a credential create. Same
family of bug as v0.6.10 (chat invoke) and v0.6.13 (whisper transcribe).

This test AST-walks api/routers/credentials.py and asserts every call to
validate_url is wrapped in asyncio.to_thread(). Allowed patterns:
    await asyncio.to_thread(validate_url, ...)
    asyncio.to_thread(validate_url, ...)
Disallowed:
    validate_url(...)   # direct sync call from async handler
"""

from __future__ import annotations

import ast
from pathlib import Path


def _function_calls_in_source(src: str) -> list[str]:
    """Return every Call node's callable text, as `ast.unparse` would render it."""
    tree = ast.parse(src)
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            calls.append(ast.unparse(node.func))
    return calls


def test_validate_url_always_wrapped_in_to_thread():
    repo_root = Path(__file__).resolve().parent.parent
    src = (repo_root / "api/routers/credentials.py").read_text()

    # The "direct" pattern means validate_url appears as the OUTER callable
    # of a Call. In the wrapped form (asyncio.to_thread(validate_url, ...))
    # validate_url is an ARGUMENT, not the callable, so it won't appear here.
    direct = [c for c in _function_calls_in_source(src) if c == "validate_url"]
    assert not direct, (
        "api/routers/credentials.py contains direct validate_url(...) calls. "
        "These do synchronous DNS in an async handler and can stall the "
        "event loop for up to 30s per URL field. Wrap each callsite in "
        "`await asyncio.to_thread(validate_url, ...)` like the existing "
        "ones already do."
    )

    # Sanity: the wrapped form IS used (so a future refactor can't satisfy
    # the test by deleting the validation entirely).
    assert "asyncio.to_thread" in src
    assert "validate_url" in src
