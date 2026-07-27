#!/usr/bin/env python3
"""Classify tracked legacy-name references during the Deeper Notebook rebrand."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

CATEGORIES = (
    "compatibility_alias",
    "upstream_reference",
    "historical_reference",
    "migration_documentation",
    "unexpected_active_identity",
)
ALLOWLIST_SCHEMA_VERSION = 4
LEGACY_PATTERNS = (
    "Open Notebook Plus",
    "Open Notebook",
    "Open notebook+",
    "OpenNotebook",
    "open-notebook-Plus",
    "open-notebook-plus",
    "open_notebook",
    "OPEN_NOTEBOOK_",
    "ONP_",
    "/onp/",
    "onpFetch",
    "--onp-",
    "onp-theme",
    "components/onp",
    "/api/onp",
)
_SAFE_NESTED_APPROVALS = frozenset(
    {
        ("Open Notebook Plus", "Open Notebook"),
    }
)
_CATEGORY_OVERRIDES = {
    ("desktop/tests/test_data_root_conflict_recovery.py", "open-notebook-plus"): (
        "compatibility_alias"
    ),
    ("desktop/tests/test_data_root_conflict_recovery.py", "Open Notebook Plus"): (
        "compatibility_alias"
    ),
    ("desktop/tests/test_emergency_log.py", "open-notebook-plus"): (
        "compatibility_alias"
    ),
    ("tests/test_product_identity.py", "OpenNotebook"): (
        "compatibility_alias"
    ),
    (
        "frontend/src/components/deeper-notebook/ThemeSwitcher.tsx",
        "onp-theme",
    ): "compatibility_alias",
    (
        "frontend/src/components/deeper-notebook/ThemeSwitcher.test.tsx",
        "onp-theme",
    ): "compatibility_alias",
    ("tests/test_task5_brand_namespace.py", "onp-theme"): (
        "compatibility_alias"
    ),
    ("tests/test_local_model_benchmarks.py", "open-notebook-plus"): (
        "compatibility_alias"
    ),
    ("desktop/__init__.py", "open-notebook-plus"): "historical_reference",
    ("desktop/paths.py", "Open Notebook Plus"): "migration_documentation",
    ("deeper_notebook/logging.py", "OPEN_NOTEBOOK_"): (
        "migration_documentation"
    ),
    ("deeper_notebook/logging.py", "ONP_"): "migration_documentation",
}

OccurrenceKey = tuple[str, str, str, int | None, int, str]


@dataclass(frozen=True)
class Rationale:
    path: str
    pattern: str
    source: str
    line: int | None
    column: int
    context_sha256: str
    category: str
    explanation: str
    compatibility_contract: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "pattern": self.pattern,
            "source": self.source,
            "line": self.line,
            "column": self.column,
            "context_sha256": self.context_sha256,
            "category": self.category,
            "explanation": self.explanation,
            "compatibility_contract": self.compatibility_contract,
        }


@dataclass(frozen=True)
class Approval:
    category: str
    rationale: Rationale


Allowlist = Mapping[OccurrenceKey, Approval]
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "persisted_queue_identifiers",
        "compatibility_contracts",
        "entries",
    }
)
_ENTRY_FIELDS = frozenset(
    {
        "path",
        "pattern",
        "source",
        "line",
        "column",
        "context_sha256",
        "category",
        "rationale",
    }
)
_RATIONALE_FIELDS = frozenset(
    {
        "path",
        "pattern",
        "source",
        "line",
        "column",
        "context_sha256",
        "category",
        "explanation",
        "compatibility_contract",
    }
)
_COMPATIBILITY_CONTRACT_FIELDS = frozenset(
    {"kind", "owner", "retention_reason", "proof"}
)
COMPATIBILITY_CONTRACT_KINDS = frozenset(
    {
        "env_alias",
        "import_shim",
        "data_migration",
        "installer_upgrade",
        "legacy_api_route",
        "persisted_identifier",
        "public_symbol",
        "external_protocol",
        "legacy_artifact_probe",
        "regression_fixture",
    }
)
_STATIC_COMPATIBILITY_PROOFS = frozenset(
    {"static:rebrand-audit-schema-v1"}
)
_PROVEN_LEGACY_TEST_FIXTURE_PATHS = frozenset(
    {
        "desktop/tests/conftest.py",
        "desktop/tests/test_app_migration.py",
        "desktop/tests/test_auto_register.py",
        "desktop/tests/test_bootstrap.py",
        "desktop/tests/test_data_root_final_window_race.py",
        "desktop/tests/test_first_run.py",
        "desktop/tests/test_launcher.py",
        "desktop/tests/test_launcher_prefs.py",
        "desktop/tests/test_llamacpp_provider.py",
        "desktop/tests/test_next_rewrites_patcher.py",
        "desktop/tests/test_release_manifest.py",
        "desktop/tests/test_v0_8_68_launch_race.py",
        "desktop/tests/test_window.py",
        "frontend/src/components/chat/CitationPill.test.tsx",
        "frontend/src/components/deeper-notebook/ArtifactRail.test.tsx",
        "frontend/src/lib/task6-active-brand.test.ts",
        "tests/test_deeper_notebook_router.py",
        "tests/test_digest_builder.py",
        "tests/test_evidence_studio_artifact_api.py",
        "tests/test_logging_config.py",
        "tests/test_local_model_benchmarks.py",
        "tests/test_podcast_suggest.py",
        "tests/test_product_identity.py",
        "tests/test_repair_desktop_db_script.py",
        "tests/test_studio_router.py",
        "tests/test_task5_brand_namespace.py",
        "tests/test_task6_active_product.py",
        "tests/test_v0_7_141_bootstrap.py",
        "tests/test_v0_7_142_singleton.py",
        "tests/test_v0_7_201_audit_sweep.py",
        "tests/test_v0_8_6_launcher_prefs_api.py",
    }
)
_VISIBLE_IDENTITY_PATTERNS = frozenset(
    {
        "Open Notebook Plus",
        "Open Notebook",
        "Open notebook+",
        "OpenNotebook",
        "open-notebook-Plus",
        "open-notebook-plus",
    }
)
_DEFAULT_COMPATIBILITY_CONTRACTS = {
    "env-alias-v1": {
        "kind": "env_alias",
        "owner": "runtime-configuration",
        "retention_reason": (
            "Existing operator environments need a deprecation window while "
            "canonical settings take precedence."
        ),
        "proof": (
            "tests/test_environment_aliases.py::"
            "test_all_four_precedence_positions"
        ),
    },
    "python-import-shim-v1": {
        "kind": "import_shim",
        "owner": "python-package-compatibility",
        "retention_reason": (
            "Installed integrations may import the former package until the "
            "documented compatibility window closes."
        ),
        "proof": (
            "tests/test_python_import_compatibility.py::"
            "test_every_pre_move_legacy_import_resolves_to_canonical_object"
        ),
    },
    "python-symbol-compat-v1": {
        "kind": "public_symbol",
        "owner": "python-api-compatibility",
        "retention_reason": (
            "Existing extensions may catch the former public exception base "
            "while the canonical symbol migration is staged."
        ),
        "proof": (
            "tests/test_v0_7_139.py::TestGetModelErrorDiscrimination"
        ),
    },
    "database-record-identifier-v1": {
        "kind": "persisted_identifier",
        "owner": "database-migrations",
        "retention_reason": (
            "Existing SurrealDB records retain stable record identifiers "
            "until a dedicated idempotent data migration is shipped."
        ),
        "proof": (
            "tests/integration/test_notebook_lifecycle.py::"
            "test_fixture_provisions_isolated_namespace"
        ),
    },
    "data-root-migration-v1": {
        "kind": "data_migration",
        "owner": "desktop-migration",
        "retention_reason": (
            "Existing installations need their legacy application and data "
            "roots detected without overwriting either location."
        ),
        "proof": (
            "desktop/tests/test_data_root_migration.py::"
            "test_rerun_after_success_is_idempotent"
        ),
    },
    "installer-upgrade-v1": {
        "kind": "installer_upgrade",
        "owner": "desktop-release",
        "retention_reason": (
            "Existing desktop installations require stable upgrade identity "
            "while visible package names become canonical."
        ),
        "proof": (
            "desktop/tests/test_release_manifest.py::"
            "test_installer_rebrands_visible_identity_but_pins_upgrade_app_id"
        ),
    },
    "legacy-api-route-v1": {
        "kind": "legacy_api_route",
        "owner": "api-routing",
        "retention_reason": (
            "Existing clients and registered callbacks require the hidden "
            "legacy route to reach the canonical handler."
        ),
        "proof": (
            "tests/test_task6_active_product.py::"
            "test_canonical_namespace_is_documented_and_legacy_alias_is_hidden"
        ),
    },
    "external-format-v1": {
        "kind": "external_protocol",
        "owner": "artifact-import",
        "retention_reason": (
            "Previously exported research bundles remain readable while new "
            "artifacts use the canonical format identifier."
        ),
        "proof": (
            "tests/test_task6_active_product.py::"
            "test_research_bundle_writes_canonical_format_and_reads_legacy_format"
        ),
    },
    "legacy-artifact-probe-v1": {
        "kind": "legacy_artifact_probe",
        "owner": "desktop-release",
        "retention_reason": (
            "Upgrade verification must detect retired application artifacts "
            "without launching or mutating unrelated installations."
        ),
        "proof": (
            "desktop/tests/test_release_manifest.py::"
            "test_compatibility_jobs_probe_real_readiness_then_leave_no_sidecars"
        ),
    },
    "export-directory-fallback-v1": {
        "kind": "legacy_artifact_probe",
        "owner": "filesystem-export",
        "retention_reason": (
            "Existing export directories remain discoverable only when the "
            "canonical directory does not already exist."
        ),
        "proof": (
            "tests/test_filesystem_router.py::"
            "test_fs_home_falls_back_to_existing_legacy_exports_without_moving"
        ),
    },
    "frontend-env-alias-v1": {
        "kind": "env_alias",
        "owner": "frontend-runtime-configuration",
        "retention_reason": (
            "Existing frontend deployments keep legacy feature settings while "
            "canonical settings take deterministic precedence."
        ),
        "proof": (
            "frontend/src/lib/features.test.ts::"
            "continues to support legacy Plus flags when canonical flags are absent"
        ),
    },
    "theme-storage-migration-v1": {
        "kind": "persisted_identifier",
        "owner": "frontend-theme-storage",
        "retention_reason": (
            "Existing browser profiles retain their selected theme while the "
            "canonical storage key becomes primary."
        ),
        "proof": (
            "frontend/src/components/deeper-notebook/ThemeSwitcher.test.tsx::"
            "migrates legacy theme storage into the canonical key"
        ),
    },
    "benchmark-history-fallback-v1": {
        "kind": "persisted_identifier",
        "owner": "local-model-benchmarks",
        "retention_reason": (
            "Existing benchmark history remains readable while every new "
            "write targets the canonical filename."
        ),
        "proof": (
            "tests/test_local_model_benchmarks.py::"
            "test_legacy_benchmark_filename_is_read_but_new_writes_are_canonical"
        ),
    },
    "container-log-fallback-v1": {
        "kind": "legacy_artifact_probe",
        "owner": "runtime-logging",
        "retention_reason": (
            "Existing container log mounts remain readable only when the "
            "canonical log directory is absent."
        ),
        "proof": (
            "tests/test_logging_config.py::"
            "test_existing_legacy_container_log_dir_is_deprecated_fallback"
        ),
    },
    "podcast-profile-identifier-v1": {
        "kind": "persisted_identifier",
        "owner": "podcast-profiles",
        "retention_reason": (
            "Existing saved podcast profiles retain their former selectable "
            "identity until records receive a dedicated migration."
        ),
        "proof": (
            "tests/test_podcast_suggest.py::"
            "test_suggest_medium_volume_matches_canonical_and_legacy_local_profile_names"
        ),
    },
    "central-legacy-identity-v1": {
        "kind": "persisted_identifier",
        "owner": "product-identity",
        "retention_reason": (
            "Centralized former identifiers remain explicit so compatibility "
            "readers can reject stale visible branding elsewhere."
        ),
        "proof": (
            "tests/test_task6_active_product.py::"
            "test_active_product_code_has_no_stale_visible_brand_labels"
        ),
    },
    "legacy-test-fixture-v1": {
        "kind": "regression_fixture",
        "owner": "compatibility-tests",
        "retention_reason": (
            "Synthetic former identities exercise migration readers while "
            "production surfaces remain canonical."
        ),
        "proof": (
            "tests/test_task6_active_product.py::"
            "test_active_product_code_has_no_stale_visible_brand_labels"
        ),
    },
    "rebrand-audit-regression-v1": {
        "kind": "regression_fixture",
        "owner": "rebrand-audit",
        "retention_reason": (
            "The audit test suite must retain synthetic former identities to "
            "prove unsafe compatibility entries are rejected."
        ),
        "proof": (
            "tests/test_product_identity.py::"
            "test_allowlist_rejects_compatibility_for_active_docs_ui_and_defaults"
        ),
    },
}
_AUDIT_METADATA_PATHS = frozenset({"scripts/rebrand-allowlist.json"})
_MIN_EXPLANATION_CHARS = 48
_MIN_EXPLANATION_WORDS = 8
_GENERIC_EXPLANATIONS = frozenset(
    {
        "compatibility behavior is intentionally preserved.",
        "historical product name retained for accuracy.",
        (
            "historical reference retained for accuracy and migration "
            "compatibility."
        ),
        "this legacy reference is retained for compatibility.",
    }
)
_MECHANICAL_LOCATOR_RE = re.compile(
    r"\s*(?:this\s+)?occurrence\s+at\s+"
    r"(?:[\w.@+ -]+/)*[\w.@+ -]+:\d+:\d+"
    r"\s+is\s+individually\s+pinned(?:\s+to\s+its\s+audited\s+context)?[.!]?",
    flags=re.IGNORECASE,
)
_STRUCTURAL_LOCATOR_RE = re.compile(
    r"(?:[\w.@+ -]+/)+[\w.@+ -]+:\d+:\d+|"
    r"\b(?:line|column)\s+\d+\b|"
    r"\b[0-9a-f]{64}\b",
    flags=re.IGNORECASE,
)


def _humanize(value: str) -> str:
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    return " ".join(
        word for word in re.split(r"[^A-Za-z0-9]+", value) if word
    ).lower()


def _scrub_structural_terms(value: str) -> str:
    scrubbed = value
    for pattern in sorted(LEGACY_PATTERNS, key=len, reverse=True):
        scrubbed = re.sub(
            re.escape(pattern),
            "former identifier",
            scrubbed,
            flags=re.IGNORECASE,
        )
    for category in CATEGORIES:
        scrubbed = re.sub(
            re.escape(category),
            "approved classification",
            scrubbed,
            flags=re.IGNORECASE,
        )
    scrubbed = _STRUCTURAL_LOCATOR_RE.sub("", scrubbed)
    return " ".join(scrubbed.split()).strip(" .,:;-")


def semantic_explanation_key(explanation: str) -> str:
    """Normalize semantic meaning without locator-only differentiation."""
    normalized = _MECHANICAL_LOCATOR_RE.sub("", explanation)
    normalized = _scrub_structural_terms(normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.casefold())
    return " ".join(normalized.split())


def _source_role(relative_path: str) -> str:
    path = Path(relative_path)
    if path.name == "Makefile":
        return "The build automation manifest"
    if relative_path == "desktop/__init__.py":
        return "The desktop package wrapper"
    if path.name in {"CHANGELOG.md", "CHANGELOG"}:
        return "The product changelog"
    if path.name == "MEMORY.md":
        return "The project memory history"
    if relative_path.startswith(".github/workflows/"):
        return f"The {_humanize(path.stem)} workflow"
    if relative_path.startswith(".github/ISSUE_TEMPLATE/"):
        return f"The {_humanize(path.stem)} issue template"
    if path.name.startswith("Dockerfile"):
        return (
            "The single-image container build definition"
            if path.name != "Dockerfile"
            else "The multi-stage container build definition"
        )
    if path.name == "docker-compose.yml":
        return "The container orchestration definition"
    if path.name == ".env.example":
        return "The environment configuration example"

    stem_role = _humanize(path.stem or path.name) or "project"
    semantic_parents = [
        _humanize(part)
        for part in path.parts[:-1]
        if part
        not in {
            ".",
            ".github",
            "src",
            "docs",
            "tests",
            "test",
        }
    ]
    qualifier = " ".join(part for part in semantic_parents[-3:] if part)
    subject = " ".join(part for part in (qualifier, stem_role) if part)
    if relative_path.startswith("tests/") or "/tests/" in relative_path:
        return f"The {subject} regression suite"
    if path.suffix == ".py":
        return f"The {subject} Python module"
    if path.suffix in {".ts", ".tsx", ".js", ".mjs"}:
        return f"The {subject} client module"
    if path.suffix in {".yml", ".yaml"}:
        return f"The {subject} configuration"
    if path.suffix == ".md":
        if "spec" in path.stem:
            return f"The {subject} specification"
        if "plan" in path.stem:
            return f"The {subject} plan"
        if "report" in path.stem:
            return f"The {subject} report"
        return f"The {subject} document"
    return f"The {subject} project artifact"


def _markdown_scope(lines: list[str], line_number: int) -> str | None:
    headings: list[tuple[int, str]] = []
    local_label: str | None = None
    in_fence = False
    for line in lines[:line_number]:
        if re.match(r"^\s*```", line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^\s*(#{1,6})\s+(.+?)\s*$", line)
        if match:
            level = len(match.group(1))
            headings = [heading for heading in headings if heading[0] < level]
            headings.append((level, _scrub_structural_terms(match.group(2))))
            local_label = None
            continue
        bold_match = re.match(
            r"^\s*(?:\d+\.\s*)?\*\*(.+?)\*\*\s*:?(?:\s+.*)?$",
            line,
        )
        if bold_match:
            local_label = _scrub_structural_terms(bold_match.group(1))
    if not headings:
        return f'the "{local_label}" section' if local_label else None
    hierarchy_parts = [heading for _level, heading in headings[-3:]]
    if local_label:
        hierarchy_parts.append(local_label)
    hierarchy = " / ".join(hierarchy_parts)
    return f'the "{hierarchy}" section'


def _python_scope(source: str, line_number: int) -> str | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    scopes: list[tuple[int, int, str]] = []
    branches: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            start = node.lineno
            end = getattr(node, "end_lineno", node.lineno)
            if start <= line_number <= end:
                condition = _scrub_structural_terms(ast.unparse(node.test))
                branches.append((start, end, condition))
            continue
        if not isinstance(
            node,
            (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue
        start = min(
            [node.lineno, *(decorator.lineno for decorator in node.decorator_list)]
        )
        end = getattr(node, "end_lineno", node.lineno)
        if start <= line_number <= end:
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            scopes.append((start, end, f"the `{node.name}` {kind}"))
    if branches:
        ordered = sorted(
            branches,
            key=lambda branch: (-(branch[1] - branch[0]), branch[0]),
        )
        conditions = list(dict.fromkeys(branch[2] for branch in ordered))
        return "the branch where " + " and ".join(conditions)
    if scopes:
        return min(
            scopes,
            key=lambda scope: (scope[1] - scope[0], -scope[0]),
        )[2]
    return None


def _workflow_scope(lines: list[str], line_number: int) -> str | None:
    for line in reversed(lines[:line_number]):
        match = re.match(r"^\s*-\s+name:\s*(.+?)\s*$", line)
        if match:
            return (
                f'the "{_scrub_structural_terms(match.group(1))}" '
                "workflow step"
            )
    return None


def _generic_scope(lines: list[str], line_number: int) -> str | None:
    symbol_patterns = (
        r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^\s*(?:function\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{",
        r"^\s*(?:describe|test|it)\s*\(\s*['\"](.+?)['\"]",
        r"^\s*(?:Task|Step)\s+\d+[.: -]+\s*(.+?)\s*$",
    )
    for line in reversed(lines[:line_number]):
        for pattern in symbol_patterns:
            match = re.match(pattern, line)
            if match:
                name = _scrub_structural_terms(match.group(1))
                return f'the "{name}" operation'
    return None


def _semantic_scope(
    relative_path: str,
    lines: list[str],
    line_number: int,
) -> str:
    suffix = Path(relative_path).suffix
    if suffix == ".md":
        return _markdown_scope(lines, line_number) or "the document overview"
    if suffix == ".py":
        source = "\n".join(lines)
        return _python_scope(source, line_number) or "the module overview"
    if suffix in {".yml", ".yaml"}:
        return (
            _workflow_scope(lines, line_number)
            or _generic_scope(lines, line_number)
            or "the configuration block"
        )
    return _generic_scope(lines, line_number) or "the active artifact section"


def _alias_purpose(
    line: str,
    *,
    pattern: str,
    column: int,
) -> str | None:
    start = column - 1
    if pattern in {"OPEN_NOTEBOOK_", "ONP_"}:
        variable_match = re.match(r"[A-Z][A-Z0-9_]+", line[start:])
        variable = variable_match.group(0) if variable_match else pattern
        suffix = variable.removeprefix(pattern)
        setting = _humanize(suffix) or "product setting"
        form = "long-form" if pattern == "OPEN_NOTEBOOK_" else "short-form"
        base = (
            f"the deprecated {form} {setting} setting is named so operators "
            "can recognize and migrate that specific fallback"
        )
        return f"{base}; {_statement_semantics(line, pattern, column)}"
    if pattern == "open_notebook":
        lowered = line.casefold()
        if "app=" in lowered or '"app"' in lowered or "'app'" in lowered:
            return (
                "the persisted command application namespace remains explicit "
                "so queued registrations and submissions keep routing "
                f"correctly; {_statement_semantics(line, pattern, column)}"
            )
        if "namespace" in lowered:
            return (
                "the persisted database namespace remains explicit so existing "
                "records continue to resolve during upgrades; "
                f"{_statement_semantics(line, pattern, column)}"
            )
        if "database" in lowered:
            return (
                "the persisted database name remains explicit so existing "
                "records continue to resolve during upgrades; "
                f"{_statement_semantics(line, pattern, column)}"
            )
        if re.search(r"\b(?:from|import)\s+", line):
            return (
                "the compatibility Python package is imported so downstream "
                "extensions keep their established module boundary; "
                f"{_statement_semantics(line, pattern, column)}"
            )
    if pattern in {"Open Notebook Plus", "Open Notebook", "Open notebook+"}:
        if "http" in line or "](" in line or "spec" in line.casefold():
            return (
                "the archived product wording identifies the historical design "
                "or source link that maintainers still need to trace; "
                f"{_statement_semantics(line, pattern, column)}"
            )
    return None


def _pattern_role(pattern: str, line: str) -> str:
    roles = {
        "Open Notebook Plus": "former full desktop product title",
        "Open Notebook": "former base product title",
        "Open notebook+": "former stylized plus title",
        "OpenNotebook": "former compact product title",
        "open-notebook-Plus": "former mixed-case package slug",
        "open-notebook-plus": "former lowercase package slug",
        "/onp/": "legacy API path segment",
        "onpFetch": "legacy client fetch helper",
        "--onp-": "legacy command-line option prefix",
        "components/onp": "legacy component directory",
        "/api/onp": "legacy API namespace",
    }
    if pattern in roles:
        return roles[pattern]
    if pattern == "open_notebook":
        lowered = line.casefold()
        if "namespace" in lowered:
            return "persisted database namespace"
        if "database" in lowered:
            return "persisted database name"
        if "app" in lowered:
            return "persisted command application namespace"
        if re.search(r"\b(?:from|import)\s+", line):
            return "compatibility Python package"
        return "legacy underscored identifier"
    if pattern == "OPEN_NOTEBOOK_":
        return "deprecated long-form environment prefix"
    if pattern == "ONP_":
        return "deprecated short-form environment prefix"
    return "legacy compatibility role"


def _statement_semantics(line: str, pattern: str, column: int) -> str:
    start = column - 1
    end = start + len(pattern)
    if pattern in {"OPEN_NOTEBOOK_", "ONP_"}:
        variable_match = re.match(r"[A-Z][A-Z0-9_]+", line[start:])
        if variable_match:
            end = start + len(variable_match.group(0))
    role = _pattern_role(pattern, line)
    window_start = max(0, start - 100)
    window_end = min(len(line), end + 100)
    marked = (
        line[window_start:start]
        + f" current {role} "
        + line[end:window_end]
    )
    marked = _scrub_structural_terms(marked)
    marked = re.sub(r"[`*_#|<>{}\[\]();]+", " ", marked)
    marked = " ".join(marked.split()).strip(" .,:;-")
    if len(marked) > 180:
        marked = marked[:177].rsplit(" ", 1)[0] + "..."
    return (
        f"the statement uses that role while expressing {marked}"
        if marked
        else "the statement assigns that role to the current migration case"
    )


def _normalized_line_purpose(
    line: str,
    *,
    pattern: str,
    column: int,
) -> str:
    alias_purpose = _alias_purpose(line, pattern=pattern, column=column)
    if alias_purpose:
        return alias_purpose

    return _statement_semantics(line, pattern, column)


def _role_specific_purpose(
    relative_path: str,
    pattern: str,
    line: str,
) -> str | None:
    if relative_path == "desktop/__init__.py":
        return (
            "the archived desktop design specification keeps its former "
            "filename so maintainers can trace packaging decisions made "
            "before the rename"
        )
    if relative_path == "README.upstream.md":
        return (
            "the original project terminology remains visible so inherited "
            "documentation stays attributable to its upstream source"
        )
    if (
        relative_path == "deeper_notebook/identity.py"
        and pattern == "open_notebook"
    ):
        return (
            "the declared legacy Python package name remains available so "
            "compatibility imports resolve after the package rename"
        )
    if relative_path == "scripts/rebrand_audit.py":
        role = _pattern_role(pattern, line)
        return (
            f"the scanner enumerates the {role} form so active legacy remnants "
            "cannot evade the identity audit; "
            f"{_statement_semantics(line, pattern, line.index(pattern) + 1)}"
        )
    return None


def _nearby_semantic_context(
    lines: list[str],
    line_number: int,
) -> str | None:
    neighbors: list[tuple[str, str]] = []
    for label, indexes in (
        ("the preceding context", range(line_number - 2, -1, -1)),
        ("the following context", range(line_number, len(lines))),
    ):
        for index in indexes:
            candidate = _scrub_structural_terms(lines[index])
            candidate = re.sub(r"[`*_#|<>{}\[\]();]+", " ", candidate)
            candidate = " ".join(candidate.split()).strip(" .,:;-")
            if not candidate:
                continue
            if len(candidate) > 110:
                candidate = candidate[:107].rsplit(" ", 1)[0] + "..."
            neighbors.append((label, candidate))
            break
    if not neighbors:
        return None
    return "; ".join(f"{label} concerns {value}" for label, value in neighbors)


def _semantic_context_label(
    lines: list[str],
    line_number: int,
) -> str | None:
    current_line = lines[line_number - 1]
    current_indent = len(current_line) - len(current_line.lstrip())
    label_patterns = (
        r"^\s*(?:\d+\.\s*)?\*\*(.+?)\*\*\s*:?\s*$",
        r"^\s*(?:Task|Step)\s+\d+[.: -]+\s*(.+?)\s*$",
    )
    for line in reversed(lines[max(0, line_number - 120) : line_number]):
        if re.search(r"(?:\"rationale\"\s*:\s*|rationale\s*=\s*)_rationale\(", line):
            return "the rationale binding"
        function_match = re.match(
            r"^(\s*)(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)",
            line,
        )
        if function_match and len(function_match.group(1)) < current_indent:
            return _scrub_structural_terms(function_match.group(2))
        class_match = re.match(
            r"^(\s*)class\s+([A-Za-z_][A-Za-z0-9_]*)",
            line,
        )
        if class_match and len(class_match.group(1)) < current_indent:
            return _scrub_structural_terms(class_match.group(2))
        for pattern in label_patterns:
            match = re.match(pattern, line)
            if match:
                return _scrub_structural_terms(match.group(1))
    return None


def semantic_explanation_for_occurrence(
    root: Path,
    occurrence: Mapping[str, object],
    category: str,
) -> str:
    """Explain why one exact legacy occurrence remains using source semantics."""
    relative_path = occurrence["path"]
    pattern = occurrence["pattern"]
    source = occurrence["source"]
    line_number = occurrence.get("line")
    column = occurrence["column"]
    if not isinstance(relative_path, str) or not isinstance(pattern, str):
        raise ValueError("occurrence path and pattern must be strings")
    if not isinstance(source, str) or not isinstance(column, int):
        raise ValueError("occurrence source and column must be valid")

    role = _source_role(relative_path)
    if source == "path":
        scope = "the installed or persisted artifact identity"
        purpose = (
            "the legacy artifact name remains discoverable for upgrade and "
            "compatibility checks"
        )
    else:
        if not isinstance(line_number, int):
            raise ValueError("content occurrence requires a line number")
        lines = (root / relative_path).read_text(encoding="utf-8").splitlines()
        if not 1 <= line_number <= len(lines):
            raise ValueError("occurrence line is outside the source file")
        scope = _semantic_scope(relative_path, lines, line_number)
        current_line = lines[line_number - 1]
        purpose = _role_specific_purpose(
            relative_path,
            pattern,
            current_line,
        ) or _normalized_line_purpose(
            current_line,
            pattern=pattern,
            column=column,
        )
        nearby_context = _nearby_semantic_context(lines, line_number)
        if nearby_context:
            purpose = f"{purpose}, while {nearby_context}"
        context_label = _semantic_context_label(lines, line_number)
        if context_label and context_label.casefold() not in scope.casefold():
            purpose = (
                f"{purpose}; the local example is introduced by "
                f"{context_label}"
            )

    templates = {
        "compatibility_alias": (
            "{role} keeps the legacy behavior in {scope} because {purpose}."
        ),
        "historical_reference": (
            "{role} preserves the historical record in {scope} because "
            "{purpose}."
        ),
        "migration_documentation": (
            "{role} documents the upgrade boundary in {scope} because "
            "{purpose}."
        ),
        "upstream_reference": (
            "{role} retains inherited terminology in {scope} because "
            "{purpose}."
        ),
    }
    try:
        explanation = templates[category].format(
            role=role,
            scope=scope,
            purpose=purpose,
        )
    except KeyError as exc:
        raise ValueError(f"invalid rationale category: {category}") from exc
    explanation = explanation.replace(
        relative_path,
        "the related project artifact",
    )
    return _scrub_structural_terms(explanation).rstrip(".") + "."


def context_sha256(context: str) -> str:
    """Return the integrity digest used to pin an approval to exact context."""
    return hashlib.sha256(context.encode("utf-8")).hexdigest()


def occurrence_anchor(
    path: str,
    source: str,
    line: int | None,
    column: int,
) -> str:
    """Return the human-readable anchor every approval reason must name."""
    line_label = "path" if line is None else str(line)
    return f"{path}@{source}:{line_label}:{column}"


def _occurrence_key(
    *,
    path: str,
    pattern: str,
    source: str,
    line: int | None,
    column: int,
    context: str,
) -> OccurrenceKey:
    return (
        path,
        pattern,
        source,
        line,
        column,
        context_sha256(context),
    )


def classify_match(key: OccurrenceKey, allowlist: Allowlist) -> str:
    """Return the exact occurrence's category or flag it as active identity."""
    approval = allowlist.get(key)
    return approval.category if approval else "unexpected_active_identity"


def patterns_for_path(path: str, allowlist: Allowlist) -> tuple[str, ...]:
    """Return the scanner's immutable, built-in legacy-pattern policy."""
    del path, allowlist
    return LEGACY_PATTERNS


def _allowlist_root(path: Path) -> Path:
    if path.parent.name == "scripts":
        return path.parent.parent.resolve()
    return path.parent.resolve()


def _validate_compatibility_proof(root: Path, proof: str) -> None:
    if proof in _STATIC_COMPATIBILITY_PROOFS:
        return
    if proof.count("::") != 1:
        raise ValueError(
            "compatibility contract requires a tracked proof reference "
            "formatted as path::test_name or a validated static contract ID"
        )
    relative_path, symbol = proof.split("::", 1)
    proof_path = Path(relative_path)
    if (
        not relative_path
        or not symbol
        or proof_path.is_absolute()
        or ".." in proof_path.parts
    ):
        raise ValueError(
            "compatibility contract requires a tracked proof reference"
        )
    target = root / proof_path
    if not target.is_file():
        raise ValueError(
            "compatibility contract requires a tracked proof reference"
        )
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", relative_path],
        check=False,
        capture_output=True,
    )
    if tracked.returncode != 0:
        raise ValueError(
            "compatibility contract requires a tracked proof reference"
        )
    source = target.read_text(encoding="utf-8")
    if target.suffix == ".py":
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise ValueError(
                "compatibility contract proof must be parseable"
            ) from exc
        symbols = {
            node.name
            for node in ast.walk(tree)
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            )
        }
        if symbol not in symbols:
            raise ValueError(
                "compatibility contract requires a tracked proof reference"
            )
    elif symbol not in source:
        raise ValueError(
            "compatibility contract requires a tracked proof reference"
        )


def _compatibility_is_forbidden(
    root: Path,
    path: str,
    pattern: str,
    source: str,
    line: int | None,
) -> bool:
    path_obj = Path(path)
    if path_obj.suffix.lower() in {".md", ".mdx", ".rst"}:
        return True
    if "/locales/" in f"/{path}":
        return True
    if (
        path.startswith("frontend/src/")
        and ".test." not in path
        and pattern in _VISIBLE_IDENTITY_PATTERNS
    ):
        return True
    if (
        path.startswith("tests/")
        or path.startswith("desktop/tests/")
        or ".test." in path
    ):
        return False
    if source != "content" or line is None:
        return False
    target = root / path_obj
    try:
        context = target.read_text(encoding="utf-8").splitlines()[line - 1]
    except (OSError, UnicodeError, IndexError):
        return False
    return (
        pattern in _VISIBLE_IDENTITY_PATTERNS | {"OpenNotebook"}
        and bool(
            re.search(
                r"\bdefault(?:s|ed)?\b|default_",
                context,
                re.IGNORECASE,
            )
        )
    )


def compatibility_contract_for_occurrence(
    occurrence: Mapping[str, object],
) -> str | None:
    """Return only a proof-backed compatibility group for an occurrence."""
    path = occurrence.get("path")
    pattern = occurrence.get("pattern")
    if not isinstance(path, str) or not isinstance(pattern, str):
        return None
    path_obj = Path(path)
    if path_obj.suffix.lower() in {".md", ".mdx", ".rst"}:
        return None
    if "/locales/" in f"/{path}":
        return None
    if (
        path.startswith("frontend/src/")
        and ".test." not in path
        and pattern in _VISIBLE_IDENTITY_PATTERNS
    ):
        return None
    if pattern == "onp-theme":
        return "theme-storage-migration-v1"

    is_test = (
        path.startswith("tests/")
        or path.startswith("desktop/tests/")
        or ".test." in path
    )
    if is_test:
        if path == "tests/test_product_identity.py":
            return "rebrand-audit-regression-v1"
        if pattern in {
            "OPEN_NOTEBOOK_",
            "ONP_",
        }:
            if path in {
                "frontend/src/lib/features.test.ts",
                "frontend/src/lib/features.ts",
            }:
                return "frontend-env-alias-v1"
            return "env-alias-v1"
        if pattern == "open_notebook":
            return "python-import-shim-v1"
        if pattern == "OpenNotebook":
            if path == "tests/test_filesystem_router.py":
                return "export-directory-fallback-v1"
            return "python-symbol-compat-v1"
        if pattern in {"/api/onp", "/onp/", "onpFetch", "components/onp"}:
            return "legacy-api-route-v1"
        if path == "tests/test_python_import_compatibility.py":
            return "python-import-shim-v1"
        if path == "desktop/tests/test_data_root_migration.py":
            return "data-root-migration-v1"
        if path == "desktop/tests/test_data_root_conflict_recovery.py":
            return (
                "installer-upgrade-v1"
                if pattern == "Open Notebook Plus"
                else "data-root-migration-v1"
            )
        if path == "desktop/tests/test_emergency_log.py":
            return "data-root-migration-v1"
        if path == "desktop/tests/test_release_manifest.py":
            return (
                "installer-upgrade-v1"
                if pattern in {"open-notebook-plus", "Open Notebook Plus"}
                else "legacy-artifact-probe-v1"
            )
        if path == "tests/test_task6_active_product.py":
            if pattern in {"/api/onp", "/onp/", "onpFetch"}:
                return "legacy-api-route-v1"
            if pattern in {"open-notebook-plus", "Open Notebook Plus"}:
                return "external-format-v1"
        if path in _PROVEN_LEGACY_TEST_FIXTURE_PATHS and pattern in {
            "Open Notebook Plus",
            "Open Notebook",
            "Open notebook+",
            "open-notebook-Plus",
            "open-notebook-plus",
            "--onp-",
        }:
            return "legacy-test-fixture-v1"
        return None

    if pattern in {"OPEN_NOTEBOOK_", "ONP_"}:
        if path in {
            "frontend/src/lib/features.test.ts",
            "frontend/src/lib/features.ts",
        }:
            return "frontend-env-alias-v1"
        return "env-alias-v1"
    if pattern == "open_notebook":
        if "/database/migrations/" in f"/{path}":
            return "database-record-identifier-v1"
        return "python-import-shim-v1"
    if pattern == "OpenNotebook":
        if path == "api/routers/filesystem.py":
            return "export-directory-fallback-v1"
        return "python-symbol-compat-v1"
    if pattern in {"/api/onp", "/onp/", "onpFetch", "components/onp"}:
        return "legacy-api-route-v1"
    if path == "desktop/app_migration.py":
        return (
            "installer-upgrade-v1"
            if pattern == "Open Notebook Plus"
            else "data-root-migration-v1"
        )
    if path == "desktop/data_root.py":
        return "data-root-migration-v1"
    if path == "deeper_notebook/identity.py":
        return "central-legacy-identity-v1"
    if path == "deeper_notebook/podcasts/profile_names.py":
        return "podcast-profile-identifier-v1"
    if path == "deeper_notebook/local_models/benchmarks.py":
        return "benchmark-history-fallback-v1"
    if path == "deeper_notebook/logging.py":
        return "container-log-fallback-v1"
    if path in {
        "deeper_notebook/studio/exporters/research_bundle.py",
        "deeper_notebook/studio/generation/persistence.py",
        "api/routers/studio/artifacts.py",
    }:
        return "external-format-v1"
    if path in {"desktop/window.py", "desktop/paths.py"}:
        return "installer-upgrade-v1"
    if path == "scripts/repair_desktop_db.sh":
        return (
            "installer-upgrade-v1"
            if pattern == "Open Notebook Plus"
            else "data-root-migration-v1"
        )
    if (
        path.startswith("desktop/build/")
        or path.startswith(".github/workflows/")
    ):
        return (
            "installer-upgrade-v1"
            if pattern in {"open-notebook-plus", "Open Notebook Plus"}
            else "legacy-artifact-probe-v1"
        )
    return None


def load_allowlist(path: Path) -> dict[OccurrenceKey, Approval]:
    """Load approvals pinned to exact path/content occurrences."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("allowlist must be an object")
    if frozenset(payload) != _TOP_LEVEL_FIELDS:
        raise ValueError(
            "allowlist must contain exactly the schema_version, "
            "persisted_queue_identifiers, compatibility_contracts, and "
            "entries fields"
        )
    if payload.get("schema_version") != ALLOWLIST_SCHEMA_VERSION:
        raise ValueError(
            f"allowlist schema_version must be {ALLOWLIST_SCHEMA_VERSION}"
        )
    persisted_identifiers = payload.get("persisted_queue_identifiers")
    if not isinstance(persisted_identifiers, list):
        raise ValueError(
            "allowlist persisted_queue_identifiers must be a list"
        )
    queue_identifier_fields = {
        "registration": frozenset(
            {"kind", "path", "symbol", "callee", "app", "command"}
        ),
        "submission": frozenset(
            {
                "kind",
                "path",
                "symbol",
                "callee",
                "app",
                "command",
                "invocation",
            }
        ),
    }
    for identifier in persisted_identifiers:
        if not isinstance(identifier, dict):
            raise ValueError(
                "each persisted queue identifier must be an object"
            )
        expected_fields = queue_identifier_fields.get(identifier.get("kind"))
        if (
            expected_fields is None
            or frozenset(identifier) != expected_fields
            or not all(
                isinstance(value, str) and value
                for value in identifier.values()
            )
        ):
            raise ValueError(
                "persisted queue identifiers must use the exact registration "
                "or submission field schema"
            )
    raw_contracts = payload.get("compatibility_contracts")
    if not isinstance(raw_contracts, dict):
        raise ValueError("allowlist compatibility_contracts must be an object")
    contracts: dict[str, dict[str, str]] = {}
    root = _allowlist_root(path)
    for contract_id, contract in raw_contracts.items():
        if (
            not isinstance(contract_id, str)
            or not contract_id
            or not isinstance(contract, dict)
            or frozenset(contract) != _COMPATIBILITY_CONTRACT_FIELDS
            or not all(isinstance(value, str) and value for value in contract.values())
        ):
            raise ValueError(
                "compatibility contracts must use the exact structured fields"
            )
        if contract["kind"] not in COMPATIBILITY_CONTRACT_KINDS:
            raise ValueError(
                "compatibility contract kind must be a closed compatibility "
                "contract kind"
            )
        if len(contract["retention_reason"].split()) < 8:
            raise ValueError(
                "compatibility contract requires a meaningful retention reason"
            )
        _validate_compatibility_proof(root, contract["proof"])
        contracts[contract_id] = contract
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("allowlist must contain an 'entries' list")

    allowlist: dict[OccurrenceKey, Approval] = {}
    explanations: set[str] = set()
    referenced_contracts: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each allowlist entry must be an object")
        if frozenset(entry) != _ENTRY_FIELDS:
            raise ValueError(
                "allowlist entries must contain exactly the documented fields"
            )
        allowlisted_path = entry.get("path")
        pattern = entry.get("pattern")
        source = entry.get("source")
        line = entry.get("line")
        column = entry.get("column")
        digest = entry.get("context_sha256")
        category = entry.get("category")
        rationale = entry.get("rationale")
        if not all(
            isinstance(value, str)
            for value in (
                allowlisted_path,
                pattern,
                source,
                digest,
                category,
            )
        ):
            raise ValueError(
                "allowlist path, pattern, source, context_sha256, and category "
                "must be strings"
            )
        if pattern not in LEGACY_PATTERNS:
            raise ValueError(
                "allowlist pattern must be one of the scanner's built-in "
                "legacy patterns"
            )
        if source not in {"path", "content"}:
            raise ValueError("allowlist source must be 'path' or 'content'")
        if source == "content" and (
            not isinstance(line, int) or isinstance(line, bool) or line < 1
        ):
            raise ValueError("content approvals require a positive line")
        if source == "path" and line is not None:
            raise ValueError("path approvals require line=null")
        if (
            not isinstance(column, int)
            or isinstance(column, bool)
            or column < 1
        ):
            raise ValueError("allowlist column must be a positive integer")
        if not _SHA256_RE.fullmatch(digest):
            raise ValueError("allowlist context_sha256 must be 64 lowercase hex chars")
        if not isinstance(rationale, dict):
            raise ValueError("allowlist rationale must be an object")
        if frozenset(rationale) != _RATIONALE_FIELDS:
            raise ValueError(
                "allowlist rationale must contain exactly path, pattern, "
                "source, line, column, context_sha256, category, and explanation"
            )
        rationale_location = (
            rationale.get("path"),
            rationale.get("source"),
            rationale.get("line"),
            rationale.get("column"),
            rationale.get("context_sha256"),
        )
        if rationale_location != (
            allowlisted_path,
            source,
            line,
            column,
            digest,
        ):
            raise ValueError(
                "allowlist rationale location and context hash must exactly "
                "match its occurrence"
            )
        if rationale.get("pattern") != pattern:
            raise ValueError(
                "allowlist rationale pattern must exactly match its occurrence"
            )
        if rationale.get("category") != category:
            raise ValueError(
                "allowlist rationale category must exactly match its occurrence"
            )
        explanation = rationale.get("explanation")
        if not isinstance(explanation, str):
            raise ValueError("allowlist rationale explanation must be a string")
        normalized_explanation = " ".join(explanation.split())
        casefolded_explanation = normalized_explanation.casefold()
        if (
            len(normalized_explanation) < _MIN_EXPLANATION_CHARS
            or len(normalized_explanation.split()) < _MIN_EXPLANATION_WORDS
            or casefolded_explanation in _GENERIC_EXPLANATIONS
        ):
            raise ValueError(
                "allowlist rationale requires a meaningful explanation of at "
                f"least {_MIN_EXPLANATION_CHARS} characters and "
                f"{_MIN_EXPLANATION_WORDS} words"
            )
        if (
            allowlisted_path.casefold() in casefolded_explanation
            or pattern.casefold() in casefolded_explanation
            or category.casefold() in casefolded_explanation
            or digest.casefold() in casefolded_explanation
            or _STRUCTURAL_LOCATOR_RE.search(normalized_explanation)
            or _MECHANICAL_LOCATOR_RE.search(normalized_explanation)
        ):
            raise ValueError(
                "allowlist rationale explanation must not repeat structural "
                "path, locator, hash, pattern, or category fields"
            )
        duplicate_key = semantic_explanation_key(normalized_explanation)
        if duplicate_key in explanations:
            raise ValueError(
                "allowlist rationale contains a duplicate semantic explanation"
            )
        explanations.add(duplicate_key)
        if category not in CATEGORIES[:-1]:
            raise ValueError(f"invalid allowlist category: {category}")
        compatibility_contract = rationale.get("compatibility_contract")
        if category == "compatibility_alias":
            if (
                not isinstance(compatibility_contract, str)
                or compatibility_contract not in contracts
            ):
                raise ValueError(
                    "compatibility_alias requires a structured compatibility "
                    "contract"
                )
            if _compatibility_is_forbidden(
                root,
                allowlisted_path,
                pattern,
                source,
                line,
            ):
                raise ValueError(
                    "active UI, documentation, or default identifier cannot "
                    "use compatibility_alias"
                )
            referenced_contracts.add(compatibility_contract)
        elif compatibility_contract is not None:
            raise ValueError(
                "non-compatibility rationale cannot reference a compatibility "
                "contract"
            )
        if "*" in allowlisted_path:
            raise ValueError("allowlist paths must be exact; wildcards are disallowed")
        key: OccurrenceKey = (
            allowlisted_path,
            pattern,
            source,
            line,
            column,
            digest,
        )
        if key in allowlist:
            raise ValueError(f"duplicate allowlist entry: {key}")
        allowlist[key] = Approval(
            category=category,
            rationale=Rationale(
                path=allowlisted_path,
                pattern=pattern,
                source=source,
                line=line,
                column=column,
                context_sha256=digest,
                category=category,
                explanation=normalized_explanation,
                compatibility_contract=compatibility_contract,
            ),
        )
    unused_contracts = set(contracts) - referenced_contracts
    if unused_contracts:
        raise ValueError(
            "allowlist contains unused compatibility contracts: "
            f"{sorted(unused_contracts)}"
        )
    return allowlist


def _tracked_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [
        raw_path.decode("utf-8", errors="surrogateescape")
        for raw_path in result.stdout.split(b"\0")
        if raw_path
    ]


def _text_lines(path: Path) -> list[str] | None:
    data = path.read_bytes()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return None


def _pattern_occurrences(
    value: str,
    patterns: tuple[str, ...],
) -> list[tuple[str, int, int]]:
    occurrences: list[tuple[str, int, int]] = []
    for pattern in patterns:
        if not pattern:
            continue
        start = 0
        while (match_start := value.find(pattern, start)) != -1:
            match_end = match_start + len(pattern)
            occurrences.append((pattern, match_start, match_end))
            start = match_start + 1
    return sorted(
        occurrences,
        key=lambda occurrence: (
            occurrence[1],
            -(occurrence[2] - occurrence[1]),
            occurrence[0],
        ),
    )


def audit_repository(root: Path, allowlist: Allowlist) -> dict[str, object]:
    """Scan tracked path names and UTF-8 text contents for legacy references."""
    categorized: dict[str, list[dict[str, object]]] = {
        category: [] for category in CATEGORIES
    }
    matched_allowlist: set[OccurrenceKey] = set()

    def record(
        *,
        path: str,
        pattern: str,
        source: str,
        line: int | None,
        column: int,
        context: str,
    ) -> None:
        key = _occurrence_key(
            path=path,
            pattern=pattern,
            source=source,
            line=line,
            column=column,
            context=context,
        )
        category = classify_match(key, allowlist)
        entry: dict[str, object] = {
            "path": path,
            "pattern": pattern,
            "source": source,
            "column": column,
            "context_sha256": key[-1],
        }
        if line is not None:
            entry["line"] = line
        categorized[category].append(entry)
        if key in allowlist:
            matched_allowlist.add(key)

    for relative_path in _tracked_paths(root):
        # The allowlist contains hashes of audited source lines. Auditing its
        # own serialized entries would make those hashes self-referential and
        # impossible to stabilize. Its structure and every field are instead
        # validated by ``load_allowlist`` before repository scanning begins.
        if relative_path in _AUDIT_METADATA_PATHS:
            continue
        patterns = patterns_for_path(relative_path, allowlist)
        for pattern, start, _end in _pattern_occurrences(relative_path, patterns):
            record(
                path=relative_path,
                pattern=pattern,
                source="path",
                line=None,
                column=start + 1,
                context=relative_path,
            )

        absolute_path = root / relative_path
        if not absolute_path.is_file():
            continue
        lines = _text_lines(absolute_path)
        if lines is None:
            continue
        for line_number, line in enumerate(lines, start=1):
            occurrences = _pattern_occurrences(line, patterns)
            allowed_contexts = [
                (pattern, start, end)
                for pattern, start, end in occurrences
                if classify_match(
                    _occurrence_key(
                        path=relative_path,
                        pattern=pattern,
                        source="content",
                        line=line_number,
                        column=start + 1,
                        context=line,
                    ),
                    allowlist,
                )
                != "unexpected_active_identity"
            ]
            for pattern, start, end in occurrences:
                if any(
                    (context_pattern, pattern) in _SAFE_NESTED_APPROVALS
                    and context_start <= start
                    and end <= context_end
                    for context_pattern, context_start, context_end in allowed_contexts
                ):
                    continue
                record(
                    path=relative_path,
                    pattern=pattern,
                    source="content",
                    line=line_number,
                    column=start + 1,
                    context=line,
                )

    stale = [
        {
            "path": key[0],
            "pattern": key[1],
            "source": key[2],
            "line": key[3],
            "column": key[4],
            "context_sha256": key[5],
            "category": approval.category,
            "rationale": approval.rationale.as_dict(),
        }
        for key, approval in allowlist.items()
        if key not in matched_allowlist
    ]
    return {
        "schema_version": ALLOWLIST_SCHEMA_VERSION,
        "categories": categorized,
        "summary": {
            category: len(matches) for category, matches in categorized.items()
        },
        "stale_allowlist": stale,
    }


def _without_safe_nested_matches(
    matches: list[dict[str, object]],
) -> list[dict[str, object]]:
    identities = {
        (
            match["path"],
            match["source"],
            match.get("line"),
            match["column"],
            match["context_sha256"],
            match["pattern"],
        )
        for match in matches
    }
    return [
        match
        for match in matches
        if not any(
            match["pattern"] == nested
            and (
                match["path"],
                match["source"],
                match.get("line"),
                match["column"],
                match["context_sha256"],
                broader,
            )
            in identities
            for broader, nested in _SAFE_NESTED_APPROVALS
        )
    ]


def regenerate_allowlist(
    root: Path,
    allowlist_path: Path,
) -> dict[str, object]:
    """Regenerate exact approvals and semantic rationales deterministically."""
    payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("allowlist must be an object")
    persisted_identifiers = payload.get("persisted_queue_identifiers")
    entries = payload.get("entries")
    if not isinstance(persisted_identifiers, list) or not isinstance(
        entries,
        list,
    ):
        raise ValueError(
            "allowlist regeneration requires persisted identifiers and entries"
        )

    category_sets: dict[tuple[str, str], set[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("allowlist regeneration entries must be objects")
        path = entry.get("path")
        pattern = entry.get("pattern")
        category = entry.get("category")
        if not all(isinstance(value, str) for value in (path, pattern, category)):
            raise ValueError(
                "allowlist regeneration entries require path, pattern, and category"
            )
        category_sets.setdefault((path, pattern), set()).add(category)
    ambiguous = {
        key: categories
        for key, categories in category_sets.items()
        if len(categories) != 1
    }
    if ambiguous:
        raise ValueError(f"ambiguous category policies: {ambiguous}")
    category_policy = {
        key: next(iter(categories))
        for key, categories in category_sets.items()
    }
    category_policy.update(_CATEGORY_OVERRIDES)

    report = audit_repository(root.resolve(), {})
    raw_matches = report["categories"]["unexpected_active_identity"]
    assert isinstance(raw_matches, list)
    matches = _without_safe_nested_matches(raw_matches)
    generated_entries: list[dict[str, object]] = []
    semantic_keys: set[str] = set()
    used_contracts: set[str] = set()
    uncontracted_groups: dict[tuple[str, str], int] = {}
    for match in sorted(
        matches,
        key=lambda item: (
            item["path"],
            item["source"],
            item.get("line") or 0,
            item["column"],
            item["pattern"],
        ),
    ):
        policy_key = (match["path"], match["pattern"])
        category = category_policy.get(policy_key)
        match_path = Path(str(match["path"]))
        if category is None:
            if match_path.suffix.lower() in {".md", ".mdx", ".rst"}:
                category = "migration_documentation"
            elif match["path"] == "scripts/rebrand_audit.py":
                category = "migration_documentation"
            elif str(match["path"]).startswith("output/"):
                category = "historical_reference"
            else:
                raise ValueError(
                    "unclassified occurrence requires explicit review: "
                    f"{match}"
                )
        if category == "compatibility_alias":
            if match_path.suffix.lower() in {".md", ".mdx", ".rst"}:
                category = "migration_documentation"
            elif match["path"] == "scripts/rebrand_audit.py":
                category = "migration_documentation"
            elif str(match["path"]).startswith("output/"):
                category = "historical_reference"
        compatibility_contract: str | None = None
        if category == "compatibility_alias":
            compatibility_contract = compatibility_contract_for_occurrence(match)
            if compatibility_contract is None:
                path_group = str(match["path"]).split("/", 1)[0]
                group_key = (path_group, str(match["pattern"]))
                uncontracted_groups[group_key] = (
                    uncontracted_groups.get(group_key, 0) + 1
                )
                continue
            used_contracts.add(compatibility_contract)
        explanation = semantic_explanation_for_occurrence(
            root.resolve(),
            match,
            category,
        )
        semantic_key = semantic_explanation_key(explanation)
        if semantic_key in semantic_keys:
            raise ValueError(
                "semantic rationale generation produced a duplicate: "
                f"{explanation}"
            )
        semantic_keys.add(semantic_key)
        line = match.get("line")
        rationale = {
            "path": match["path"],
            "pattern": match["pattern"],
            "source": match["source"],
            "line": line,
            "column": match["column"],
            "context_sha256": match["context_sha256"],
            "category": category,
            "explanation": explanation,
            "compatibility_contract": compatibility_contract,
        }
        generated_entries.append(
            {
                "path": match["path"],
                "pattern": match["pattern"],
                "source": match["source"],
                "line": line,
                "column": match["column"],
                "context_sha256": match["context_sha256"],
                "category": category,
                "rationale": rationale,
            }
        )
    if uncontracted_groups:
        grouped = [
            {
                "path_group": path_group,
                "pattern": pattern,
                "count": count,
            }
            for (path_group, pattern), count in sorted(
                uncontracted_groups.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]
        raise ValueError(
            "uncontracted compatibility groups require review: "
            + json.dumps(grouped, sort_keys=True)
        )
    generated: dict[str, object] = {
        "schema_version": ALLOWLIST_SCHEMA_VERSION,
        "persisted_queue_identifiers": persisted_identifiers,
        "compatibility_contracts": {
            contract_id: _DEFAULT_COMPATIBILITY_CONTRACTS[contract_id]
            for contract_id in sorted(used_contracts)
        },
        "entries": generated_entries,
    }
    allowlist_path.write_text(
        json.dumps(generated, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return generated


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the script's parent repository)",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=Path(__file__).with_name("rebrand-allowlist.json"),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail for unexpected active identity or stale allowlist entries",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="rewrite exact approvals with deterministic semantic rationales",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.regenerate:
        regenerate_allowlist(args.root.resolve(), args.allowlist)
    allowlist = load_allowlist(args.allowlist)
    report = audit_repository(args.root.resolve(), allowlist)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.check:
        categories = report["categories"]
        assert isinstance(categories, dict)
        if categories["unexpected_active_identity"] or report["stale_allowlist"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
