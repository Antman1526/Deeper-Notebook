"""Contract tests for Deeper Notebook product-owned environment aliases."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from deeper_notebook.environment import (
    SETTINGS,
    LegacyEnvironmentWarning,
    apply_product_environment,
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


def _apply_and_resolve_secret(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
):
    canonical = "DEEPER_NOTEBOOK_ENCRYPTION_KEY"
    _clear_aliases(monkeypatch, canonical)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        normalized = apply_product_environment(os.environ)
        value, receipt = resolve_env(
            canonical,
            getter=get_secret_from_env,
            with_receipt=True,
        )
    return value, receipt, normalized, caught


def _assert_secret_values_not_exposed(
    secrets: tuple[str, ...],
    receipt,
    caught,
    captured,
) -> None:
    observable = (
        repr(receipt)
        + "".join(str(item.message) for item in caught)
        + captured.out
        + captured.err
    )
    for secret in secrets:
        assert secret not in observable


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


def test_canonical_direct_secret_beats_lower_legacy_file_and_normalizes_safely(
    monkeypatch,
    tmp_path,
):
    canonical = "DEEPER_NOTEBOOK_ENCRYPTION_KEY"
    _clear_aliases(monkeypatch, canonical)
    legacy_secret_path = tmp_path / "legacy-secret"
    legacy_secret_path.write_text("lower-priority-secret\n", encoding="utf-8")
    monkeypatch.setenv(canonical, "canonical-direct-secret")
    monkeypatch.setenv(
        "OPEN_NOTEBOOK_ENCRYPTION_KEY_FILE",
        str(legacy_secret_path),
    )

    value, receipt = resolve_env(
        canonical,
        getter=get_secret_from_env,
        with_receipt=True,
    )
    normalized = normalize_product_environment(
        {
            canonical: "canonical-direct-secret",
            "OPEN_NOTEBOOK_ENCRYPTION_KEY_FILE": str(legacy_secret_path),
        }
    )

    assert value == "canonical-direct-secret"
    assert receipt.winner == canonical
    assert "canonical-direct-secret" not in repr(receipt)
    assert "lower-priority-secret" not in repr(receipt)
    assert normalized["DEEPER_NOTEBOOK_ENCRYPTION_KEY"] == "canonical-direct-secret"
    assert normalized["OPEN_NOTEBOOK_ENCRYPTION_KEY"] == "canonical-direct-secret"
    assert "DEEPER_NOTEBOOK_ENCRYPTION_KEY_FILE" not in normalized
    assert "OPEN_NOTEBOOK_ENCRYPTION_KEY_FILE" not in normalized


def test_empty_canonical_direct_secret_beats_lower_legacy_file(tmp_path):
    legacy_secret_path = tmp_path / "legacy-secret"
    legacy_secret_path.write_text("lower-priority-secret\n", encoding="utf-8")
    normalized = normalize_product_environment(
        {
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY": "",
            "OPEN_NOTEBOOK_ENCRYPTION_KEY_FILE": str(legacy_secret_path),
        }
    )

    assert normalized["DEEPER_NOTEBOOK_ENCRYPTION_KEY"] == ""
    assert normalized["OPEN_NOTEBOOK_ENCRYPTION_KEY"] == ""
    assert "DEEPER_NOTEBOOK_ENCRYPTION_KEY_FILE" not in normalized
    assert "OPEN_NOTEBOOK_ENCRYPTION_KEY_FILE" not in normalized


def test_file_form_wins_before_direct_form_within_same_alias(tmp_path):
    secret_path = tmp_path / "canonical-secret"
    secret_path.write_text("canonical-file-secret\n", encoding="utf-8")
    normalized = normalize_product_environment(
        {
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY_FILE": str(secret_path),
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY": "canonical-direct-secret",
        }
    )

    assert normalized["DEEPER_NOTEBOOK_ENCRYPTION_KEY_FILE"] == str(secret_path)
    assert normalized["OPEN_NOTEBOOK_ENCRYPTION_KEY_FILE"] == str(secret_path)
    assert normalized["DEEPER_NOTEBOOK_ENCRYPTION_KEY"] == "canonical-direct-secret"
    assert normalized["OPEN_NOTEBOOK_ENCRYPTION_KEY"] == "canonical-direct-secret"
    assert "canonical-file-secret" not in repr(normalized)


def test_empty_file_form_is_still_an_assigned_higher_priority_value():
    normalized = normalize_product_environment(
        {
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY_FILE": "",
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY": "canonical-direct-secret",
        }
    )

    assert normalized["DEEPER_NOTEBOOK_ENCRYPTION_KEY_FILE"] == ""
    assert normalized["OPEN_NOTEBOOK_ENCRYPTION_KEY_FILE"] == ""
    assert normalized["DEEPER_NOTEBOOK_ENCRYPTION_KEY"] == "canonical-direct-secret"
    assert normalized["OPEN_NOTEBOOK_ENCRYPTION_KEY"] == "canonical-direct-secret"


def test_apply_preserves_direct_secret_fallback_for_empty_file_path(
    monkeypatch,
    capsys,
):
    direct_secret = "direct-empty-path-sentinel"
    value, receipt, normalized, caught = _apply_and_resolve_secret(
        monkeypatch,
        {
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY_FILE": "",
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY": direct_secret,
        },
    )

    assert value == direct_secret
    assert normalized["DEEPER_NOTEBOOK_ENCRYPTION_KEY"] == direct_secret
    _assert_secret_values_not_exposed(
        (direct_secret,),
        receipt,
        caught,
        capsys.readouterr(),
    )


def test_apply_preserves_direct_secret_fallback_for_missing_file(
    monkeypatch,
    tmp_path,
    capsys,
):
    direct_secret = "direct-missing-file-sentinel"
    missing_path = tmp_path / "does-not-exist"
    value, receipt, normalized, caught = _apply_and_resolve_secret(
        monkeypatch,
        {
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY_FILE": str(missing_path),
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY": direct_secret,
        },
    )

    assert value == direct_secret
    assert normalized["DEEPER_NOTEBOOK_ENCRYPTION_KEY"] == direct_secret
    _assert_secret_values_not_exposed(
        (direct_secret,),
        receipt,
        caught,
        capsys.readouterr(),
    )


def test_apply_preserves_direct_secret_fallback_for_unreadable_file(
    monkeypatch,
    tmp_path,
    capsys,
):
    direct_secret = "direct-unreadable-file-sentinel"
    secret_path = tmp_path / "unreadable-secret"
    secret_path.write_text("unreadable-file-sentinel\n", encoding="utf-8")
    original_read_text = Path.read_text

    def _deny_target_read(path, *args, **kwargs):
        if path == secret_path:
            raise PermissionError("portable unreadable-file simulation")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _deny_target_read)
    value, receipt, normalized, caught = _apply_and_resolve_secret(
        monkeypatch,
        {
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY_FILE": str(secret_path),
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY": direct_secret,
        },
    )

    assert value == direct_secret
    assert normalized["DEEPER_NOTEBOOK_ENCRYPTION_KEY"] == direct_secret
    _assert_secret_values_not_exposed(
        (direct_secret, "unreadable-file-sentinel"),
        receipt,
        caught,
        capsys.readouterr(),
    )


def test_apply_preserves_direct_secret_fallback_for_empty_content_file(
    monkeypatch,
    tmp_path,
    capsys,
):
    direct_secret = "direct-empty-content-sentinel"
    secret_path = tmp_path / "empty-secret"
    secret_path.write_text(" \n", encoding="utf-8")
    value, receipt, normalized, caught = _apply_and_resolve_secret(
        monkeypatch,
        {
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY_FILE": str(secret_path),
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY": direct_secret,
        },
    )

    assert value == direct_secret
    assert normalized["DEEPER_NOTEBOOK_ENCRYPTION_KEY"] == direct_secret
    _assert_secret_values_not_exposed(
        (direct_secret,),
        receipt,
        caught,
        capsys.readouterr(),
    )


def test_apply_keeps_usable_file_ahead_of_preserved_direct_fallback(
    monkeypatch,
    tmp_path,
    capsys,
):
    file_secret = "usable-file-sentinel"
    direct_secret = "direct-fallback-sentinel"
    secret_path = tmp_path / "usable-secret"
    secret_path.write_text(f"{file_secret}\n", encoding="utf-8")
    value, receipt, normalized, caught = _apply_and_resolve_secret(
        monkeypatch,
        {
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY_FILE": str(secret_path),
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY": direct_secret,
        },
    )

    assert value == file_secret
    assert normalized["DEEPER_NOTEBOOK_ENCRYPTION_KEY"] == direct_secret
    assert normalized["OPEN_NOTEBOOK_ENCRYPTION_KEY"] == direct_secret
    _assert_secret_values_not_exposed(
        (file_secret, direct_secret),
        receipt,
        caught,
        capsys.readouterr(),
    )


def test_apply_keeps_canonical_direct_ahead_of_lower_legacy_file(
    monkeypatch,
    tmp_path,
    capsys,
):
    canonical_secret = "canonical-direct-sentinel"
    legacy_file_secret = "legacy-file-sentinel"
    legacy_path = tmp_path / "legacy-secret"
    legacy_path.write_text(f"{legacy_file_secret}\n", encoding="utf-8")
    value, receipt, normalized, caught = _apply_and_resolve_secret(
        monkeypatch,
        {
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY": canonical_secret,
            "OPEN_NOTEBOOK_ENCRYPTION_KEY_FILE": str(legacy_path),
        },
    )

    assert value == canonical_secret
    assert normalized["OPEN_NOTEBOOK_ENCRYPTION_KEY"] == canonical_secret
    assert "DEEPER_NOTEBOOK_ENCRYPTION_KEY_FILE" not in normalized
    assert "OPEN_NOTEBOOK_ENCRYPTION_KEY_FILE" not in normalized
    _assert_secret_values_not_exposed(
        (canonical_secret, legacy_file_secret),
        receipt,
        caught,
        capsys.readouterr(),
    )


def test_legacy_provider_timeout_is_registered_and_mirrored_for_children():
    canonical = "DEEPER_NOTEBOOK_CONNECTION_TEST_TIMEOUT_SEC_OLLAMA"
    env = {"ONP_CONNECTION_TEST_TIMEOUT_SEC_OLLAMA": "75"}

    with pytest.warns(LegacyEnvironmentWarning):
        normalized = normalize_product_environment(env)

    assert canonical in SETTINGS
    assert normalized[canonical] == "75"
    assert normalized["DN_CONNECTION_TEST_TIMEOUT_SEC_OLLAMA"] == "75"
    assert normalized["OPEN_NOTEBOOK_CONNECTION_TEST_TIMEOUT_SEC_OLLAMA"] == "75"
    assert normalized["ONP_CONNECTION_TEST_TIMEOUT_SEC_OLLAMA"] == "75"


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


@pytest.mark.parametrize("module_name", ["api.main", "commands"])
def test_bootstrap_applies_normalized_aliases_to_process_environment(module_name):
    sentinel = "bootstrap-do-not-leak"
    aliases = (
        "DEEPER_NOTEBOOK_METRICS_AUTH_TOKEN",
        "DN_METRICS_AUTH_TOKEN",
        "OPEN_NOTEBOOK_METRICS_AUTH_TOKEN",
        "ONP_METRICS_AUTH_TOKEN",
    )
    child_env = dict(os.environ)
    for name in aliases:
        child_env.pop(name, None)
    child_env["ONP_METRICS_AUTH_TOKEN"] = sentinel
    script = (
        "import importlib, os\n"
        f"importlib.import_module({module_name!r})\n"
        f"names = {aliases!r}\n"
        f"assert all(os.environ.get(name) == {sentinel!r} for name in names)\n"
        "print('bootstrap-mirrors-present')\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=child_env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    combined_output = completed.stdout + completed.stderr
    assert completed.returncode == 0, combined_output
    assert "bootstrap-mirrors-present" in completed.stdout
    assert sentinel not in combined_output


def test_production_python_does_not_directly_access_legacy_product_keys():
    """All product-owned legacy accesses must route through the central resolver."""
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
                if isinstance(node, ast.Subscript):
                    is_environ_subscript = (
                        isinstance(node.value, ast.Attribute)
                        and isinstance(node.value.value, ast.Name)
                        and node.value.value.id == "os"
                        and node.value.attr == "environ"
                    )
                    key = node.slice
                    if (
                        is_environ_subscript
                        and isinstance(key, ast.Constant)
                        and isinstance(key.value, str)
                        and key.value.startswith(("OPEN_NOTEBOOK_", "ONP_"))
                    ):
                        violations.append(
                            f"{path.relative_to(root)}:{node.lineno}:{key.value}"
                        )
                    continue
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
