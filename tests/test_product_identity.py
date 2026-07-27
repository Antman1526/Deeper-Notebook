import hashlib
import importlib
import json
import re
import subprocess
import sys
import tomllib
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import patch

import pytest

import deeper_notebook
import scripts.rebrand_audit as rebrand_audit
from deeper_notebook.environment import SETTINGS
from deeper_notebook.identity import (
    API_NAMESPACE,
    DATA_DIR_NAME,
    LEGACY_API_NAMESPACE,
    LEGACY_DATA_DIR_NAME,
    PRODUCT_NAME,
    REPOSITORY,
    TAGLINE,
)
from deeper_notebook.logging import default_log_dir
from scripts.rebrand_audit import (
    LEGACY_PATTERNS,
    Approval,
    Rationale,
    audit_repository,
    classify_match,
    context_sha256,
    load_allowlist,
    patterns_for_path,
)

ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "scripts" / "rebrand_audit.py"
ALLOWLIST_PATH = ROOT / "scripts" / "rebrand-allowlist.json"


def _write_allowlist(path: Path, entries: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "persisted_queue_identifiers": [],
                "entries": entries,
            }
        ),
        encoding="utf-8",
    )
    return path


def _approval(
    *,
    path: str,
    pattern: str,
    context: str,
    source: str = "content",
    line: int | None = 1,
    column: int | None = None,
    category: str = "compatibility_alias",
    rationale: str = "Compatibility behavior is intentionally preserved.",
):
    actual_column = column or context.index(pattern) + 1
    key = (
        path,
        pattern,
        source,
        line,
        actual_column,
        context_sha256(context),
    )
    return key, Approval(
        category=category,
        rationale=Rationale(
            path=path,
            pattern=pattern,
            source=source,
            line=line,
            column=actual_column,
            context_sha256=key[-1],
            category=category,
            explanation=rationale,
        ),
    )


def _rationale(
    *,
    path: str,
    pattern: str,
    source: str,
    line: int | None,
    column: int,
    context: str,
    category: str,
    explanation: str,
) -> dict[str, object]:
    return {
        "path": path,
        "pattern": pattern,
        "source": source,
        "line": line,
        "column": column,
        "context_sha256": context_sha256(context),
        "category": category,
        "explanation": explanation,
    }


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
    line = "open_notebook"
    approved_key, approval = _approval(
        path="desktop/build/deeper-notebook.iss",
        pattern=line,
        context=line,
    )
    allowlist = {approved_key: approval}

    assert classify_match(approved_key, allowlist) == "compatibility_alias"
    active_key, _ = _approval(
        path="frontend/src/app/layout.tsx",
        pattern="Open Notebook Plus",
        context="Open Notebook Plus",
    )
    assert (
        classify_match(active_key, allowlist)
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


def test_audit_patterns_are_immutable_and_not_extended_by_approvals():
    custom_allowlist = {
        ("README.upstream.md", "lfnovo/open-notebook"): "upstream_reference"
    }

    assert patterns_for_path("README.upstream.md", custom_allowlist) == (
        LEGACY_PATTERNS
    )


def test_allowlist_rejects_broad_custom_pattern_containing_builtins(tmp_path):
    path = "docs/history.md"
    pattern = "compat open_notebook and Open Notebook Plus wrapper"
    custom = _write_allowlist(
        tmp_path / "custom.json",
        [
            {
                "path": path,
                "pattern": pattern,
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": context_sha256(pattern),
                "category": "historical_reference",
                "rationale": _rationale(
                    path=path,
                    pattern=pattern,
                    source="content",
                    line=1,
                    column=1,
                    context=pattern,
                    category="historical_reference",
                    explanation=(
                        "This exact historical wording is retained to preserve "
                        "the accuracy of the recorded release."
                    ),
                ),
            }
        ],
    )

    with pytest.raises(ValueError, match="built-in legacy patterns"):
        load_allowlist(custom)


def test_legacy_installer_path_is_unexpected_and_app_id_remains_stable():
    allowlist = load_allowlist(ALLOWLIST_PATH)
    legacy_installer = "desktop/build/open-notebook-plus.iss"
    legacy_key = (
        legacy_installer,
        "open-notebook-plus",
        "path",
        None,
        legacy_installer.index("open-notebook-plus") + 1,
        context_sha256(legacy_installer),
    )

    assert (
        classify_match(legacy_key, allowlist)
        == "unexpected_active_identity"
    )
    installer = (ROOT / "desktop/build/deeper-notebook.iss").read_text(
        encoding="utf-8"
    )
    assert "AppId={{572C65B3-D1E8-4EBD-8D64-2BFDF3CA5842}" in installer


def test_allowlist_uses_exact_persisted_context_not_broad_module_pattern():
    allowlist = load_allowlist(ALLOWLIST_PATH)
    command_key = next(
        key
        for key, approval in allowlist.items()
        if key[0] == "commands/embedding_commands.py"
        and key[1] == "open_notebook"
        and approval.category == "compatibility_alias"
    )
    shifted_command_key = (*command_key[:4], command_key[4] + 1, command_key[5])
    assert (
        classify_match(shifted_command_key, allowlist)
        == "unexpected_active_identity"
    )
    repair_key = next(
        key
        for key, approval in allowlist.items()
        if key[0] == "desktop/db_repair.py"
        and key[1] == "open_notebook"
        and approval.category == "compatibility_alias"
    )
    assert classify_match(command_key, allowlist) == "compatibility_alias"
    assert classify_match(repair_key, allowlist) == "compatibility_alias"


def test_allowlist_rejects_all_wildcard_paths(
    tmp_path,
):
    path = "docs/1-INSTALLATION/**"
    pattern = "Open Notebook"
    wildcard = _write_allowlist(
        tmp_path / "wildcard.json",
        [
            {
                "path": path,
                "pattern": pattern,
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": context_sha256(pattern),
                "category": "upstream_reference",
                "rationale": _rationale(
                    path=path,
                    pattern=pattern,
                    source="content",
                    line=1,
                    column=1,
                    context=pattern,
                    category="upstream_reference",
                    explanation=(
                        "This exact upstream product reference is retained to "
                        "preserve the documented project history."
                    ),
                ),
            }
        ],
    )

    with pytest.raises(ValueError, match="wildcards are disallowed"):
        load_allowlist(wildcard)


def test_repository_allowlist_entries_have_bound_specific_rationales():
    payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))

    for entry in payload["entries"]:
        rationale = entry["rationale"]
        for field in (
            "path",
            "pattern",
            "source",
            "line",
            "column",
            "context_sha256",
            "category",
        ):
            assert rationale[field] == entry[field], entry
        assert len(rationale["explanation"]) >= 48, entry
        assert len(rationale["explanation"].split()) >= 8, entry
        assert entry["path"] not in rationale["explanation"], entry
        assert entry["pattern"] not in rationale["explanation"], entry
        assert entry["category"] not in rationale["explanation"], entry
        assert not re.search(
            r"\boccurrence at\b|:[0-9]+:[0-9]+\b|[0-9a-f]{64}",
            rationale["explanation"],
            flags=re.IGNORECASE,
        ), entry


def test_allowlist_requires_occurrence_location_and_context(tmp_path):
    incomplete = _write_allowlist(
        tmp_path / "incomplete.json",
        [
            {
                "path": "docs/history.md",
                "pattern": "Open Notebook Plus",
                "category": "historical_reference",
                "rationale": {},
            }
        ],
    )

    with pytest.raises(ValueError, match="exactly the documented fields"):
        load_allowlist(incomplete)


def test_allowlist_rationale_is_bound_to_its_exact_occurrence(tmp_path):
    line = "Historical release: Open Notebook Plus"
    generic = _write_allowlist(
        tmp_path / "generic.json",
        [
            {
                "path": "docs/history.md",
                "pattern": "Open Notebook Plus",
                "source": "content",
                "line": 1,
                "column": line.index("Open Notebook Plus") + 1,
                "context_sha256": hashlib.sha256(line.encode()).hexdigest(),
                "category": "historical_reference",
                "rationale": _rationale(
                    path="docs/wrong-history.md",
                    pattern="Open Notebook Plus",
                    source="content",
                    line=1,
                    column=line.index("Open Notebook Plus") + 1,
                    context=line,
                    category="historical_reference",
                    explanation=(
                        "This historical product name is retained to preserve "
                        "the accuracy of the documented release."
                    ),
                ),
            }
        ],
    )

    with pytest.raises(ValueError, match="exactly match its occurrence"):
        load_allowlist(generic)


def test_allowlist_rejects_rationale_pattern_mismatch_for_safe_nested_names(
    tmp_path,
):
    path = "docs/history.md"
    line = "Open Notebook Plus"
    mismatched = _write_allowlist(
        tmp_path / "pattern-mismatch.json",
        [
            {
                "path": path,
                "pattern": "Open Notebook Plus",
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": context_sha256(line),
                "category": "historical_reference",
                "rationale": _rationale(
                    path=path,
                    pattern="Open Notebook",
                    source="content",
                    line=1,
                    column=1,
                    context=line,
                    category="historical_reference",
                    explanation=(
                        "The release record preserves the former desktop name "
                        "because that was the identity shipped to users."
                    ),
                ),
            }
        ],
    )

    with pytest.raises(ValueError, match="pattern.*exactly match"):
        load_allowlist(mismatched)


def test_allowlist_rejects_rationale_category_mismatch(tmp_path):
    path = "docs/history.md"
    line = "Open Notebook Plus"
    mismatched = _write_allowlist(
        tmp_path / "category-mismatch.json",
        [
            {
                "path": path,
                "pattern": line,
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": context_sha256(line),
                "category": "historical_reference",
                "rationale": _rationale(
                    path=path,
                    pattern=line,
                    source="content",
                    line=1,
                    column=1,
                    context=line,
                    category="compatibility_alias",
                    explanation=(
                        "The release record preserves the former desktop name "
                        "because that was the identity shipped to users."
                    ),
                ),
            }
        ],
    )

    with pytest.raises(ValueError, match="category.*exactly match"):
        load_allowlist(mismatched)


def test_allowlist_rejects_unknown_entry_fields(tmp_path):
    path = "docs/history.md"
    line = "Historical release: Open Notebook Plus"
    unknown = _write_allowlist(
        tmp_path / "unknown.json",
        [
            {
                "path": path,
                "pattern": "Open Notebook Plus",
                "source": "content",
                "line": 1,
                "column": line.index("Open Notebook Plus") + 1,
                "context_sha256": context_sha256(line),
                "category": "historical_reference",
                "rationale": _rationale(
                    path=path,
                    pattern="Open Notebook Plus",
                    source="content",
                    line=1,
                    column=21,
                    context=line,
                    category="historical_reference",
                    explanation=(
                        "This exact historical release name is retained to "
                        "preserve the accuracy of the release record."
                    ),
                ),
                "unexpected": True,
            }
        ],
    )

    with pytest.raises(ValueError, match="exactly the documented fields"):
        load_allowlist(unknown)


def test_allowlist_rejects_one_character_rationale(tmp_path):
    path = "docs/history.md"
    line = "Open Notebook Plus"
    trivial = _write_allowlist(
        tmp_path / "trivial.json",
        [
            {
                "path": path,
                "pattern": line,
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": context_sha256(line),
                "category": "historical_reference",
                "rationale": _rationale(
                    path=path,
                    pattern=line,
                    source="content",
                    line=1,
                    column=1,
                    context=line,
                    category="historical_reference",
                    explanation="x",
                ),
            }
        ],
    )

    with pytest.raises(ValueError, match="meaningful explanation"):
        load_allowlist(trivial)


def test_allowlist_rejects_generic_rationale(tmp_path):
    path = "docs/history.md"
    line = "Open Notebook Plus"
    generic = _write_allowlist(
        tmp_path / "generic-rationale.json",
        [
            {
                "path": path,
                "pattern": line,
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": context_sha256(line),
                "category": "historical_reference",
                "rationale": _rationale(
                    path=path,
                    pattern=line,
                    source="content",
                    line=1,
                    column=1,
                    context=line,
                    category="historical_reference",
                    explanation=(
                        "Historical reference retained for accuracy and "
                        "migration compatibility."
                    ),
                ),
            }
        ],
    )

    with pytest.raises(ValueError, match="meaningful explanation"):
        load_allowlist(generic)


def test_allowlist_rejects_duplicate_generic_rationales(tmp_path):
    first_path = "docs/history-one.md"
    second_path = "docs/history-two.md"
    line = "Open Notebook Plus"
    generic = (
        "This exact historical product reference remains here to preserve "
        "the accuracy of the documented release record."
    )
    duplicate = _write_allowlist(
        tmp_path / "duplicate.json",
        [
            {
                "path": path,
                "pattern": line,
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": context_sha256(line),
                "category": "historical_reference",
                "rationale": _rationale(
                    path=path,
                    pattern=line,
                    source="content",
                    line=1,
                    column=1,
                    context=line,
                    category="historical_reference",
                    explanation=generic,
                ),
            }
            for path in (first_path, second_path)
        ],
    )

    with pytest.raises(ValueError, match="duplicate semantic explanation"):
        load_allowlist(duplicate)


def test_semantic_duplicate_key_ignores_mechanical_locator_suffixes():
    first = (
        "The release record preserves the former desktop name because that "
        "was the identity shipped to users. This occurrence at "
        "docs/history-one.md:12:4 is individually pinned."
    )
    second = (
        "The release record preserves the former desktop name because that "
        "was the identity shipped to users. This occurrence at "
        "docs/history-two.md:48:9 is individually pinned."
    )

    assert rebrand_audit.semantic_explanation_key(first) == (
        rebrand_audit.semantic_explanation_key(second)
    )


def test_semantic_explanation_uses_heading_and_line_purpose_not_locator(
    tmp_path,
):
    path = "docs/history.md"
    line = "Upgrade notes retain Open Notebook Plus for archival accuracy."
    root = tmp_path / "repo"
    root.mkdir()
    target = root / path
    target.parent.mkdir(parents=True)
    target.write_text(
        "# Release History\n\n## Version 1 migration\n\n" + line + "\n",
        encoding="utf-8",
    )

    explanation = rebrand_audit.semantic_explanation_for_occurrence(
        root,
        {
            "path": path,
            "pattern": "Open Notebook Plus",
            "source": "content",
            "line": 5,
            "column": line.index("Open Notebook Plus") + 1,
            "context_sha256": context_sha256(line),
        },
        "historical_reference",
    )

    assert "Version 1 migration" in explanation
    assert "archival accuracy" in explanation
    assert path not in explanation
    assert "Open Notebook Plus" not in explanation
    assert "historical_reference" not in explanation
    assert not re.search(r":[0-9]+:[0-9]+", explanation)


def test_allowlist_regeneration_is_deterministic_and_semantic(tmp_path):
    path = "docs/history.md"
    line = "Upgrade notes retain Open Notebook Plus for archival accuracy."
    repo = _init_tracked_repo(
        tmp_path / "repo",
        {
            path: (
                "# Release History\n\n"
                "## Version 1 migration\n\n"
                f"{line}\n"
            )
        },
    )
    allowlist_path = _write_allowlist(
        tmp_path / "allowlist.json",
        [
            {
                "path": path,
                "pattern": "Open Notebook Plus",
                "source": "content",
                "line": 5,
                "column": line.index("Open Notebook Plus") + 1,
                "context_sha256": context_sha256(line),
                "category": "historical_reference",
                "rationale": _rationale(
                    path=path,
                    pattern="Open Notebook Plus",
                    source="content",
                    line=5,
                    column=line.index("Open Notebook Plus") + 1,
                    context=line,
                    category="historical_reference",
                    explanation=(
                        "The release history preserves the former desktop "
                        "identity because the migration record depends on it."
                    ),
                ),
            }
        ],
    )

    first = rebrand_audit.regenerate_allowlist(repo, allowlist_path)
    first_bytes = allowlist_path.read_bytes()
    second = rebrand_audit.regenerate_allowlist(repo, allowlist_path)

    assert first == second
    assert allowlist_path.read_bytes() == first_bytes
    entry = first["entries"][0]
    assert entry["rationale"]["pattern"] == entry["pattern"]
    assert entry["rationale"]["category"] == entry["category"]
    assert "Version 1 migration" in entry["rationale"]["explanation"]


def test_repository_category_examples_match_their_actual_roles():
    payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    entries = payload["entries"]

    assert any(
        entry["path"] == "deeper_notebook/identity.py"
        and entry["pattern"] == "open_notebook"
        and entry["category"] == "compatibility_alias"
        for entry in entries
    )
    assert any(
        entry["path"] == "desktop/__init__.py"
        and entry["pattern"] == "open-notebook-plus"
        and entry["category"] == "historical_reference"
        for entry in entries
    )
    logging_aliases = [
        entry
        for entry in entries
        if entry["path"] == "deeper_notebook/logging.py"
        and entry["line"] in {18, 19}
        and entry["pattern"] in {"OPEN_NOTEBOOK_", "ONP_"}
    ]
    assert logging_aliases
    assert {
        entry["category"] for entry in logging_aliases
    } == {"migration_documentation"}
    assert any(
        entry["path"] == "README.upstream.md"
        and entry["category"] == "upstream_reference"
        for entry in entries
    )
    assert any(
        entry["path"] == ".github/workflows/build-desktop.yml"
        and entry["pattern"] == "open-notebook-plus"
        and entry["category"] == "compatibility_alias"
        for entry in entries
    )
    assert any(
        entry["path"] == "CHANGELOG.md"
        and entry["category"] == "historical_reference"
        for entry in entries
    )
    assert any(
        entry["path"] == "docs/7-DEVELOPMENT/maintainer-guide.md"
        and entry["category"] == "migration_documentation"
        for entry in entries
    )
    assert any(
        entry["path"] == "Dockerfile"
        and entry["category"] == "upstream_reference"
        for entry in entries
    )


def test_approved_broad_builtin_suppresses_only_its_safe_nested_pattern(
    tmp_path,
):
    line = "Historical release: Open Notebook Plus"
    repo = _init_tracked_repo(tmp_path / "repo", {"history.md": f"{line}\n"})
    key, approval = _approval(
        path="history.md",
        pattern="Open Notebook Plus",
        context=line,
        category="historical_reference",
        rationale=(
            "This exact product name identifies the software shipped in the "
            "recorded historical release."
        ),
    )

    report = audit_repository(repo, {key: approval})

    assert report["summary"]["historical_reference"] == 1
    assert report["summary"]["unexpected_active_identity"] == 0


def test_logging_contract_prefers_canonical_names_and_container_path(
    monkeypatch,
):
    assert SETTINGS["DEEPER_NOTEBOOK_LOG_DIR"].precedence == (
        "DEEPER_NOTEBOOK_LOG_DIR",
        "DN_LOG_DIR",
        "OPEN_NOTEBOOK_LOG_DIR",
        "ONP_LOG_DIR",
    )
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)
    for name in SETTINGS["DEEPER_NOTEBOOK_LOG_DIR"].precedence:
        monkeypatch.delenv(name, raising=False)

    assert default_log_dir() == Path("/var/log/deeper-notebook")


def test_active_logging_provision_maintainer_and_wrapper_copy_is_canonical():
    logging_source = (ROOT / "deeper_notebook/logging.py").read_text(
        encoding="utf-8"
    )
    provision_source = (ROOT / "deeper_notebook/ai/provision.py").read_text(
        encoding="utf-8"
    )
    maintainer_source = (
        ROOT / "docs/7-DEVELOPMENT/maintainer-guide.md"
    ).read_text(encoding="utf-8")
    wrapper_source = (ROOT / "desktop/__init__.py").read_text(encoding="utf-8")

    assert "DEEPER_NOTEBOOK_LOG_LEVEL" in logging_source
    assert "DEEPER_NOTEBOOK_LOG_JSON" in logging_source
    assert "Deprecated aliases" in logging_source
    assert "DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT" in provision_source
    assert "DEEPER_NOTEBOOK_CLOUD_CHAT_MODEL_ID" in provision_source
    assert "Deprecated aliases accepted during migration" in provision_source
    assert "## Deeper Notebook Hardening Reference" in maintainer_source
    assert "`DN_STUDIO_PAGE_TIMEOUT_SEC`" in maintainer_source
    assert "### Deprecated environment aliases" in maintainer_source
    assert wrapper_source.startswith('"""Deeper Notebook desktop wrapper.')


def test_same_file_legacy_injection_is_not_covered_by_existing_approval(tmp_path):
    line = "Historical release: Open Notebook Plus"
    repo = _init_tracked_repo(tmp_path / "repo", {"history.md": f"{line}\n"})
    allowlist_path = _write_allowlist(
        tmp_path / "allowlist.json",
        [
            {
                "path": "history.md",
                "pattern": "Open Notebook Plus",
                "source": "content",
                "line": 1,
                "column": line.index("Open Notebook Plus") + 1,
                "context_sha256": hashlib.sha256(line.encode()).hexdigest(),
                "category": "historical_reference",
                "rationale": _rationale(
                    path="history.md",
                    pattern="Open Notebook Plus",
                    source="content",
                    line=1,
                    column=line.index("Open Notebook Plus") + 1,
                    context=line,
                    category="historical_reference",
                    explanation=(
                        "This exact product name identifies the software "
                        "shipped in the recorded historical release."
                    ),
                ),
            }
        ],
    )
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

    (repo / "history.md").write_text(
        f"{line}\nActive copy: Open Notebook Plus\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo), "add", "history.md"], check=True)

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 1, result.stdout + result.stderr


def test_active_user_copy_uses_canonical_paths_and_settings():
    expected = {
        "frontend/src/app/(dashboard)/page.tsx": ("~/.deeper-notebook/",),
        "frontend/src/lib/api/client.ts": (
            "~/.deeper-notebook/logs/api.log",
        ),
        "docs/4-AI-PROVIDERS/local-models-tool-calling.md": (
            "DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID",
            "~/.deeper-notebook/launcher.env",
        ),
        "docs/3-USER-GUIDE/free-mcp-servers-web-search.md": (
            "DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID",
            "~/.deeper-notebook/logs/launcher.log",
        ),
    }
    forbidden = (
        "~/.open-notebook-plus/",
        "OPEN_NOTEBOOK_LOCAL_CHAT_MODEL_ID",
    )

    for path, snippets in expected.items():
        source = (ROOT / path).read_text(encoding="utf-8")
        for snippet in snippets:
            assert snippet in source, f"{path}: {snippet}"
        for legacy in forbidden:
            assert legacy not in source, f"{path}: {legacy}"


def test_current_runtime_descriptions_use_deeper_notebook_name():
    expected_copy = {
        "api/routers/auth.py": (
            "Authentication router for Deeper Notebook API."
        ),
        "api/updates_service.py": (
            "Deeper Notebook is privacy-first"
        ),
        "deeper_notebook/exceptions.py": (
            "Base exception class for Deeper Notebook errors."
        ),
        "deeper_notebook/domain/__init__.py": (
            "Domain models for Deeper Notebook."
        ),
        "deeper_notebook/utils/__init__.py": (
            "Utils package for Deeper Notebook."
        ),
        "deeper_notebook/utils/token_utils.py": (
            "Token utilities for Deeper Notebook."
        ),
        "deeper_notebook/utils/context_builder.py": (
            "Generic ContextBuilder for the Deeper Notebook project."
        ),
        "deeper_notebook/utils/embedding.py": (
            "Unified embedding utilities for Deeper Notebook."
        ),
        "deeper_notebook/utils/text_utils.py": (
            "Text utilities for Deeper Notebook."
        ),
        "deeper_notebook/utils/chunking.py": (
            "Chunking utilities for Deeper Notebook."
        ),
        "deeper_notebook/utils/version_utils.py": (
            "Version utilities for Deeper Notebook."
        ),
        "deeper_notebook/local_models/manifest.py": (
            "Most helpers let Deeper Notebook"
        ),
    }

    for path, expected in expected_copy.items():
        source = (ROOT / path).read_text(encoding="utf-8")
        assert expected in source, path


def test_podcast_default_profile_names_use_deeper_notebook():
    source = (ROOT / "api/routers/podcasts.py").read_text(encoding="utf-8")
    from desktop.auto_register.episode_profile import _PRESETS

    assert "Deeper Notebook Local" in source
    assert "Open Notebook Plus Local" not in source
    assert _PRESETS[0]["name"] == "Deeper Notebook Local"


def test_current_bootstrap_and_connection_test_copy_use_deeper_notebook():
    bootstrap = (ROOT / "desktop/bootstrap.py").read_text(encoding="utf-8")
    connection_tester = (
        ROOT / "deeper_notebook/ai/connection_tester.py"
    ).read_text(encoding="utf-8")

    assert "open 'Deeper Notebook.app'" in bootstrap
    assert 'text="Hello from Deeper Notebook"' in connection_tester


def test_current_cli_and_development_banners_use_deeper_notebook():
    expected_copy = {
        "Makefile": (
            "Starting Deeper Notebook",
            "Stopping all Deeper Notebook services",
            "Deeper Notebook Service Status",
        ),
        "run_api.py": (
            "Startup script for Deeper Notebook API server.",
            "Starting Deeper Notebook API server",
        ),
        "dev-init.sh": (
            "Development environment startup for Deeper Notebook",
            "=== Deeper Notebook Dev Startup ===",
        ),
        ".pre-commit-config.yaml": (
            "Pre-commit hooks for Deeper Notebook",
        ),
        ".env.example": (
            "default ~/.deeper-notebook/logs",
        ),
    }

    for path, snippets in expected_copy.items():
        source = (ROOT / path).read_text(encoding="utf-8")
        for snippet in snippets:
            assert snippet in source, f"{path}: {snippet}"


def test_current_operator_scripts_use_deeper_notebook_copy_and_compat_paths():
    expected_copy = {
        "commands/__init__.py": (
            "Surreal-commands integration for Deeper Notebook.",
        ),
        "scripts/upstream_sync_guard.sh": (
            "Safe upstream integration guard for Deeper Notebook.",
            "deeper-notebook-upstream-sync-",
        ),
        "scripts/ralph.sh": (
            "autonomous AI agent loop for Deeper Notebook",
        ),
        "scripts/backup_restore.py": (
            "Backup + restore for the Deeper Notebook data",
            "DEEPER_NOTEBOOK_DATA_DIR",
        ),
        "scripts/create-signing-identity.sh": (
            "Deeper Notebook Local",
        ),
        "scripts/live_source_ingestion_smoke.py": (
            "running native Deeper Notebook app",
            "Deeper Notebook live ingestion smoke marker",
        ),
        "scripts/verify-chat-platform.sh": (
            "Deeper Notebook v0.8.0",
            "DEEPER_NOTEBOOK_PASSWORD",
            "DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT",
        ),
    }

    for path, snippets in expected_copy.items():
        source = (ROOT / path).read_text(encoding="utf-8")
        for snippet in snippets:
            assert snippet in source, f"{path}: {snippet}"

    repair = (ROOT / "scripts/repair_desktop_db.sh").read_text(
        encoding="utf-8"
    )
    assert "/Applications/Deeper Notebook.app/" in repair
    assert "/Applications/Open Notebook Plus.app/" in repair
    assert "${HOME}/.deeper-notebook" in repair
    assert "${HOME}/.open-notebook-plus" in repair


def test_visible_locale_configuration_examples_use_canonical_short_prefix():
    locale_root = ROOT / "frontend" / "src" / "lib" / "locales"
    locale_files = sorted(locale_root.glob("*/index.ts"))
    assert locale_files

    for path in locale_files:
        source = path.read_text(encoding="utf-8")
        assert "ONP_" not in source, path
        assert "OPEN_NOTEBOOK_LOCAL_DRAFT_" not in source, path
        assert "DEEPER_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH" in source, path
        assert "DEEPER_NOTEBOOK_LOCAL_DRAFT_N_PREDICT" in source, path
        assert "DN_CHAT_LLM_CTX" in source, path
        assert "DN_CHAT_LLM_CTX_MAX" in source, path
        assert "DN_METRICS_AUTH_TOKEN" in source, path


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


def test_audit_skips_only_its_self_referential_allowlist_metadata(tmp_path):
    repo = _init_tracked_repo(
        tmp_path / "repo",
        {
            "scripts/rebrand-allowlist.json": (
                '{"pattern": "Open Notebook Plus"}\n'
            ),
            "active.txt": "Deeper Notebook\n",
        },
    )

    report = audit_repository(repo, {})

    assert not any(
        match["path"] == "scripts/rebrand-allowlist.json"
        for matches in report["categories"].values()
        for match in matches
    )


def test_exact_context_does_not_hide_active_imports(tmp_path):
    compatibility_line = '@command("work", app="open_notebook")'
    repo = _init_tracked_repo(
        tmp_path / "repo",
        {
            "commands/example.py": (
                "from open_notebook.domain import Note\n"
                f"{compatibility_line}\n"
            )
        },
    )
    key, approval = _approval(
        path="commands/example.py",
        pattern="open_notebook",
        context=compatibility_line,
        line=2,
    )
    allowlist = {key: approval}

    report = audit_repository(repo, allowlist)

    assert report["categories"]["compatibility_alias"] == [
        {
            "path": "commands/example.py",
            "pattern": "open_notebook",
            "source": "content",
            "line": 2,
            "column": compatibility_line.index("open_notebook") + 1,
            "context_sha256": context_sha256(compatibility_line),
        }
    ]
    assert [
        match["line"]
        for match in report["categories"]["unexpected_active_identity"]
        if match["pattern"] == "open_notebook"
    ] == [1]


def test_exact_context_does_not_hide_distinct_same_line_active_occurrence(tmp_path):
    line = (
        'legacy_module = open_notebook; @command("work", '
        'app="open_notebook")'
    )
    repo = _init_tracked_repo(
        tmp_path / "repo",
        {
            "commands/example.py": f"{line}\n"
        },
    )
    key, approval = _approval(
        path="commands/example.py",
        pattern="open_notebook",
        context=line,
        column=line.rindex("open_notebook") + 1,
    )
    allowlist = {key: approval}

    report = audit_repository(repo, allowlist)

    assert len(report["categories"]["compatibility_alias"]) == 1
    assert [
        match
        for match in report["categories"]["unexpected_active_identity"]
        if match["pattern"] == "open_notebook"
    ] == [
        {
            "path": "commands/example.py",
            "pattern": "open_notebook",
            "source": "content",
            "line": 1,
            "column": line.index("open_notebook") + 1,
            "context_sha256": context_sha256(line),
        }
    ]


def test_repository_rebrand_audit_has_no_unexpected_active_identity():
    result = subprocess.run(
        [sys.executable, "scripts/rebrand_audit.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_audit_reports_stale_entries_and_skips_binary_contents(tmp_path):
    repo = _init_tracked_repo(
        tmp_path / "repo",
        {
            "binary.bin": b"\0Open Notebook Plus",
            "invalid.bin": b"\xffOpen Notebook Plus",
            "clean.txt": "Deeper Notebook\n",
        },
    )
    key, approval = _approval(
        path="missing.md",
        pattern="Open Notebook",
        context="Open Notebook",
        category="historical_reference",
        rationale="Historical product name retained for accuracy.",
    )
    allowlist = {key: approval}

    report = audit_repository(repo, allowlist)

    assert report["stale_allowlist"] == [
        {
            "path": "missing.md",
            "pattern": "Open Notebook",
            "source": "content",
            "line": 1,
            "column": 1,
            "context_sha256": context_sha256("Open Notebook"),
            "category": "historical_reference",
            "rationale": approval.rationale.as_dict(),
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
