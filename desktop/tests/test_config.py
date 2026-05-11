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


def test_theme_defaults_to_light_blue(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg = load_or_create(cfg_path)
    assert cfg.theme == "light-blue"


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
