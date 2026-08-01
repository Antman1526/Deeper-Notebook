"""Local model manifest parsing and route-match tests."""
from __future__ import annotations

from pathlib import Path

from deeper_notebook.local_models.gguf_metadata import GGUFMetadata
from deeper_notebook.local_models.inventory import LocalModelInfo
from deeper_notebook.local_models.manifest import (
    build_manifest_recommendations,
    build_manifest_reconciliation,
    find_manifest_matches,
    find_unmatched_manifest_entries,
    load_model_manifest,
)


def test_readiness_is_pure_and_manifest_text_never_verifies_a_model():
    from deeper_notebook.local_models.contracts import (
        ModelReadinessEvidence,
        classify_model_readiness,
    )

    manifest_only = ModelReadinessEvidence(
        file_complete=True,
        supported_runtime=True,
        manifest_state="installed",
        runtime_identity_matches=True,
        health_checked=False,
        health_healthy=False,
        benchmark_accepted=False,
        symlink_trusted=True,
    )
    verified = ModelReadinessEvidence(
        file_complete=True,
        supported_runtime=True,
        manifest_state="installed",
        runtime_identity_matches=True,
        health_checked=True,
        health_healthy=True,
        health_latency_ms=900,
        benchmark_accepted=True,
        symlink_trusted=True,
    )

    assert classify_model_readiness(manifest_only).readiness == "ready_unverified"
    ready = classify_model_readiness(verified)
    assert ready.readiness == "ready_verified"
    assert ready.route_eligible is True


def test_readiness_distinguishes_missing_runtime_from_runtime_identity_mismatch():
    from deeper_notebook.local_models.contracts import (
        ModelReadinessEvidence,
        classify_model_readiness,
    )

    common = {
        "file_complete": True,
        "supported_runtime": True,
        "manifest_state": "installed",
        "symlink_trusted": True,
    }
    no_runtime = classify_model_readiness(
        ModelReadinessEvidence(**common, runtime_configured=False)
    )
    mismatched_runtime = classify_model_readiness(
        ModelReadinessEvidence(**common, runtime_configured=True)
    )

    assert no_runtime.readiness == "requires_runtime"
    assert mismatched_runtime.readiness == "runtime_unavailable"
    assert no_runtime.route_eligible is False
    assert mismatched_runtime.route_eligible is False


def test_manifest_lifecycle_state_is_explicit_and_never_proves_readiness(tmp_path):
    from deeper_notebook.local_models.manifest import manifest_lifecycle_state

    manifest = tmp_path / "manifests" / "model_inventory.md"
    planned = load_model_manifest_from_text(
        "planned",
        manifest,
    )
    removed = load_model_manifest_from_text(
        "removed - retired",
        manifest,
    )

    assert manifest_lifecycle_state(planned) == "planned"
    assert manifest_lifecycle_state(removed) == "removed"


def load_model_manifest_from_text(status: str, manifest: Path):
    from deeper_notebook.local_models.manifest import parse_model_manifest

    return parse_model_manifest(
        "\n".join([
            "| Category | Role | Repo | Local Path | Runtime Type | Estimated Status | Notes |",
            "|---|---|---|---|---|---|---|",
            f"| Test | primary | `example/model` | `MLX/example__model` | MLX | {status} | test |",
        ]),
        manifest_path=manifest,
    )[0]


def _write_manifest(root: Path) -> Path:
    manifest = root / "manifests" / "model_inventory.md"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        "\n".join([
            "# Local Model Inventory",
            "",
            "| Category | Role | Repo | Local Path | Runtime Type | Estimated Status | Notes |",
            "|---|---|---|---|---|---|---|",
            "| Coding Assistant - Mac MLX | primary | `mlx-community/North-Mini-Code-1.0-6bit` | `"
            + str(root / "MLX" / "mlx-community__North-Mini-Code-1.0-6bit")
            + "` | MLX | downloaded - verified | coding and agent workflows |",
        ])
    )
    return manifest


def test_load_model_manifest_parses_markdown_table(tmp_path):
    manifest = _write_manifest(tmp_path)

    entries = load_model_manifest(tmp_path)

    assert len(entries) == 1
    assert entries[0].manifest_path == str(manifest)
    assert entries[0].category == "Coding Assistant - Mac MLX"
    assert entries[0].role == "primary"
    assert entries[0].repo == "mlx-community/North-Mini-Code-1.0-6bit"
    assert entries[0].runtime_type == "MLX"


def test_find_manifest_matches_uses_path_and_repo_keys(tmp_path):
    _write_manifest(tmp_path)
    model = LocalModelInfo(
        name="mlx-community/North-Mini-Code-1.0-6bit",
        path=str(tmp_path / "MLX" / "mlx-community__North-Mini-Code-1.0-6bit"),
        runtime="mlx",
        metadata=GGUFMetadata(
            architecture="qwen2",
            context_length=32768,
            quant="6bit",
            parameter_count_b=7,
            file_size_bytes=1024,
        ),
    )

    matches = find_manifest_matches(model, load_model_manifest(tmp_path))

    assert len(matches) == 1
    assert matches[0].category == "Coding Assistant - Mac MLX"


def test_find_unmatched_manifest_entries_reports_curated_models_missing_from_scan(tmp_path):
    _write_manifest(tmp_path)
    scanned = [
        LocalModelInfo(
            name="other-model",
            path=str(tmp_path / "GGUF" / "other-model.gguf"),
            runtime="gguf",
            metadata=GGUFMetadata(
                architecture=None,
                context_length=None,
                quant=None,
                parameter_count_b=None,
                file_size_bytes=1024,
            ),
        )
    ]

    unmatched = find_unmatched_manifest_entries(load_model_manifest(tmp_path), scanned)

    assert len(unmatched) == 1
    assert unmatched[0].repo == "mlx-community/North-Mini-Code-1.0-6bit"


def test_build_manifest_reconciliation_classifies_matched_missing_and_unsupported(tmp_path):
    manifest = tmp_path / "manifests" / "model_inventory.md"
    manifest.parent.mkdir(parents=True)
    mlx_path = tmp_path / "MLX" / "mlx-community__North-Mini-Code-1.0-6bit"
    transformers_path = tmp_path / "Transformers" / "microsoft__FastContext-1.0-4B-SFT"
    missing_path = tmp_path / "MLX" / "missing__Curated-Model-4bit"
    manifest.write_text(
        "\n".join([
            "# Local Model Inventory",
            "",
            "| Category | Role | Repo | Local Path | Runtime Type | Estimated Status | Notes |",
            "|---|---|---|---|---|---|---|",
            f"| Coding Assistant - Mac MLX | primary | `mlx-community/North-Mini-Code-1.0-6bit` | `{mlx_path}` | MLX | downloaded - verified | ready |",
            f"| Agentic Workflows - Transformers | backup | `microsoft/FastContext-1.0-4B-SFT` | `{transformers_path}` | Transformers | skipped - existing verified | needs runtime |",
            f"| Reasoning - Mac MLX | backup | `missing/Curated-Model-4bit` | `{missing_path}` | MLX | missing from scan | should be checked |",
        ])
    )
    models = [
        LocalModelInfo(
            name="mlx-community/North-Mini-Code-1.0-6bit",
            path=str(mlx_path),
            runtime="mlx",
            metadata=GGUFMetadata(
                architecture="qwen2",
                context_length=32768,
                quant="6bit",
                parameter_count_b=7,
                file_size_bytes=1024,
            ),
        ),
        LocalModelInfo(
            name="microsoft/FastContext-1.0-4B-SFT",
            path=str(transformers_path),
            runtime="transformers",
            metadata=GGUFMetadata(
                architecture="llama",
                context_length=65536,
                quant=None,
                parameter_count_b=4,
                file_size_bytes=2048,
            ),
        ),
    ]

    reconciliation = build_manifest_reconciliation(load_model_manifest(tmp_path), models)
    by_repo = {row.entry.repo: row for row in reconciliation}

    assert by_repo["mlx-community/North-Mini-Code-1.0-6bit"].status == "matched"
    assert by_repo["microsoft/FastContext-1.0-4B-SFT"].status == "unsupported_runtime"
    assert by_repo["microsoft/FastContext-1.0-4B-SFT"].matched_model_runtime == "transformers"
    assert by_repo["missing/Curated-Model-4bit"].status == "missing"
    assert by_repo["missing/Curated-Model-4bit"].setup_task is not None
    assert by_repo["missing/Curated-Model-4bit"].setup_task.action_type == "download_snapshot"
    assert by_repo["missing/Curated-Model-4bit"].setup_task.command == (
        f"huggingface-cli download missing/Curated-Model-4bit --local-dir {missing_path}"
    )
    assert by_repo["microsoft/FastContext-1.0-4B-SFT"].setup_task is not None
    assert by_repo["microsoft/FastContext-1.0-4B-SFT"].setup_task.action_type == "configure_runtime"


def test_build_manifest_reconciliation_creates_direct_gguf_download_task(tmp_path):
    manifest = tmp_path / "manifests" / "model_inventory.md"
    manifest.parent.mkdir(parents=True)
    gguf_path = tmp_path / "GGUF" / "bartowski__Qwen2.5-7B-Instruct-GGUF" / "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    manifest.write_text(
        "\n".join([
            "# Local Model Inventory",
            "",
            "| Category | Role | Repo | Local Path | Runtime Type | Estimated Status | Notes |",
            "|---|---|---|---|---|---|---|",
            f"| General Chat - GGUF | primary | `bartowski/Qwen2.5-7B-Instruct-GGUF` | `{gguf_path}` | GGUF | missing from scan | exact quant |",
        ])
    )

    reconciliation = build_manifest_reconciliation(load_model_manifest(tmp_path), [])
    task = reconciliation[0].setup_task

    assert reconciliation[0].status == "missing"
    assert task is not None
    assert task.action_type == "download_gguf"
    assert task.repo_id == "bartowski/Qwen2.5-7B-Instruct-GGUF"
    assert task.filename == "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    assert task.target_path == str(gguf_path)


def test_build_manifest_recommendations_rank_mlx_and_emit_setup_tasks(tmp_path):
    manifest = tmp_path / "manifests" / "model_inventory.md"
    manifest.parent.mkdir(parents=True)
    mlx_path = tmp_path / "MLX" / "mlx-community__North-Mini-Code-1.0-6bit"
    gguf_path = (
        tmp_path
        / "GGUF"
        / "bartowski__Qwen2.5-7B-Instruct-GGUF"
        / "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    )
    manifest.write_text(
        "\n".join([
            "# Local Model Inventory",
            "",
            "| Category | Role | Repo | Local Path | Runtime Type | Estimated Status | Notes |",
            "|---|---|---|---|---|---|---|",
            f"| General Chat - GGUF | primary | `bartowski/Qwen2.5-7B-Instruct-GGUF` | `{gguf_path}` | GGUF | missing from scan | exact quant |",
            f"| Coding Assistant - Mac MLX | primary | `mlx-community/North-Mini-Code-1.0-6bit` | `{mlx_path}` | MLX | missing from scan | coding and agent workflows |",
        ])
    )

    cards = build_manifest_recommendations(load_model_manifest(tmp_path), [])

    assert cards[0].runtime_type == "MLX"
    assert cards[0].setup_task is not None
    assert cards[0].setup_task.action_type == "download_snapshot"
    assert cards[1].runtime_type == "GGUF"
    assert cards[1].setup_task is not None
    assert cards[1].setup_task.action_type == "download_gguf"
    assert cards[1].setup_task.filename == "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
