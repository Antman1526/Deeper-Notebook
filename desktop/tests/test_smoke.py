import re
from pathlib import Path

import desktop

# v0.7.210 — was a literal "0.1.0" assertion (set when the project
# started, never updated). Replaced with a SemVer-shape check plus
# a sync assertion against the latest `- **vX.Y.Z**` heading in
# desktop/CHANGELOG.md so future bumps stay locked together.
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def test_package_importable():
    assert _VERSION_RE.match(desktop.__version__), (
        f"v0.7.210: desktop.__version__ must match SemVer X.Y.Z; "
        f"got {desktop.__version__!r}"
    )


def test_version_matches_changelog():
    """v0.7.210 — `desktop.__version__` must equal the most recent
    `- **vX.Y.Z**` bullet in desktop/CHANGELOG.md (the bullet
    inside the Unreleased block, sorted newest-first). Catches
    drift the moment somebody bumps the CHANGELOG without bumping
    the constant (or vice versa)."""
    changelog = (Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text(
        encoding="utf-8"
    )
    m = re.search(r"^- \*\*v(\d+\.\d+\.\d+)\*\*", changelog, re.MULTILINE)
    assert m is not None, (
        "v0.7.210: could not find a `- **vX.Y.Z**` bullet in "
        "desktop/CHANGELOG.md. CHANGELOG format changed?"
    )
    changelog_version = m.group(1)
    assert desktop.__version__ == changelog_version, (
        f"v0.7.210 drift: desktop.__version__={desktop.__version__!r} "
        f"but CHANGELOG latest is v{changelog_version}. Update "
        f"desktop/__init__.py to keep them in sync."
    )
