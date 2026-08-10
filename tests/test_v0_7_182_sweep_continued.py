"""v0.7.182 — Round-8 sweep: iso() + NotFoundError continuation.

Continuation of:
  - v0.7.181 iso() migration (4 routers → 10 routers)
  - v0.7.179/v0.7.181 NotFoundError re-raise (6 routers → 10 routers)
  - v0.7.181 SourceResponse/SourceListResponse Optional[str] widening
    (2 response models → 8 response models)

This file pins:
  - iso() migration on the 6 new routers (source_chat, podcasts,
    models, exports, embedding_rebuild, insights).
  - NotFoundError re-raise on the 4 new routers (studio, source_chat,
    episode_profiles, speaker_profiles).
  - api/models.py response shape widening across the rest of the
    domain models so the new iso(None) → None behavior doesn't
    Pydantic-reject responses during pre-persist windows.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    path = ROOT / rel
    if path.is_file():
        return path.read_text(encoding="utf-8")

    package = path.with_suffix("")
    if package.is_dir():
        return "\n".join(
            child.read_text(encoding="utf-8")
            for child in sorted(package.rglob("*.py"))
        )

    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# iso() migration pins — the 6 new routers
# ---------------------------------------------------------------------------


_NEW_ISO_ROUTERS = (
    "api/routers/source_chat.py",
    "api/routers/podcasts.py",
    "api/routers/models.py",
    "api/routers/exports.py",
    "api/routers/embedding_rebuild.py",
    "api/routers/insights.py",
)


def test_new_iso_routers_import_helper():
    """v0.7.182: each of the 6 new routers must import the iso helper.
    Without the import, the iso() calls below are NameErrors and the
    endpoint 500s on every request."""
    for rel in _NEW_ISO_ROUTERS:
        src = _read_source(rel)
        assert "from api.utils.iso import iso" in src, (
            f"v0.7.182 regression: {rel} no longer imports iso. "
            f"The iso() calls below will NameError."
        )


def test_new_iso_routers_have_no_unsafe_str_calls():
    """v0.7.182: no `str(X.created)` / `str(X.updated)` left in
    any of the 6 new routers. Combined with v0.7.181's pin on the
    original 4 routers, the count of "iso-clean" routers is now 10."""
    offenders: list[tuple[str, int, str]] = []
    for rel in _NEW_ISO_ROUTERS:
        src = _read_source(rel)
        for i, line in enumerate(src.splitlines(), start=1):
            stripped = line.strip()
            if "str(" in stripped and (
                ".created)" in stripped or ".updated)" in stripped
            ):
                offenders.append((rel, i, stripped))
    assert not offenders, (
        "v0.7.182 regression: new iso-routers contain unsafe "
        "str(X.created) / str(X.updated). Safari new Date() will "
        "fail.\n"
        + "\n".join(f"  {r}:{ln} → {t}" for r, ln, t in offenders)
    )


# ---------------------------------------------------------------------------
# Response model widening pins
# ---------------------------------------------------------------------------


def test_response_models_have_optional_created_updated():
    """v0.7.182: every domain response model that accepts created/
    updated MUST declare them as Optional[str] (not required `str`).
    With the iso() helper returning None for None input, required
    `str` fields would Pydantic-reject responses in async-create
    paths where the row isn't persisted yet."""
    from api.models import (
        CredentialResponse,
        ModelResponse,
        NotebookResponse,
        NoteResponse,
        SourceInsightResponse,
        SourceListResponse,
        SourceResponse,
        TransformationResponse,
    )

    expected_models = [
        NotebookResponse,
        ModelResponse,
        TransformationResponse,
        NoteResponse,
        SourceResponse,
        SourceListResponse,
        SourceInsightResponse,
        CredentialResponse,
    ]
    for cls in expected_models:
        for field_name in ("created", "updated"):
            f = cls.model_fields.get(field_name)
            assert f is not None, (
                f"v0.7.182: {cls.__name__}.{field_name} is missing"
            )
            # Optional[str] means the field's annotation includes None.
            anno = str(f.annotation)
            assert "None" in anno or "Optional" in anno, (
                f"v0.7.182 regression: {cls.__name__}.{field_name} "
                f"is no longer Optional. iso(None) → None will "
                f"Pydantic-reject responses in async-create paths."
            )


# ---------------------------------------------------------------------------
# NotFoundError re-raise pins — the 4 new routers
# ---------------------------------------------------------------------------


_NEW_NFERROR_ROUTERS = (
    "api/routers/studio.py",
    "api/routers/source_chat.py",
    "api/routers/episode_profiles.py",
    "api/routers/speaker_profiles.py",
)


def test_new_nferror_routers_import_typed_exceptions():
    """v0.7.182: each of the 4 new routers must import NotFoundError
    + InvalidInputError. Without these imports the typed re-raise
    clauses below are NameErrors at import time."""
    for rel in _NEW_NFERROR_ROUTERS:
        src = _read_source(rel)
        assert "NotFoundError" in src, (
            f"v0.7.182 regression: {rel} no longer references "
            f"NotFoundError. Imports check."
        )


def test_new_nferror_routers_have_typed_reraise_clauses():
    """v0.7.182: each of the 4 new routers has at least one typed
    re-raise clause inserted by the sweep. Combined with the v0.7.179
    + v0.7.181 routers, the running total is now ~10 routers fully
    routing legitimate 404s to the global handler instead of 500s."""
    for rel in _NEW_NFERROR_ROUTERS:
        src = _read_source(rel)
        assert "except (NotFoundError, InvalidInputError):" in src, (
            f"v0.7.182 regression: {rel} no longer has the typed "
            f"re-raise clause. The broad except Exception will mask "
            f"404s as 500s again."
        )


# ---------------------------------------------------------------------------
# Cumulative pin: the iso() helper file is intact
# ---------------------------------------------------------------------------


def test_iso_helper_unchanged_behavioural_contract():
    """v0.7.182: defensive re-pin of the iso() helper contract.
    A future refactor that 'simplifies' iso() by dropping the
    None-safety would re-introduce the bug v0.7.181 fixed (and
    that v0.7.182 propagated across 8 response models).
    """
    from api.utils.iso import iso

    # None safety.
    assert iso(None) is None
    # T separator on datetime.
    from datetime import datetime, timezone
    dt = datetime(2026, 5, 22, 11, 0, 0, tzinfo=timezone.utc)
    s = iso(dt)
    assert s is not None and "T" in s
    # Idempotent on strings.
    assert iso("anything") == "anything"
