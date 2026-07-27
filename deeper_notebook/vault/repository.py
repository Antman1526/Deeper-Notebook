"""Internal repository boundary for external-vault projections."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from deeper_notebook.vault._projection_context import (
    _PROJECTION_CAPABILITY,
    _activate_projection_refresh,
)


@contextmanager
def _projection_note_refresh() -> Iterator[None]:
    """Grant note-refresh authority only inside the vault repository."""

    with _activate_projection_refresh(_PROJECTION_CAPABILITY):
        yield
