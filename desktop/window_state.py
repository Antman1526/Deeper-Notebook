"""v0.8.67m — persist the main window's size between launches.

v0.8.67j made the window open screen-aware instead of a fixed 1280x800. This
adds the small follow-up the user asked for: remember the size YOU set. Stored
as a tiny JSON file (separate from config.toml, which holds secrets and is a
frozen dataclass with a string-only serializer). Size-only by design — we read
the window's final width/height at close rather than subscribing to pywebview
resize/move events, so there's no dependency on event APIs that vary across
pywebview versions, and a corrupt/missing file simply falls back to the
screen-aware default.
"""

from __future__ import annotations

import json
from pathlib import Path


def state_path(data_home: Path) -> Path:
    return Path(data_home) / "window_state.json"


def clamp(
    width, height, screen_w, screen_h, min_w: int = 1024, min_h: int = 700
) -> tuple[int, int]:
    """Keep a remembered size sane: never below (min_w, min_h), never larger
    than the current screen (a monitor change mustn't strand the window
    off-screen). Non-positive screen dims mean "unknown" → only the floor is
    applied."""
    try:
        w = max(min_w, int(width))
        h = max(min_h, int(height))
    except (TypeError, ValueError):
        return min_w, min_h
    if screen_w and screen_w > 0:
        w = min(w, int(screen_w))
    if screen_h and screen_h > 0:
        h = min(h, int(screen_h))
    return w, h


def load_size(data_home: Path) -> "tuple[int, int] | None":
    """Return the saved (width, height), or None if absent/unreadable/invalid."""
    p = state_path(data_home)
    try:
        data = json.loads(p.read_text())
        w = int(data["width"])
        h = int(data["height"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if w <= 0 or h <= 0:
        return None
    return w, h


def save_size(data_home: Path, width, height) -> None:
    """Persist (width, height). Best-effort; never raises."""
    try:
        w, h = int(width), int(height)
    except (TypeError, ValueError):
        return
    if w <= 0 or h <= 0:
        return
    p = state_path(data_home)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps({"width": w, "height": h}))
        tmp.replace(p)
    except OSError:
        pass
