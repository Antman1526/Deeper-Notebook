"""Config persistence for the desktop launcher and first-run wizard."""
from __future__ import annotations

import os
import secrets
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from desktop.data_root import active_data_root


def _toml_string(v: str) -> str:
    """TOML-safe string serialization.

    Prefers literal strings (single-quoted, no escape interpretation) when the
    value has no single quote or newline; otherwise falls back to a basic
    string with backslash and double-quote escapes. Sufficient for the values
    we serialize: paths, provider names, model identifiers, surreal credentials.
    """
    if "'" not in v and "\n" not in v:
        return f"'{v}'"
    escaped = v.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_value(value: object) -> str:
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, tuple):
        return "[" + ", ".join(_toml_string(str(item)) for item in value) + "]"
    raise TypeError(f"Unsupported config value: {type(value)!r}")


Provider = Literal["ollama", "llamacpp", "mlx", "none"]
_VALID_PROVIDERS: set[str] = {"ollama", "llamacpp", "mlx", "none"}


@dataclass(frozen=True)
class Config:
    model_dir: Path
    provider: Provider
    default_model: str
    surreal_user: str
    surreal_password: str
    theme: str = "light-blue"
    openchronicle_choice: str = "skip"
    encryption_key: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    execution_policy: Literal["strict_local", "local_preferred", "custom"] = "strict_local"
    compute_profile: Literal["efficient", "balanced", "maximum_quality"] = "balanced"
    local_model_memory_limit_bytes: int | None = None
    role_overrides: dict[str, str] = field(default_factory=dict)
    trusted_external_model_roots: tuple[str, ...] = ()

    def save(self, path: Path) -> None:
        # v0.6.8 — config.toml stores both the SurrealDB password and the
        # Fernet encryption_key that decrypts every saved API key + Gmail
        # OAuth token. With default umask (022 on most Macs/Linux) the file
        # is world-readable, which means any other local user on a shared
        # machine could exfiltrate the user's tokens. Restrict to owner-only.
        path.parent.mkdir(parents=True, exist_ok=True)
        # Tighten parent dir too — same secrets reachable via dir listing.
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass  # non-fatal (read-only fs, Windows ACL, etc.)
        data = asdict(self)
        data["model_dir"] = str(self.model_dir)
        role_overrides = data.pop("role_overrides", {})
        toml = "".join(
            f"{key} = {_toml_value(value)}\n"
            for key, value in data.items()
            if value is not None
        )
        if role_overrides:
            toml += "[role_overrides]\n"
            toml += "".join(
                f"{_toml_string(str(key))} = {_toml_string(str(value))}\n"
                for key, value in role_overrides.items()
            )
        # Write atomically via temp file + replace, so a crashed write
        # never leaves a half-written world-readable file behind.
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(toml)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass  # Windows: file permission model is different; rely on ACLs
        os.replace(tmp, path)


def default_model_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ["USERPROFILE"]) / "Desktop" / "AI_Models"
    return Path(os.environ["HOME"]) / "Desktop" / "AI_Models"


def default_config_path() -> Path:
    return active_data_root() / "config.toml"


def load_or_create(path: Path) -> Config:
    if not path.exists():
        cfg = Config(
            model_dir=default_model_dir(),
            provider="none",
            default_model="",
            surreal_user="root",
            surreal_password=secrets.token_urlsafe(24),
            theme="light-blue",
            openchronicle_choice="skip",
            encryption_key=secrets.token_urlsafe(32),
        )
        cfg.save(path)
        return cfg

    raw = tomllib.loads(path.read_text())
    provider = raw.get("provider", "none")
    if provider not in _VALID_PROVIDERS:
        raise ValueError(f"Invalid provider in {path}: {provider!r}")

    encryption_key = raw.get("encryption_key", "")
    cfg = Config(
        model_dir=Path(raw["model_dir"]),
        provider=provider,  # type: ignore[arg-type]
        default_model=raw.get("default_model", ""),
        surreal_user=raw.get("surreal_user", "root"),
        surreal_password=raw["surreal_password"],
        theme=raw.get("theme", "light-blue"),
        openchronicle_choice=raw.get("openchronicle_choice", "skip"),
        encryption_key=encryption_key if encryption_key else secrets.token_urlsafe(32),
        execution_policy=raw.get("execution_policy", "strict_local"),
        compute_profile=raw.get("compute_profile", "balanced"),
        local_model_memory_limit_bytes=raw.get("local_model_memory_limit_bytes"),
        role_overrides=dict(raw.get("role_overrides", {})),
        trusted_external_model_roots=tuple(raw.get("trusted_external_model_roots", ())),
    )
    # If the key was missing or blank in the file, persist the freshly-generated one.
    if not encryption_key:
        cfg.save(path)
    return cfg
