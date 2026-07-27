"""Private capabilities shared by the read-only vault projection boundary."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_PROJECTION_CAPABILITY = object()
_ACTIVE_PROJECTION_CAPABILITY: ContextVar[object | None] = ContextVar(
    "deeper_notebook_active_projection_capability",
    default=None,
)


def _projection_refresh_is_active() -> bool:
    """Return whether the current task owns the private projection capability."""

    return _ACTIVE_PROJECTION_CAPABILITY.get() is _PROJECTION_CAPABILITY


@contextmanager
def _projection_note_refresh() -> Iterator[None]:
    """Allow the vault repository to refresh canonical projected note rows.

    This module-private context is intentionally not represented by a request
    field or boolean argument. The future vault repository is the only
    production caller; generic API routes cannot activate it from user input.
    """

    token = _ACTIVE_PROJECTION_CAPABILITY.set(_PROJECTION_CAPABILITY)
    try:
        yield
    finally:
        _ACTIVE_PROJECTION_CAPABILITY.reset(token)


__all__: list[str] = []
