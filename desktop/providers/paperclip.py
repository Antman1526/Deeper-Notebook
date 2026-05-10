"""Paperclip provider — Phase 2 stub.

TODO(phase-2): Implement against Paperclip's HTTP API. Surface Paperclip-hired
agents matching role/skill filters as model options, and on start() return env
vars routing the upstream FastAPI request handler at Paperclip's chat endpoint
(or an OpenAI-compatible bridge if Paperclip exposes one).

Paperclip URL configured via Settings page once shipped.
"""
from __future__ import annotations

from desktop.providers import ProviderEnv


class PaperclipProvider:
    name: str = "paperclip"

    def is_available(self) -> bool:
        return False  # always unavailable until Phase 2 lands

    def list_models(self) -> list[str]:
        raise NotImplementedError("Phase 2 — see TODO in desktop/providers/paperclip.py")

    def start(self, model: str) -> ProviderEnv:
        raise NotImplementedError("Phase 2 — see TODO in desktop/providers/paperclip.py")

    def stop(self) -> None:
        return None
