"""Task-owned capability state for the internal vault repository."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class _ProjectionOwner:
    capability: object
    task: asyncio.Task[object] | None
    thread_id: int


_PROJECTION_CAPABILITY = object()
_ACTIVE_PROJECTION_OWNER: ContextVar[_ProjectionOwner | None] = ContextVar(
    "deeper_notebook_active_projection_owner",
    default=None,
)


def _current_task() -> asyncio.Task[object] | None:
    try:
        return asyncio.current_task()
    except RuntimeError:
        return None


def _projection_refresh_is_active() -> bool:
    """Return true only for the exact task or synchronous thread owner."""

    owner = _ACTIVE_PROJECTION_OWNER.get()
    if owner is None or owner.capability is not _PROJECTION_CAPABILITY:
        return False
    if owner.thread_id != threading.get_ident():
        return False
    current_task = _current_task()
    if owner.task is not None:
        return current_task is owner.task
    return current_task is None


@contextmanager
def _activate_projection_refresh(capability: object) -> Iterator[None]:
    """Activate a projector refresh for its exact execution owner."""

    if capability is not _PROJECTION_CAPABILITY:
        raise PermissionError("invalid projection capability")
    owner = _ProjectionOwner(
        capability=capability,
        task=_current_task(),
        thread_id=threading.get_ident(),
    )
    token = _ACTIVE_PROJECTION_OWNER.set(owner)
    try:
        yield
    finally:
        _ACTIVE_PROJECTION_OWNER.reset(token)
