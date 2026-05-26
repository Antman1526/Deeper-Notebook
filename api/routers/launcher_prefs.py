"""v0.8.6 Item D — GET/PUT /api/launcher-prefs.

Admin-only endpoints (protected by PasswordAuthMiddleware, same as all
other API endpoints) for reading and writing the launcher.env preference
file at ``~/.open-notebook-plus/launcher.env``.

Endpoints
---------
GET  /api/launcher-prefs
    Returns ``{"prefs": {KEY: VALUE, ...}}``.  Empty dict when the file
    doesn't exist.

PUT  /api/launcher-prefs
    Accepts ``{"prefs": {KEY: VALUE | null, ...}}``.  Keys with null
    values are removed from the file.  Returns the new merged state.
    400 if a non-whitelisted key is present in the payload.

Note: changes are written immediately but only take effect after the
launcher is restarted, since env vars are read once at startup before
the API exists.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class PrefsResponse(BaseModel):
    prefs: dict[str, str]


class PrefsUpdate(BaseModel):
    # Values may be str (set) or None (remove the key).
    prefs: dict[str, str | None]


@router.get("/api/launcher-prefs", response_model=PrefsResponse)
async def get_launcher_prefs():
    """Return current launcher.env preference values.

    Returns an empty ``prefs`` dict when the file does not exist.
    """
    try:
        from desktop.launcher_prefs import get_prefs
        prefs = get_prefs()
        return {"prefs": prefs}
    except ValueError as exc:
        # Malformed line in the file — surface as 400 so the UI can
        # show a useful error rather than a 500 with a traceback.
        raise HTTPException(
            status_code=400,
            detail=f"launcher.env is malformed: {exc}",
        )


@router.put("/api/launcher-prefs", response_model=PrefsResponse)
async def update_launcher_prefs(body: PrefsUpdate):
    """Write updates to launcher.env and return the new merged state.

    Accepts ``{prefs: {KEY: VALUE | null}}``.  Null removes the key.
    Returns 400 for non-whitelisted keys or malformed existing file.
    """
    try:
        from desktop.launcher_prefs import update_prefs
        new_prefs = update_prefs(body.prefs)
        return {"prefs": new_prefs}
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )
