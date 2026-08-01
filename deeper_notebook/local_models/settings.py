"""Owner-only persistence for non-secret device-local model preferences."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ExecutionPolicy = Literal["strict_local", "local_preferred", "custom"]
ComputeProfile = Literal["efficient", "balanced", "maximum_quality"]
_POLICIES = {"strict_local", "local_preferred", "custom"}
_PROFILES = {"efficient", "balanced", "maximum_quality"}


def validate_model_root(root: Path) -> Path:
    """Require an existing, readable directory without scanning its contents."""
    candidate = Path(root).expanduser()
    try:
        if not candidate.is_dir() or not os.access(candidate, os.R_OK | os.X_OK):
            raise ValueError
        next(candidate.iterdir(), None)
    except (OSError, ValueError):
        raise ValueError("Model root must be a readable directory.") from None
    return candidate


@dataclass(frozen=True)
class LocalModelSettings:
    model_dir: Path
    execution_policy: ExecutionPolicy = "strict_local"
    compute_profile: ComputeProfile = "balanced"
    local_model_memory_limit_bytes: int | None = None
    role_overrides: dict[str, str] = field(default_factory=dict)
    trusted_external_model_roots: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_model_root(self.model_dir)
        if self.execution_policy not in _POLICIES:
            raise ValueError("Unsupported execution policy.")
        if self.compute_profile not in _PROFILES:
            raise ValueError("Unsupported compute profile.")
        if self.local_model_memory_limit_bytes is not None and self.local_model_memory_limit_bytes < 0:
            raise ValueError("Memory limit must be non-negative.")


class LocalModelSettingsStore:
    """Small, secret-free TOML store with atomic owner-only writes."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> LocalModelSettings:
        raw = tomllib.loads(self.path.read_text())
        return LocalModelSettings(
            model_dir=Path(raw["model_dir"]),
            execution_policy=raw.get("execution_policy", "strict_local"),
            compute_profile=raw.get("compute_profile", "balanced"),
            local_model_memory_limit_bytes=raw.get("local_model_memory_limit_bytes"),
            role_overrides=dict(raw.get("role_overrides", {})),
            trusted_external_model_roots=tuple(raw.get("trusted_external_model_roots", ())),
        )

    def save(self, settings: LocalModelSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        lines = [
            f"model_dir = {settings.model_dir.as_posix()!r}",
            f"execution_policy = {settings.execution_policy!r}",
            f"compute_profile = {settings.compute_profile!r}",
        ]
        if settings.local_model_memory_limit_bytes is not None:
            lines.append(
                "local_model_memory_limit_bytes = "
                f"{settings.local_model_memory_limit_bytes}"
            )
        if settings.trusted_external_model_roots:
            values = ", ".join(repr(item) for item in settings.trusted_external_model_roots)
            lines.append(f"trusted_external_model_roots = [{values}]")
        if settings.role_overrides:
            lines.append("[role_overrides]")
            lines.extend(f"{key!r} = {value!r}" for key, value in settings.role_overrides.items())
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text("\n".join(lines) + "\n")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.path)
