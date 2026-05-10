"""Config persistence for the desktop launcher and first-run wizard."""
from __future__ import annotations

import os
import secrets
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

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


Provider = Literal["ollama", "llamacpp", "none"]
_VALID_PROVIDERS: set[str] = {"ollama", "llamacpp", "none"}


@dataclass(frozen=True)
class Config:
    model_dir: Path
    provider: Provider
    default_model: str
    surreal_user: str
    surreal_password: str
    theme: str = "light-blue"

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data["model_dir"] = str(self.model_dir)
        toml = "".join(f"{k} = {_toml_string(v)}\n" for k, v in data.items())
        path.write_text(toml)


def default_model_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ["USERPROFILE"]) / "Desktop" / "AI_Models"
    return Path(os.environ["HOME"]) / "Desktop" / "AI_Models"


def default_config_path() -> Path:
    if sys.platform == "win32":
        return Path(os.environ["USERPROFILE"]) / ".open-notebook-plus" / "config.toml"
    return Path(os.environ["HOME"]) / ".open-notebook-plus" / "config.toml"


def load_or_create(path: Path) -> Config:
    if not path.exists():
        cfg = Config(
            model_dir=default_model_dir(),
            provider="none",
            default_model="",
            surreal_user="root",
            surreal_password=secrets.token_urlsafe(24),
            theme="light-blue",
        )
        cfg.save(path)
        return cfg

    raw = tomllib.loads(path.read_text())
    provider = raw.get("provider", "none")
    if provider not in _VALID_PROVIDERS:
        raise ValueError(f"Invalid provider in {path}: {provider!r}")
    return Config(
        model_dir=Path(raw["model_dir"]),
        provider=provider,  # type: ignore[arg-type]
        default_model=raw.get("default_model", ""),
        surreal_user=raw.get("surreal_user", "root"),
        surreal_password=raw["surreal_password"],
        theme=raw.get("theme", "light-blue"),
    )
