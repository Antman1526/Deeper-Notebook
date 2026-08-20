"""Task 5 repository-wide active visual namespace contracts."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_COMPONENT_PATH = "components/" + "onp"
LEGACY_CSS_TOKEN = re.compile(r"(?<![-\w])--onp-[a-z0-9-]+")


def _classification(path: str) -> str | None:
    if path == "desktop/CHANGELOG.md":
        return "historical_reference"
    if path.startswith("docs/superpowers/plans/"):
        return "migration_documentation"
    if path in {"scripts/rebrand-allowlist.json", "scripts/rebrand_audit.py"}:
        return "audit_configuration"
    return None


def _tracked_text() -> list[tuple[str, str]]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    files: list[tuple[str, str]] = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        relative_path = raw_path.decode("utf-8", errors="surrogateescape")
        data = (ROOT / relative_path).read_bytes()
        if b"\0" in data:
            continue
        try:
            files.append((relative_path, data.decode("utf-8")))
        except UnicodeDecodeError:
            continue
    return files


def test_active_repository_has_no_stale_component_onp_paths() -> None:
    unexpected = [
        f"{path}:{line_number}"
        for path, source in _tracked_text()
        if _classification(path) is None
        for line_number, line in enumerate(source.splitlines(), start=1)
        if LEGACY_COMPONENT_PATH in line
    ]

    assert unexpected == [], (
        f"Unclassified active {LEGACY_COMPONENT_PATH} references remain:\n"
        + "\n".join(unexpected)
    )


def test_active_repository_has_no_onp_css_custom_properties() -> None:
    unexpected = [
        f"{path}:{line_number}:{match.group(0)}"
        for path, source in _tracked_text()
        if _classification(path) is None
        for line_number, line in enumerate(source.splitlines(), start=1)
        for match in LEGACY_CSS_TOKEN.finditer(line)
    ]

    assert unexpected == [], (
        "Unclassified active --onp-* CSS custom properties remain:\n"
        + "\n".join(unexpected)
    )


def test_theme_storage_uses_canonical_identity_and_mirrors_legacy() -> None:
    theme_switcher = (
        ROOT / "frontend/src/components/deeper-notebook/ThemeSwitcher.tsx"
    ).read_text(encoding="utf-8")
    theme_storage = (ROOT / "frontend/src/lib/theme-storage.ts").read_text(
        encoding="utf-8"
    )

    assert "const CANONICAL_THEME_KEY = 'dn-theme'" in theme_storage
    assert "const LEGACY_THEME_KEY = 'onp-theme'" in theme_storage
    assert "readStoredTheme(localStorage)" in theme_switcher
    assert "writeStoredTheme(localStorage, themeId)" in theme_switcher
    assert "const themeBridge = w.DN ?? w.ONP" in theme_switcher
