"""Hermes-agents provider — Phase 2 stub.

TODO(phase-2): Auto-download the canonical Hermes 3 Llama-3.1 8B GGUF into the
configured model directory and register it under the "Hermes Agents" label in
the picker. If the v2026.5.7 release is an agent runtime rather than just
weights, spawn that runtime as a separate provider and route via its
OpenAI-compatible bridge.

Reference: https://github.com/NousResearch/hermes-agent/releases/tag/v2026.5.7
"""
from __future__ import annotations

from desktop.providers import ProviderEnv


class HermesProvider:
    name: str = "hermes"

    def is_available(self) -> bool:
        return False

    def list_models(self) -> list[str]:
        raise NotImplementedError("Phase 2 — see TODO in desktop/providers/hermes.py")

    def start(self, model: str) -> ProviderEnv:
        raise NotImplementedError("Phase 2 — see TODO in desktop/providers/hermes.py")

    def stop(self) -> None:
        return None
