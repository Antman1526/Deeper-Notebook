"""Ollama provider: detection + model listing only. Ollama daemon is user-managed."""
from __future__ import annotations

import httpx

from desktop.providers import ProviderEnv


class OllamaProvider:
    name: str = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: float = 1.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=self.timeout)
            return r.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
            return False

    def list_models(self) -> list[str]:
        r = httpx.get(f"{self.base_url}/api/tags", timeout=self.timeout)
        if r.status_code != 200:
            raise httpx.HTTPStatusError(
                f"Ollama /api/tags returned {r.status_code}",
                request=r.request,
                response=r,
            )
        return [m["name"] for m in r.json().get("models", [])]

    def start(self, model: str) -> ProviderEnv:
        return ProviderEnv(
            OLLAMA_BASE_URL=self.base_url,
            DEFAULT_MODEL=model,
        )

    def stop(self) -> None:
        return None
