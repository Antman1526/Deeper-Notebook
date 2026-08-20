"""Compatibility checks for the split Studio router package."""

from __future__ import annotations


def test_legacy_package_patch_syncs_to_workflow_endpoint_globals(monkeypatch) -> None:
    from api.routers import studio
    from api.routers.studio import workflows

    replacement = object()
    monkeypatch.setattr(studio, "Notebook", replacement)

    studio._sync_legacy_patches()

    assert workflows.Notebook is replacement
