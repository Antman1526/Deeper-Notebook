import importlib
import json
import subprocess
import sys
import tomllib
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import patch

import pytest

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
from scripts.rebrand_audit import (
    audit_repository,
    classify_match,
    load_allowlist,
    patterns_for_path,
)

ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "scripts" / "rebrand_audit.py"
ALLOWLIST_PATH = ROOT / "scripts" / "rebrand-allowlist.json"


def _write_allowlist(path: Path, entries: list[dict[str, str]]) -> Path:
    path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return path


def _init_tracked_repo(path: Path, files: dict[str, bytes | str]) -> Path:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    for relative_path, content in files.items():
        target = path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    return path


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


def test_source_fallback_version_matches_pyproject_when_metadata_is_unavailable():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    try:
        with patch(
            "importlib.metadata.version",
            side_effect=PackageNotFoundError,
        ):
            fallback_module = importlib.reload(deeper_notebook)
            assert fallback_module.__version__ == pyproject["project"]["version"]
    finally:
        importlib.reload(deeper_notebook)


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


def test_legacy_installer_path_remains_unexpected_but_app_id_is_compatible():
    allowlist = load_allowlist(ALLOWLIST_PATH)
    installer = "desktop/build/open-notebook-plus.iss"

    assert (
        classify_match(installer, "open-notebook-plus", allowlist)
        == "unexpected_active_identity"
    )
    assert (
        classify_match(
            installer,
            "AppId={{572C65B3-D1E8-4EBD-8D64-2BFDF3CA5842}",
            allowlist,
        )
        == "compatibility_alias"
    )


def test_allowlist_uses_exact_persisted_context_not_broad_module_pattern():
    allowlist = load_allowlist(ALLOWLIST_PATH)

    assert (
        classify_match(
            "commands/embedding_commands.py",
            'app="open_notebook"',
            allowlist,
        )
        == "compatibility_alias"
    )
    assert (
        classify_match(
            "commands/embedding_commands.py",
            "open_notebook",
            allowlist,
        )
        == "unexpected_active_identity"
    )
    assert (
        classify_match(
            "desktop/db_repair.py",
            'namespace: str = "open_notebook"',
            allowlist,
        )
        == "compatibility_alias"
    )


def test_allowlist_accepts_upstream_docs_wildcard_and_rejects_arbitrary_scope(
    tmp_path,
):
    valid = _write_allowlist(
        tmp_path / "valid.json",
        [
            {
                "path": "docs/1-INSTALLATION/**",
                "pattern": "lfnovo/open-notebook",
                "category": "upstream_reference",
            }
        ],
    )
    invalid = _write_allowlist(
        tmp_path / "invalid.json",
        [
            {
                "path": "frontend/**",
                "pattern": "Open Notebook",
                "category": "upstream_reference",
            }
        ],
    )

    assert load_allowlist(valid) == {
        ("docs/1-INSTALLATION/**", "lfnovo/open-notebook"): "upstream_reference"
    }
    with pytest.raises(ValueError, match="disallowed allowlist wildcard"):
        load_allowlist(invalid)


def test_audit_scans_tracked_paths_and_content(tmp_path):
    repo = _init_tracked_repo(
        tmp_path / "repo",
        {"legacy/open-notebook-plus.txt": "Open Notebook Plus\n"},
    )

    report = audit_repository(repo, {})
    unexpected = report["categories"]["unexpected_active_identity"]

    assert any(
        match["source"] == "path"
        and match["path"] == "legacy/open-notebook-plus.txt"
        for match in unexpected
    )
    assert any(
        match["source"] == "content"
        and match["pattern"] == "Open Notebook Plus"
        and match["line"] == 1
        for match in unexpected
    )


def test_exact_context_does_not_hide_active_imports(tmp_path):
    repo = _init_tracked_repo(
        tmp_path / "repo",
        {
            "commands/example.py": (
                "from open_notebook.domain import Note\n"
                '@command("work", app="open_notebook")\n'
            )
        },
    )
    allowlist = {
        (
            "commands/example.py",
            'app="open_notebook"',
        ): "compatibility_alias"
    }

    report = audit_repository(repo, allowlist)

    assert report["categories"]["compatibility_alias"] == [
        {
            "path": "commands/example.py",
            "pattern": 'app="open_notebook"',
            "source": "content",
            "line": 2,
        }
    ]
    assert [
        match["line"]
        for match in report["categories"]["unexpected_active_identity"]
        if match["pattern"] == "open_notebook"
    ] == [1]


def test_audit_reports_stale_entries_and_skips_binary_contents(tmp_path):
    repo = _init_tracked_repo(
        tmp_path / "repo",
        {
            "binary.bin": b"\0Open Notebook Plus",
            "invalid.bin": b"\xffOpen Notebook Plus",
            "clean.txt": "Deeper Notebook\n",
        },
    )
    allowlist = {
        ("missing.md", "Open Notebook"): "historical_reference",
    }

    report = audit_repository(repo, allowlist)

    assert report["stale_allowlist"] == [
        {
            "path": "missing.md",
            "pattern": "Open Notebook",
            "category": "historical_reference",
        }
    ]
    assert not any(
        match["path"] in {"binary.bin", "invalid.bin"}
        for matches in report["categories"].values()
        for match in matches
    )


def test_check_exits_for_unexpected_identity_and_passes_for_clean_repo(tmp_path):
    repo = _init_tracked_repo(tmp_path / "repo", {"product.txt": "Deeper Notebook\n"})
    allowlist_path = _write_allowlist(tmp_path / "allowlist.json", [])
    command = [
        sys.executable,
        str(AUDIT_SCRIPT),
        "--root",
        str(repo),
        "--allowlist",
        str(allowlist_path),
        "--check",
    ]

    assert subprocess.run(command, capture_output=True, check=False).returncode == 0

    (repo / "product.txt").write_text("Open Notebook Plus\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "product.txt"], check=True)

    assert subprocess.run(command, capture_output=True, check=False).returncode == 1
