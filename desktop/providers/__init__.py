"""Pluggable model-backend interface used by the launcher.

Each provider knows how to detect availability, list models, and (for backends
that need a process) spawn one and yield env vars to inject into the upstream
FastAPI process so existing langchain integrations Just Work.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class ProviderError(RuntimeError):
    """Raised by provider methods on detection or startup failure."""


class ProviderEnv(dict[str, str]):
    """Environment variables to inject into the upstream FastAPI process."""


@runtime_checkable
class ModelProvider(Protocol):
    name: str = ...  # type: ignore

    def is_available(self) -> bool: ...
    def list_models(self) -> list[str]: ...
    def start(self, model: str) -> ProviderEnv: ...
    def stop(self) -> None: ...
