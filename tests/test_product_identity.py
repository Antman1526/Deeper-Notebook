import hashlib
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
    Approval,
    audit_repository,
    classify_match,
    context_sha256,
    load_allowlist,
    occurrence_anchor,
    patterns_for_path,
)

ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "scripts" / "rebrand_audit.py"
ALLOWLIST_PATH = ROOT / "scripts" / "rebrand-allowlist.json"


def _write_allowlist(path: Path, entries: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps({"schema_version": 2, "entries": entries}),
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
    reason = (
        f"{occurrence_anchor(path, source, line, actual_column)} "
        f"{rationale}"
    )
    return key, Approval(category=category, reason=reason)


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
    line = "AppId={{572C65B3"
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


def test_legacy_installer_path_is_unexpected_but_current_app_id_is_compatible():
    allowlist = load_allowlist(ALLOWLIST_PATH)
    legacy_installer = "desktop/build/open-notebook-plus.iss"
    current_installer = "desktop/build/deeper-notebook.iss"
    current_key = next(
        key
        for key in allowlist
        if key[0] == current_installer
        and key[1] == "AppId={{572C65B3-D1E8-4EBD-8D64-2BFDF3CA5842}"
    )
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
    assert classify_match(current_key, allowlist) == "compatibility_alias"


def test_allowlist_uses_exact_persisted_context_not_broad_module_pattern():
    allowlist = load_allowlist(ALLOWLIST_PATH)
    command_key = next(
        key
        for key, approval in allowlist.items()
        if key[0] == "commands/embedding_commands.py"
        and key[1] == 'app="open_notebook"'
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
        and key[1] == 'namespace: str = "open_notebook"'
        and approval.category == "compatibility_alias"
    )
    assert classify_match(command_key, allowlist) == "compatibility_alias"
    assert classify_match(repair_key, allowlist) == "compatibility_alias"


def test_allowlist_rejects_all_wildcard_paths(
    tmp_path,
):
    path = "docs/1-INSTALLATION/**"
    pattern = "lfnovo/open-notebook"
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
                "reason": (
                    f"{occurrence_anchor(path, 'content', 1, 1)} "
                    "Retains an exact upstream repository reference."
                ),
            }
        ],
    )

    with pytest.raises(ValueError, match="wildcards are disallowed"):
        load_allowlist(wildcard)


def test_repository_allowlist_entries_have_specific_reasons():
    payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))

    for entry in payload["entries"]:
        assert isinstance(entry.get("reason"), str), entry
        assert entry["reason"].strip(), entry


def test_allowlist_requires_occurrence_location_and_context(tmp_path):
    incomplete = _write_allowlist(
        tmp_path / "incomplete.json",
        [
            {
                "path": "docs/history.md",
                "pattern": "Open Notebook Plus",
                "category": "historical_reference",
                "reason": "Historical product name.",
            }
        ],
    )

    with pytest.raises(ValueError, match="source.*line.*column.*context_sha256"):
        load_allowlist(incomplete)


def test_allowlist_reason_names_its_exact_occurrence_anchor(tmp_path):
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
                "reason": "Historical product name retained for accuracy.",
            }
        ],
    )

    with pytest.raises(ValueError, match="exact occurrence anchor"):
        load_allowlist(generic)


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
                "reason": (
                    "docs/history.md@content:1:21 names the product shipped "
                    "in this historical release."
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
        pattern='app="open_notebook"',
        context=compatibility_line,
        line=2,
    )
    allowlist = {key: approval}

    report = audit_repository(repo, allowlist)

    assert report["categories"]["compatibility_alias"] == [
        {
            "path": "commands/example.py",
            "pattern": 'app="open_notebook"',
            "source": "content",
            "line": 2,
            "column": compatibility_line.index('app="open_notebook"') + 1,
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
        pattern='app="open_notebook"',
        context=line,
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
            "reason": approval.reason,
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
