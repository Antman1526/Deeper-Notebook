import secrets
from pathlib import Path

import pytest

from desktop.config import Config, default_model_dir, load_or_create


def test_default_model_dir_macos(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_model_dir() == tmp_path / "Desktop" / "AI_Models"


def test_default_model_dir_windows(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert default_model_dir() == tmp_path / "Desktop" / "AI_Models"


def test_load_or_create_writes_default_when_missing(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg = load_or_create(cfg_path)
    assert cfg_path.exists()
    assert cfg.model_dir.is_absolute()
    assert cfg.provider == "none"
    assert cfg.default_model == ""
    assert len(cfg.surreal_password) >= 24


def test_load_or_create_reads_existing(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        'model_dir = "/tmp/foo"\n'
        'provider = "ollama"\n'
        'default_model = "llama3.1"\n'
        'surreal_user = "root"\n'
        'surreal_password = "supersecretsupersecret"\n'
    )
    cfg = load_or_create(cfg_path)
    assert cfg.model_dir == Path("/tmp/foo")
    assert cfg.provider == "ollama"
    assert cfg.default_model == "llama3.1"
    assert cfg.surreal_password == "supersecretsupersecret"


def test_save_round_trips(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg = Config(model_dir=tmp_path / "AI", provider="llamacpp",
                 default_model="x.gguf", surreal_user="root",
                 surreal_password="ABCDEFGHIJKLMNOPQRSTUVWX")
    cfg.save(cfg_path)
    loaded = load_or_create(cfg_path)
    assert loaded == cfg


def test_load_or_create_accepts_mlx_provider(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        'model_dir = "/tmp/foo"\n'
        'provider = "mlx"\n'
        'default_model = "MLX/mlx-community__North-Mini-Code-1.0-6bit"\n'
        'surreal_user = "root"\n'
        'surreal_password = "supersecretsupersecret"\n'
    )
    cfg = load_or_create(cfg_path)
    assert cfg.provider == "mlx"
    assert cfg.default_model == "MLX/mlx-community__North-Mini-Code-1.0-6bit"


def test_invalid_provider_raises(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('model_dir = "/tmp"\nprovider = "bogus"\n'
                        'default_model = ""\nsurreal_user = "root"\n'
                        'surreal_password = "AAAAAAAAAAAAAAAAAAAAAAAA"\n')
    with pytest.raises(ValueError, match="provider"):
        load_or_create(cfg_path)


def test_save_round_trips_windows_path(tmp_path):
    """Backslashes in model_dir must round-trip safely."""
    cfg_path = tmp_path / "config.toml"
    cfg = Config(
        model_dir=Path(r"C:\Users\foo\Desktop\AI_Models"),
        provider="llamacpp",
        default_model="x.gguf",
        surreal_user="root",
        surreal_password="ABCDEFGHIJKLMNOPQRSTUVWX",
    )
    cfg.save(cfg_path)
    # On a real Windows machine load_or_create returns a WindowsPath, but
    # tomllib parses the *string*; what matters is the string survives.
    loaded = load_or_create(cfg_path)
    assert str(loaded.model_dir) == r"C:\Users\foo\Desktop\AI_Models"


def test_save_handles_quote_in_value(tmp_path):
    """Embedded double quotes in user-supplied strings must survive."""
    cfg_path = tmp_path / "config.toml"
    cfg = Config(
        model_dir=tmp_path / "AI",
        provider="llamacpp",
        default_model='weird"name.gguf',
        surreal_user="root",
        surreal_password="ABCDEFGHIJKLMNOPQRSTUVWX",
    )
    cfg.save(cfg_path)
    loaded = load_or_create(cfg_path)
    assert loaded.default_model == 'weird"name.gguf'


def test_theme_defaults_to_research_core_dark(tmp_path):
    cfg = load_or_create(tmp_path / "config.toml")
    assert cfg.theme == "research-core-dark"


def test_existing_theme_is_not_replaced_by_new_default(tmp_path):
    cfg_path = tmp_path / "config.toml"
    Config(model_dir=tmp_path, provider="none", default_model="",
           surreal_user="root", surreal_password="A" * 24,
           theme="light-blue").save(cfg_path)
    assert load_or_create(cfg_path).theme == "light-blue"


def test_theme_round_trips(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg = Config(model_dir=tmp_path, provider="none", default_model="",
                 surreal_user="root", surreal_password="A" * 24, theme="dracula")
    cfg.save(cfg_path)
    assert load_or_create(cfg_path).theme == "dracula"


def test_encryption_key_defaults_to_random():
    """Two fresh Configs must have different keys; missing key is regenerated."""
    cfg1 = Config(
        model_dir=Path("/tmp"), provider="none", default_model="",
        surreal_user="root", surreal_password="A" * 24,
    )
    cfg2 = Config(
        model_dir=Path("/tmp"), provider="none", default_model="",
        surreal_user="root", surreal_password="A" * 24,
    )
    assert cfg1.encryption_key != cfg2.encryption_key
    assert len(cfg1.encryption_key) >= 32


def test_load_or_create_regenerates_missing_encryption_key(tmp_path):
    """Existing config file without encryption_key gets one generated and saved."""
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        'model_dir = "/tmp/foo"\n'
        'provider = "none"\n'
        'default_model = ""\n'
        'surreal_user = "root"\n'
        'surreal_password = "supersecretsupersecretXX"\n'
    )
    cfg = load_or_create(cfg_path)
    assert cfg.encryption_key  # non-empty
    assert len(cfg.encryption_key) >= 32
    # The key must now be persisted back to the file.
    cfg2 = load_or_create(cfg_path)
    assert cfg2.encryption_key == cfg.encryption_key


def test_openchronicle_choice_defaults_to_skip(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg = load_or_create(cfg_path)
    assert cfg.openchronicle_choice == "skip"


def test_openchronicle_choice_round_trips(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg = Config(model_dir=tmp_path, provider="none", default_model="",
                 surreal_user="root", surreal_password="A" * 24,
                 openchronicle_choice="prompt")
    cfg.save(cfg_path)
    assert load_or_create(cfg_path).openchronicle_choice == "prompt"


def test_config_file_is_owner_only_on_unix(tmp_path, monkeypatch):
    """v0.6.8 regression: config.toml contains the Fernet encryption key
    that protects every saved API key + Gmail OAuth token. With default
    umask the file would be world-readable on shared Macs/Linux."""
    import os
    import sys
    if sys.platform == "win32":
        pytest.skip("Unix permission bits don't apply to Windows ACLs")
    # Pretend umask is something permissive (022) so we can verify chmod
    # actually clamps it down regardless.
    monkeypatch.setattr("os.umask", lambda x: 0o022)
    cfg_path = tmp_path / ".onp" / "config.toml"
    cfg = Config(
        model_dir=tmp_path,
        provider="none",
        default_model="",
        surreal_user="root",
        surreal_password="x" * 24,
    )
    cfg.save(cfg_path)
    mode = cfg_path.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0o600 perms on config, got {oct(mode)}"


def test_config_save_is_atomic(tmp_path):
    """Writing via tmp + replace means a stale partial file can never be
    read by another reader. Verify there's no leftover .tmp after save."""
    cfg_path = tmp_path / "config.toml"
    Config(
        model_dir=tmp_path,
        provider="none",
        default_model="",
        surreal_user="root",
        surreal_password="x" * 24,
    ).save(cfg_path)
    assert cfg_path.exists()
    leftover = cfg_path.with_suffix(cfg_path.suffix + ".tmp")
    assert not leftover.exists(), "atomic-replace should leave no .tmp file"


def test_old_config_receives_safe_local_routing_defaults(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        'model_dir = "/tmp/AI Models"\n'
        'provider = "none"\n'
        'default_model = ""\n'
        'surreal_user = "root"\n'
        'surreal_password = "supersecretsupersecretXX"\n'
    )

    cfg = load_or_create(cfg_path)

    assert cfg.compute_profile == "balanced"
    assert cfg.execution_policy == "strict_local"
    assert cfg.local_model_memory_limit_bytes is None
    assert cfg.role_overrides == {}
    assert cfg.trusted_external_model_roots == ()
