"""Active diagnostics must direct maintainers to the canonical package."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_prompt_optimizer_diagnostic_uses_canonical_package_path():
    source = (ROOT / "deeper_notebook/prompt_optimizer/runner.py").read_text(
        encoding="utf-8"
    )

    assert "update deeper_notebook/prompt_optimizer." in source
    assert "update open_notebook/prompt_optimizer." not in source


def test_migration_diagnostic_uses_canonical_package_path():
    source = (ROOT / "deeper_notebook/database/async_migrate.py").read_text(
        encoding="utf-8"
    )

    assert "deeper_notebook/database/migrations/*.surrealql" in source
    assert "open_notebook/database/migrations/*.surrealql" not in source
