"""Episode-profile name compatibility shared by registration and selection."""

from __future__ import annotations

from collections.abc import Collection

CANONICAL_LOCAL_EPISODE_PROFILE = "Deeper Notebook Local"
LEGACY_LOCAL_EPISODE_PROFILE = "Open Notebook Plus Local"

EPISODE_PROFILE_NAME_ALIASES: dict[str, tuple[str, ...]] = {
    CANONICAL_LOCAL_EPISODE_PROFILE: (LEGACY_LOCAL_EPISODE_PROFILE,),
}


def equivalent_episode_profile_names(name: str) -> tuple[str, ...]:
    """Return canonical-first names equivalent to ``name``."""
    for canonical, aliases in EPISODE_PROFILE_NAME_ALIASES.items():
        if name == canonical or name in aliases:
            return (canonical, *aliases)
    return (name,)


def select_existing_episode_profile_name(
    preferred: str,
    available: Collection[str],
) -> str | None:
    """Select an existing equivalent name with canonical precedence."""
    for candidate in equivalent_episode_profile_names(preferred):
        if candidate in available:
            return candidate
    return None
