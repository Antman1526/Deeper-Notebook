"""Contract tests for Deeper Notebook product-owned environment aliases."""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from deeper_notebook.environment import (
    SETTINGS,
    LegacyEnvironmentWarning,
    normalize_product_environment,
    resolve_env,
)
from open_notebook.utils.encryption import get_secret_from_env


@pytest.fixture(autouse=True)
def _isolate_legacy_warning_state():
    import deeper_notebook.environment as environment

    environment._reset_warning_state_for_tests()
    yield
    environment._reset_warning_state_for_tests()


def _clear_aliases(monkeypatch: pytest.MonkeyPatch, canonical: str) -> None:
    for name in SETTINGS[canonical].precedence:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(f"{name}_FILE", raising=False)


def test_canonical_long_name_wins(monkeypatch):
    _clear_aliases(monkeypatch, "DEEPER_NOTEBOOK_PASSWORD")
    monkeypatch.setenv("DEEPER_NOTEBOOK_PASSWORD", "canonical")
    monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", "legacy")

    assert resolve_env("DEEPER_NOTEBOOK_PASSWORD") == "canonical"


def test_legacy_long_name_remains_accepted(monkeypatch):
    _clear_aliases(monkeypatch, "DEEPER_NOTEBOOK_PASSWORD")
    monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", "legacy")

    with pytest.warns(LegacyEnvironmentWarning):
        assert resolve_env("DEEPER_NOTEBOOK_PASSWORD") == "legacy"


@pytest.mark.parametrize(
    ("winner", "expected"),
    [
        ("DEEPER_NOTEBOOK_DB_POOL_SIZE", "16"),
        ("DN_DB_POOL_SIZE", "8"),
        ("OPEN_NOTEBOOK_DB_POOL_SIZE", "6"),
        ("ONP_DB_POOL_SIZE", "4"),
    ],
)
def test_all_four_precedence_positions(monkeypatch, winner, expected):
    canonical = "DEEPER_NOTEBOOK_DB_POOL_SIZE"
    _clear_aliases(monkeypatch, canonical)
    aliases = SETTINGS[canonical].precedence
    start = aliases.index(winner)
    values = {
        "DEEPER_NOTEBOOK_DB_POOL_SIZE": "16",
        "DN_DB_POOL_SIZE": "8",
        "OPEN_NOTEBOOK_DB_POOL_SIZE": "6",
        "ONP_DB_POOL_SIZE": "4",
    }
    for name in aliases[start:]:
        monkeypatch.setenv(name, values[name])

    if winner.startswith(("OPEN_NOTEBOOK_", "ONP_")):
        with pytest.warns(LegacyEnvironmentWarning):
            assert resolve_env(canonical) == expected
    else:
        assert resolve_env(canonical) == expected


def test_short_name_precedence_and_child_process_mirroring(monkeypatch):
    canonical = "DEEPER_NOTEBOOK_DB_POOL_SIZE"
    _clear_aliases(monkeypatch, canonical)
    env = {
        "DEEPER_NOTEBOOK_DB_POOL_SIZE": "16",
        "DN_DB_POOL_SIZE": "8",
        "OPEN_NOTEBOOK_DB_POOL_SIZE": "6",
        "ONP_DB_POOL_SIZE": "4",
        "UNRELATED": "preserved",
    }

    normalized = normalize_product_environment(env)

    assert normalized["DEEPER_NOTEBOOK_DB_POOL_SIZE"] == "16"
    assert normalized["DN_DB_POOL_SIZE"] == "16"
    assert normalized["OPEN_NOTEBOOK_DB_POOL_SIZE"] == "16"
    assert normalized["ONP_DB_POOL_SIZE"] == "16"
    assert normalized["UNRELATED"] == "preserved"
    assert env["DN_DB_POOL_SIZE"] == "8", "normalization must not mutate its input"


def test_deliberately_empty_canonical_value_wins(monkeypatch):
    canonical = "DEEPER_NOTEBOOK_PASSWORD"
    _clear_aliases(monkeypatch, canonical)
    monkeypatch.setenv(canonical, "")
    monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", "legacy")

    value, receipt = resolve_env(canonical, with_receipt=True)

    assert value == ""
    assert receipt.winner == canonical
    assert receipt.used_legacy is False


def test_missing_value_uses_default_and_receipt_has_no_winner(monkeypatch):
    canonical = "DEEPER_NOTEBOOK_PASSWORD"
    _clear_aliases(monkeypatch, canonical)

    value, receipt = resolve_env(canonical, "fallback", with_receipt=True)

    assert value == "fallback"
    assert receipt.winner is None
    assert receipt.used_legacy is False


def test_receipt_never_contains_secret_value(monkeypatch):
    canonical = "DEEPER_NOTEBOOK_ENCRYPTION_KEY"
    _clear_aliases(monkeypatch, canonical)
    monkeypatch.setenv("OPEN_NOTEBOOK_ENCRYPTION_KEY", "do-not-log-me")

    with pytest.warns(LegacyEnvironmentWarning):
        value, receipt = resolve_env(canonical, with_receipt=True)

    assert value == "do-not-log-me"
    assert receipt.winner == "OPEN_NOTEBOOK_ENCRYPTION_KEY"
    assert "do-not-log-me" not in repr(receipt)


def test_file_aware_secret_getter_obeys_alias_precedence_without_leaking(
    monkeypatch,
    tmp_path,
):
    canonical = "DEEPER_NOTEBOOK_ENCRYPTION_KEY"
    _clear_aliases(monkeypatch, canonical)
    secret_path = tmp_path / "encryption-key"
    secret_path.write_text("canonical-file-secret\n", encoding="utf-8")
    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KEY_FILE", str(secret_path))
    monkeypatch.setenv("OPEN_NOTEBOOK_ENCRYPTION_KEY", "legacy-secret")

    value, receipt = resolve_env(
        canonical,
        getter=get_secret_from_env,
        with_receipt=True,
    )

    assert value == "canonical-file-secret"
    assert receipt.winner == canonical
    assert "canonical-file-secret" not in repr(receipt)
    assert "legacy-secret" not in repr(receipt)


def test_legacy_warning_is_once_per_key_and_never_contains_value(monkeypatch):
    import deeper_notebook.environment as environment

    canonical = "DEEPER_NOTEBOOK_PASSWORD"
    _clear_aliases(monkeypatch, canonical)
    monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", "warning-secret")
    environment._reset_warning_state_for_tests()

    with pytest.warns(LegacyEnvironmentWarning) as captured:
        assert resolve_env(canonical) == "warning-secret"
        assert resolve_env(canonical) == "warning-secret"

    assert len(captured) == 1
    assert "OPEN_NOTEBOOK_PASSWORD" in str(captured[0].message)
    assert "warning-secret" not in str(captured[0].message)


def test_every_registered_setting_has_unique_aliases():
    owners: dict[str, str] = {}
    for canonical, aliases in SETTINGS.items():
        assert canonical == aliases.canonical
        for name in aliases.precedence:
            assert name not in owners, f"{name} is registered by two settings"
            owners[name] = canonical


def test_production_python_does_not_directly_read_legacy_product_keys():
    """All product-owned legacy reads must route through the central resolver."""
    root = Path(__file__).resolve().parents[1]
    production_roots = ("api", "commands", "desktop", "open_notebook")
    violations: list[str] = []
    getter_names = {
        "getenv",
        "get_secret_from_env",
        "_env_bool",
        "_env_flag",
        "_env_float",
        "_env_int",
        "_env",
        "_n_gpu_layers",
        "_startup_timeout",
        "_truthy_env",
        "env_int",
    }

    for production_root in production_roots:
        for path in (root / production_root).rglob("*.py"):
            if "tests" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                function_name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                is_environ_get = (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get"
                    and isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == "environ"
                )
                if function_name not in getter_names and not is_environ_get:
                    continue
                key = node.args[0]
                if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                    continue
                if key.value.startswith(("OPEN_NOTEBOOK_", "ONP_")):
                    violations.append(
                        f"{path.relative_to(root)}:{node.lineno}:{key.value}"
                    )

    assert violations == [], "direct legacy environment reads:\n" + "\n".join(
        violations
    )
