"""Helpers for Antman's AI_Models manifest.

The manifest is a Markdown table generated outside the app under
`<model_dir>/manifests/model_inventory.md`. Most helpers let Deeper Notebook
Plus compare scanned models with that curated intent. The patch helpers are
intentionally narrow: append one validated row, with a backup, inside the
configured model directory.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from deeper_notebook.local_models.inventory import LocalModelInfo
from deeper_notebook.local_models.role_routing import inventory_model_match_keys


@dataclass(frozen=True)
class ManifestModelEntry:
    manifest_path: str
    category: str
    role: str
    repo: str
    local_path: str
    runtime_type: str
    estimated_status: str
    notes: str


@dataclass(frozen=True)
class ManifestReconciliationEntry:
    entry: ManifestModelEntry
    status: str
    status_reason: str
    matched_model_name: str | None = None
    matched_model_path: str | None = None
    matched_model_runtime: str | None = None
    setup_task: "ManifestSetupTask | None" = None


@dataclass(frozen=True)
class ManifestRecommendation:
    id: str
    label: str
    description: str
    repo_id: str
    filename: str | None
    runtime_type: str
    target_path: str
    status: str
    tags: list[str]
    approx_size_gb: float
    context_length: int
    setup_task: "ManifestSetupTask | None" = None


@dataclass(frozen=True)
class ManifestSetupTask:
    action_type: str
    label: str
    description: str
    repo_id: str | None = None
    filename: str | None = None
    target_path: str | None = None
    command: str | None = None
    setup_href: str | None = None


@dataclass(frozen=True)
class ManifestRowPreview:
    manifest_path: str
    row: str
    entry: ManifestModelEntry
    duplicate: bool
    duplicate_entry: ManifestModelEntry | None = None


@dataclass(frozen=True)
class ManifestRowApplyResult:
    manifest_path: str
    backup_path: str | None
    row: str
    entry: ManifestModelEntry
    duplicate: bool


class ManifestRowError(ValueError):
    """Raised when a manifest draft row cannot be safely applied."""


def manifest_lifecycle_state(entry: ManifestModelEntry) -> str:
    """Return curation lifecycle only; a Markdown claim is never proof.

    Readiness still requires file, runtime identity, health, benchmark, and
    symlink evidence from the inventory classifier.
    """
    status = str(entry.estimated_status or "").lower()
    if "removed" in status or "retired" in status:
        return "removed"
    if "planned" in status:
        return "planned"
    return "installed"


def model_manifest_path(model_dir: Path | str) -> Path:
    return Path(model_dir) / "manifests" / "model_inventory.md"


def load_model_manifest(model_dir: Path | str) -> list[ManifestModelEntry]:
    path = model_manifest_path(model_dir)
    try:
        text = path.read_text()
    except OSError:
        return []
    return parse_model_manifest(text, manifest_path=path)


def parse_model_manifest(
    text: str,
    *,
    manifest_path: Path | str,
) -> list[ManifestModelEntry]:
    rows: list[ManifestModelEntry] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [_clean_cell(cell) for cell in stripped.strip("|").split("|")]
        if len(cells) < 7:
            continue
        if cells[0].lower() in {"category", "---"}:
            continue
        if all(set(cell) <= {"-"} for cell in cells[:2]):
            continue
        rows.append(
            ManifestModelEntry(
                manifest_path=str(manifest_path),
                category=cells[0],
                role=cells[1],
                repo=cells[2],
                local_path=cells[3],
                runtime_type=cells[4],
                estimated_status=cells[5],
                notes=cells[6],
            )
        )
    return rows


def preview_manifest_row(
    model_dir: Path | str,
    row: str,
) -> ManifestRowPreview:
    manifest_path = model_manifest_path(model_dir)
    normalized_row, entry = normalize_manifest_row(row, manifest_path=manifest_path)
    existing = load_model_manifest(model_dir)
    duplicate = _find_duplicate_entry(entry, existing)
    return ManifestRowPreview(
        manifest_path=str(manifest_path),
        row=normalized_row,
        entry=entry,
        duplicate=duplicate is not None,
        duplicate_entry=duplicate,
    )


def append_manifest_row(
    model_dir: Path | str,
    row: str,
    *,
    allow_duplicate: bool = False,
) -> ManifestRowApplyResult:
    manifest_path = model_manifest_path(model_dir)
    preview = preview_manifest_row(model_dir, row)
    if preview.duplicate and not allow_duplicate:
        raise ManifestRowError(
            "A manifest row for this category, repo, and local path already exists."
        )

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if manifest_path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = manifest_path.with_name(f"{manifest_path.name}.bak-{stamp}")
        shutil.copy2(manifest_path, backup_path)
    else:
        manifest_path.write_text(_manifest_table_header())

    current = manifest_path.read_text() if manifest_path.exists() else ""
    separator = "" if current.endswith("\n") or not current else "\n"
    manifest_path.write_text(f"{current}{separator}{preview.row}\n")

    return ManifestRowApplyResult(
        manifest_path=preview.manifest_path,
        backup_path=str(backup_path) if backup_path else None,
        row=preview.row,
        entry=preview.entry,
        duplicate=preview.duplicate,
    )


def normalize_manifest_row(
    row: str,
    *,
    manifest_path: Path | str,
) -> tuple[str, ManifestModelEntry]:
    raw = str(row or "").strip()
    if not raw:
        raise ManifestRowError("Manifest row is required.")
    if len(raw) > 10_000:
        raise ManifestRowError("Manifest row is too long.")
    if "\n" in raw or "\r" in raw:
        raise ManifestRowError("Manifest row must be a single Markdown table row.")
    if not raw.startswith("|") or not raw.endswith("|"):
        raise ManifestRowError("Manifest row must start and end with `|`.")

    cells = [_clean_cell(cell) for cell in raw.strip("|").split("|")]
    if len(cells) != 7:
        raise ManifestRowError(
            "Manifest row must contain exactly seven cells: Category, Role, Repo, "
            "Local Path, Runtime Type, Estimated Status, and Notes."
        )
    if cells[0].lower() == "category":
        raise ManifestRowError("Manifest header rows cannot be applied.")
    if all(set(cell) <= {"-"} for cell in cells[:2]):
        raise ManifestRowError("Manifest separator rows cannot be applied.")
    if not cells[0] or not cells[2] or not cells[3]:
        raise ManifestRowError("Category, Repo, and Local Path are required.")

    entry = ManifestModelEntry(
        manifest_path=str(manifest_path),
        category=cells[0],
        role=cells[1],
        repo=cells[2],
        local_path=cells[3],
        runtime_type=cells[4],
        estimated_status=cells[5],
        notes=cells[6],
    )
    normalized = (
        f"| {_manifest_cell(entry.category)} | {_manifest_cell(entry.role)} | "
        f"`{_manifest_cell(entry.repo)}` | `{_manifest_cell(entry.local_path)}` | "
        f"{_manifest_cell(entry.runtime_type)} | {_manifest_cell(entry.estimated_status)} | "
        f"{_manifest_cell(entry.notes)} |"
    )
    return normalized, entry


def find_manifest_matches(
    model: LocalModelInfo | None,
    entries: list[ManifestModelEntry],
) -> list[ManifestModelEntry]:
    if model is None:
        return []

    model_path = _resolved_path(model.path)
    model_keys = inventory_model_match_keys(model.name, model.path)
    matches: list[ManifestModelEntry] = []
    for entry in entries:
        if _entry_matches_model(
            entry, model, model_path=model_path, model_keys=model_keys
        ):
            matches.append(entry)

    return matches


def find_unmatched_manifest_entries(
    entries: list[ManifestModelEntry],
    models: list[LocalModelInfo],
) -> list[ManifestModelEntry]:
    matched_ids: set[tuple[str, str, str]] = set()
    for model in models:
        for entry in find_manifest_matches(model, entries):
            matched_ids.add(_entry_identity(entry))
    return [entry for entry in entries if _entry_identity(entry) not in matched_ids]


def build_manifest_reconciliation(
    entries: list[ManifestModelEntry],
    models: list[LocalModelInfo],
) -> list[ManifestReconciliationEntry]:
    rows: list[ManifestReconciliationEntry] = []
    for entry in entries:
        model = _find_matching_model(entry, models)
        if model is None:
            rows.append(
                ManifestReconciliationEntry(
                    entry=entry,
                    status="missing",
                    status_reason="Not found in the current local model scan.",
                    setup_task=_setup_task_for_missing_entry(entry),
                )
            )
            continue

        runtime = (model.runtime or "gguf").lower()
        if runtime not in {"gguf", "mlx"}:
            rows.append(
                ManifestReconciliationEntry(
                    entry=entry,
                    status="unsupported_runtime",
                    status_reason=(
                        "Found in the scan, but this runtime is inventory-only "
                        "until a runnable provider is configured."
                    ),
                    matched_model_name=model.name,
                    matched_model_path=model.path,
                    matched_model_runtime=model.runtime,
                    setup_task=_setup_task_for_unsupported_runtime(entry),
                )
            )
            continue

        rows.append(
            ManifestReconciliationEntry(
                entry=entry,
                status="matched",
                status_reason="Found in the current local model scan.",
                matched_model_name=model.name,
                matched_model_path=model.path,
                matched_model_runtime=model.runtime,
            )
        )
    return rows


def build_manifest_recommendations(
    entries: list[ManifestModelEntry],
    models: list[LocalModelInfo],
    *,
    limit: int = 8,
) -> list[ManifestRecommendation]:
    rows = build_manifest_reconciliation(entries, models)
    rows.sort(key=_recommendation_sort_key)
    return [_recommendation_from_reconciliation(row) for row in rows[: max(0, limit)]]


def _setup_task_for_missing_entry(
    entry: ManifestModelEntry,
) -> ManifestSetupTask | None:
    runtime = entry.runtime_type.strip().lower()
    repo_id = entry.repo.strip()
    local_path = entry.local_path.strip()
    if not repo_id or not local_path:
        return None

    if runtime == "gguf" and local_path.lower().endswith(".gguf"):
        filename = Path(local_path).name
        if _is_huggingface_repo_id(repo_id) and filename:
            return ManifestSetupTask(
                action_type="download_gguf",
                label="Download GGUF",
                description=(
                    "Start a managed GGUF download using the manifest repo "
                    "and exact target filename."
                ),
                repo_id=repo_id,
                filename=filename,
                target_path=local_path,
            )

    if _is_huggingface_repo_id(repo_id):
        return ManifestSetupTask(
            action_type="download_snapshot",
            label="Copy setup command",
            description=(
                "Copy a Hugging Face snapshot download command for this manifest row."
            ),
            repo_id=repo_id,
            target_path=local_path,
            command=f"huggingface-cli download {repo_id} --local-dir {local_path}",
        )

    return ManifestSetupTask(
        action_type="manual",
        label="Review manifest row",
        description=(
            "This manifest row does not have enough structured information "
            "for an automatic setup task."
        ),
        target_path=local_path,
    )


def _setup_task_for_unsupported_runtime(
    entry: ManifestModelEntry,
) -> ManifestSetupTask:
    return ManifestSetupTask(
        action_type="configure_runtime",
        label="Open launcher preferences",
        description=(
            f"{entry.runtime_type} assets are visible in inventory, but need "
            "a configured runnable provider before they can be used."
        ),
        repo_id=entry.repo,
        target_path=entry.local_path,
        setup_href="/settings/launcher-prefs",
    )


def _recommendation_from_reconciliation(
    row: ManifestReconciliationEntry,
) -> ManifestRecommendation:
    entry = row.entry
    runtime = entry.runtime_type.strip().upper() or "UNKNOWN"
    tags = [
        "manifest",
        runtime.lower(),
        _role_tag(entry.role),
        row.status,
    ]
    if "verified" in entry.estimated_status.lower():
        tags.append("verified")
    filename = (
        row.setup_task.filename
        if row.setup_task and row.setup_task.filename
        else Path(entry.local_path).name or None
    )
    return ManifestRecommendation(
        id=f"manifest:{entry.repo}:{entry.local_path}",
        label=entry.category or entry.repo,
        description=_recommendation_description(row),
        repo_id=entry.repo,
        filename=filename,
        runtime_type=runtime,
        target_path=entry.local_path,
        status=row.status,
        tags=[tag for tag in tags if tag],
        approx_size_gb=0,
        context_length=0,
        setup_task=row.setup_task,
    )


def _recommendation_description(row: ManifestReconciliationEntry) -> str:
    entry = row.entry
    parts = [
        entry.role or "curated",
        entry.estimated_status or row.status,
        entry.notes,
    ]
    return " - ".join(part for part in parts if part)


def _recommendation_sort_key(row: ManifestReconciliationEntry):
    entry = row.entry
    return (
        _runtime_recommendation_priority(entry.runtime_type),
        _manifest_role_priority(entry.role),
        _status_recommendation_priority(row.status),
        entry.category.lower(),
        entry.repo.lower(),
    )


def _runtime_recommendation_priority(runtime: str) -> int:
    normalized = runtime.strip().lower()
    if normalized == "mlx":
        return 0
    if normalized == "gguf":
        return 1
    return 2


def _manifest_role_priority(role: str) -> int:
    normalized = role.strip().lower()
    if normalized.startswith("primary"):
        return 0
    if normalized.startswith("backup"):
        return 1
    if normalized.startswith("priority"):
        return 2
    if normalized.startswith("requested"):
        return 3
    return 4


def _status_recommendation_priority(status: str) -> int:
    if status == "matched":
        return 0
    if status == "missing":
        return 1
    if status == "unsupported_runtime":
        return 2
    return 3


def _role_tag(role: str) -> str:
    normalized = role.strip().lower()
    if normalized.startswith("primary"):
        return "primary"
    if normalized.startswith("backup"):
        return "backup"
    if normalized.startswith("priority"):
        return "priority"
    if normalized.startswith("requested"):
        return "requested"
    return normalized.replace(" ", "-")


def _clean_cell(value: str) -> str:
    return value.strip().strip("`").strip()


def _manifest_cell(value: str) -> str:
    return (value or "").replace("|", "/").strip()


def _manifest_table_header() -> str:
    return "\n".join(
        [
            "# Local Model Inventory",
            "",
            "| Category | Role | Repo | Local Path | Runtime Type | Estimated Status | Notes |",
            "|---|---|---|---|---|---|---|",
            "",
        ]
    )


def _is_huggingface_repo_id(value: str) -> bool:
    return bool(
        re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*",
            value,
        )
    )


def _resolved_path(value: str) -> str | None:
    if not value:
        return None
    try:
        return str(Path(value).expanduser().resolve())
    except OSError:
        return value


def _entry_identity(entry: ManifestModelEntry) -> tuple[str, str, str]:
    return (entry.repo, entry.local_path, entry.category)


def _find_duplicate_entry(
    entry: ManifestModelEntry,
    entries: list[ManifestModelEntry],
) -> ManifestModelEntry | None:
    identity = _entry_identity(entry)
    for existing in entries:
        if _entry_identity(existing) == identity:
            return existing
    return None


def _find_matching_model(
    entry: ManifestModelEntry,
    models: list[LocalModelInfo],
) -> LocalModelInfo | None:
    for model in models:
        if _entry_matches_model(entry, model):
            return model
    return None


def _entry_matches_model(
    entry: ManifestModelEntry,
    model: LocalModelInfo,
    *,
    model_path: str | None = None,
    model_keys: set[str] | None = None,
) -> bool:
    current_model_path = (
        model_path if model_path is not None else _resolved_path(model.path)
    )
    entry_path = _resolved_path(entry.local_path)
    if current_model_path and entry_path and current_model_path == entry_path:
        return True

    current_model_keys = model_keys or inventory_model_match_keys(
        model.name, model.path
    )
    entry_keys = inventory_model_match_keys(entry.repo, entry.local_path)
    return bool(current_model_keys & entry_keys)
