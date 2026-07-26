import tomllib
from pathlib import Path

import deeper_notebook
from deeper_notebook.identity import (
    API_NAMESPACE,
    DATA_DIR_NAME,
    LEGACY_API_NAMESPACE,
    LEGACY_DATA_DIR_NAME,
    PRODUCT_NAME,
    REPOSITORY,
    TAGLINE,
)
from scripts.rebrand_audit import classify_match, patterns_for_path

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_product_identity():
    assert PRODUCT_NAME == "Deeper Notebook"
    assert TAGLINE == "Think further with every source"
    assert REPOSITORY == "Antman1526/Deeper-Notebook"
    assert DATA_DIR_NAME == ".deeper-notebook"
    assert API_NAMESPACE == "/api/deeper-notebook"


def test_legacy_identity_is_explicitly_compatibility_only():
    assert LEGACY_DATA_DIR_NAME == ".open-notebook-plus"
    assert LEGACY_API_NAMESPACE == "/api/onp"


def test_audit_distinguishes_compatibility_from_active_branding():
    allowlist = {
        (
            "desktop/build/deeper-notebook.iss",
            "AppId={{572C65B3",
        ): "compatibility_alias"
    }

    assert (
        classify_match(
            "desktop/build/deeper-notebook.iss",
            "AppId={{572C65B3",
            allowlist,
        )
        == "compatibility_alias"
    )
    assert (
        classify_match(
            "frontend/src/app/layout.tsx",
            "Open Notebook Plus",
            allowlist,
        )
        == "unexpected_active_identity"
    )


def test_distribution_metadata_is_canonical():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "deeper-notebook"
    assert pyproject["project"]["description"] == (
        "Local-first, source-grounded research and personal knowledge workspace"
    )
    assert pyproject["tool"]["setuptools"]["packages"]["find"]["include"] == [
        "deeper_notebook*",
        "open_notebook*",
    ]
    assert deeper_notebook.__version__ == pyproject["project"]["version"]


def test_custom_allowlist_patterns_are_scoped_to_their_path():
    allowlist = {
        (
            "README.upstream.md",
            "lfnovo/open-notebook",
        ): "upstream_reference"
    }

    assert "lfnovo/open-notebook" in patterns_for_path(
        "README.upstream.md", allowlist
    )
    assert "lfnovo/open-notebook" not in patterns_for_path(
        "frontend/src/app/layout.tsx", allowlist
    )
