"""Device-local model-routing preferences remain safe and restartable."""
from __future__ import annotations

from pathlib import Path

import pytest

from deeper_notebook.local_models.settings import (
    LocalModelSettings,
    LocalModelSettingsStore,
    validate_model_root,
)


def test_owner_only_atomic_store_round_trips_a_model_root_with_spaces(tmp_path: Path):
    root = tmp_path / "Model Library With Spaces"
    root.mkdir()
    path = tmp_path / "settings" / "local-models.toml"
    store = LocalModelSettingsStore(path)
    settings = LocalModelSettings(model_dir=root)

    store.save(settings)

    assert path.exists()
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert not path.with_suffix(".toml.tmp").exists()
    assert store.load() == settings


@pytest.mark.parametrize("name", ["missing", "not-a-directory"])
def test_validate_model_root_rejects_missing_and_non_directory_roots(
    tmp_path: Path, name: str
):
    target = tmp_path / name
    if name == "not-a-directory":
        target.write_text("not a model root")

    with pytest.raises(ValueError, match="readable directory"):
        validate_model_root(target)


def test_validate_model_root_rejects_an_unreadable_directory(
    monkeypatch, tmp_path: Path
):
    root = tmp_path / "unreadable"
    root.mkdir()
    monkeypatch.setattr(
        Path,
        "iterdir",
        lambda _self: (_ for _ in ()).throw(PermissionError("denied")),
    )

    with pytest.raises(ValueError, match="readable directory"):
        validate_model_root(root)


def test_balanced_is_the_safe_default_and_survives_restart(tmp_path: Path):
    root = tmp_path / "AI Models"
    root.mkdir()
    path = tmp_path / "local-models.toml"
    LocalModelSettingsStore(path).save(LocalModelSettings(model_dir=root))

    restored = LocalModelSettingsStore(path).load()

    assert restored.compute_profile == "balanced"
    assert restored.execution_policy == "strict_local"
